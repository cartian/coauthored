---
date: 2026-01-26
description: Technical design for adding CRM Entity-rooted graph views to entity-map
repository: fund-admin
tags: [tech-design, entity-map, crm-entity, gp-member, architecture]
---

# Entity Map: CRM Entity-Rooted Views (V1)

## Summary

This document describes how to add **CRM Entity-rooted graph views** to entity-map. Today, entity-map builds graphs starting from a **firm**. We want to add the ability to build graphs starting from a **CRM Entity** to support **GP Member portfolio views**.

**The driving use case:** GP Members need to see their investments across funds. They want to answer:
- "What funds am I invested in?"
- "What's my exposure in each fund?"

**V1 Scope:** Build a minimal, working CRM Entity view that reuses existing infrastructure. Defer abstractions and extensibility to future iterations.

### Assumptions

| Assumption | Value | Rationale |
|------------|-------|-----------|
| Typical GP Member fund count | 3-5 funds | Bounds performance requirements |
| 95th percentile fund count | ~15 funds | Upper bound for stress testing |
| Cross-firm positions | Possible but rare | Most GP Members operate within 1-2 firms |
| CRM Entity data source | `Partner.entity_id` only | We don't fetch CRM Entity names—that data lives elsewhere |
| CRM Entity ID in URLs | `portfolio_id` = CRM Entity UUID | Existing carta_web convention; reuse this pattern |

### What's IN V1

- **GP Entity → Main Fund traversal**: We follow the management relationship to show the funds GP Members care about
- **Connected fund traversal**: Using existing `filtered_to_fund_subgraph()`, we show feeders and related funds
- **Multi-firm support**: If a GP Member has positions across firms, we build and merge subgraphs per firm

### What's NOT in V1

- **Portfolio company nodes**: Deferred. The graph shows funds and their relationships, not underlying investments.
- **Generic root registry**: Deferred. We're adding CRM Entity support directly, not building a plugin system.
- **New abstract interfaces**: Deferred. We'll reuse `InvestedInRelationshipGraph` rather than creating a new `RelationshipGraph` abstraction.
- **Cross-firm aggregation**: V1 shows only funds where user has GP access.

---

## Terminology

| Term | Definition |
|------|------------|
| **GP Member** | The human who manages funds and receives carried interest |
| **GP Entity** | Legal structure through which GP Members receive economics |
| **Fund** | Investment vehicle that pools capital from LPs and invests in assets |
| **Partner (database)** | A single investment position in a single fund—**not a person**. One investor in three funds = three Partner records |
| **CRM Entity** | Carta's representation of a legal entity (person, trust, LLC, etc.). Partner records link to CRM Entities via `entity_id` |

**Key insight:** The "Partner" naming is confusing—it's a position record, not a person. When Jane Smith invests in Fund A, Fund B, and Fund C, she has *three* Partner records.

---

## Current Architecture

### Backend: How Graphs Are Built

The backend builds graphs through a three-stage pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: ORCHESTRATION                                                     │
│  EntityMapService (fund_admin/entity_map/entity_map_service.py)             │
│                                                                             │
│  Key Methods:                                                               │
│  • get_firm_tree(firm_id) → Graph of all funds in a firm                    │
│  • get_fund_and_related_funds_tree(firm_id, fund_id) → Graph for one fund   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: RELATIONSHIP DISCOVERY                                            │
│  InvestedInRelationshipGraphBuilder                                         │
│  (fund_admin/entity_map/invested_in_relationship_graph.py)                  │
│                                                                             │
│  Answers: "Who is connected to whom?"                                       │
│  Output: InvestedInRelationshipGraph with fund-to-fund relationships        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: GRAPH CONSTRUCTION                                                │
│  GraphBuilder (fund_admin/entity_map/graph_builder.py)                      │
│                                                                             │
│  Transforms relationships into Node/Edge objects with metrics.              │
│  Output: Graph(nodes=[], edges=[])                                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Current API Endpoints

| Endpoint | What it does |
|----------|--------------|
| `GET /firm/{uuid}/entity-atlas/` | Returns the full graph for a firm |
| `GET /fund/{uuid}/entity-atlas/v2` | Returns graph centered on a specific fund |

### Key Domain Objects

**Use `fund_admin.capital_account.domain.PartnerDomain`** for Partner lookups:

```python
@dataclass
class PartnerDomain:
    id: int
    uuid: UUID
    name: str
    fund_id: int
    partner_type: str
    entity_id: str | None  # Links to CRM Entity
    # ... other fields
```

---

## V1 Implementation

### Key Insight: GP Members Connect Through GP Entities

GP Members typically don't have Partner records directly in main funds. Their economic interest flows through **GP Entity** structures:

```
Jane Smith (CRM Entity)
       │
       │ Partner record in
       ▼
Krakatoa IV GP (GP Entity)        ← Jane's Partner is HERE
       │
       │ manages (via ManagingEntityLinksService)
       ▼
Krakatoa IV LP (Main Fund)        ← But Jane wants to SEE this
       │
       ├──► Feeder funds invested in it
       └──► Portfolio companies
```

**Implication:** We can't just look up Partner records and return those funds. We need to:
1. Find Partner records → get initial fund IDs (may be GP Entities)
2. For GP Entity funds, find the **main funds they manage**
3. Use existing graph traversal to find connected entities (feeders, etc.)

### Approach

Reuse existing infrastructure:
- `ManagingEntityLinksService.get_funds_from_managing_entity()` to traverse GP Entity → Main Fund
- `InvestedInRelationshipGraphBuilder.build_for_firm()` to build firm graphs
- `filtered_to_fund_subgraph()` to find connected entities

### New Components

#### 1. CRM Entity Graph Builder Method

Add to `InvestedInRelationshipGraphBuilder`:

```python
# fund_admin/entity_map/invested_in_relationship_graph.py

class InvestedInRelationshipGraphBuilder:
    # ... existing methods ...

    def build_for_crm_entity(
        self,
        crm_entity_id: UUID,
        accessible_firm_ids: list[int],
        managing_entity_links_service: ManagingEntityLinksService | None = None,
    ) -> InvestedInRelationshipGraph:
        """
        Build a relationship graph from a CRM Entity's perspective.

        This handles the GP Entity → Main Fund traversal that's required
        because GP Members typically have Partner records in GP Entities,
        not directly in the main funds they want to see.
        """
        managing_entity_links_service = (
            managing_entity_links_service or ManagingEntityLinksService()
        )

        # Step 1: Find all Partner records for this CRM Entity
        partner_records = self._partner_service.list_domain_objects(
            crm_entity_ids=[str(crm_entity_id)],
        )
        if not partner_records:
            return InvestedInRelationshipGraph.empty()

        # Step 2: Get funds and identify GP Entities vs regular funds
        fund_ids = [p.fund_id for p in partner_records]
        funds = self._fund_service.get_funds_by_id(fund_ids=fund_ids)

        # Filter to accessible firms
        accessible_funds = {
            fid: fund for fid, fund in funds.items()
            if fund.firm_id in accessible_firm_ids
        }
        if not accessible_funds:
            return InvestedInRelationshipGraph.empty()

        # Step 3: For GP Entity funds, find the main funds they manage
        main_fund_ids: set[int] = set()
        for fund_id, fund in accessible_funds.items():
            if fund.entity_type == EntityTypes.GP_ENTITY:
                # GP Entity → find managed main funds
                managed_fund_ids = managing_entity_links_service.get_funds_from_managing_entity(
                    firm_id=fund.firm_id,
                    managing_entity_uuid=fund.uuid,
                )
                main_fund_ids.update(managed_fund_ids)
            else:
                # Regular fund → include directly
                main_fund_ids.add(fund_id)

        if not main_fund_ids:
            return InvestedInRelationshipGraph.empty()

        # Step 4: Build firm graphs and filter to connected subgraphs
        # Group main funds by firm to minimize graph builds
        funds_by_firm: dict[int, list[int]] = defaultdict(list)
        main_funds = self._fund_service.get_funds_by_id(fund_ids=list(main_fund_ids))
        for fund_id, fund in main_funds.items():
            funds_by_firm[fund.firm_id].append(fund_id)

        # Build and merge subgraphs for each firm
        merged_graph = InvestedInRelationshipGraph.empty()
        for firm_id, fund_ids_in_firm in funds_by_firm.items():
            firm_graph = self.build_for_firm(firm_id=firm_id)
            for fund_id in fund_ids_in_firm:
                subgraph = firm_graph.filtered_to_fund_subgraph(fund_id=fund_id)
                merged_graph = merged_graph.merge(subgraph)

        return merged_graph
```

> **Note:** This assumes `InvestedInRelationshipGraph.merge()` and `.empty()` methods exist or will be added. These are straightforward to implement—merge combines two graphs, empty returns an empty graph.

#### 2. EntityMapService Method

Add to `EntityMapService`:

```python
# fund_admin/entity_map/entity_map_service.py

class EntityMapService:
    # ... existing methods ...

    def get_crm_entity_tree(
        self,
        crm_entity_id: UUID,
        accessible_firm_ids: list[int],
        end_date: date | None = None,
    ) -> Graph:
        """
        Get a graph of all funds a CRM Entity is invested in.

        Args:
            crm_entity_id: The CRM Entity UUID
            accessible_firm_ids: Firms where the requesting user has GP access
            end_date: Point-in-time for metrics (None = latest)

        Returns:
            Graph with fund nodes for each investment position
        """
        relationship_graph = self._relationship_graph_builder.build_for_crm_entity(
            crm_entity_id=crm_entity_id,
            accessible_firm_ids=accessible_firm_ids,
        )

        return self._graph_builder.build_graph(
            invested_in_relationship_graph=relationship_graph,
            end_date=end_date,
        )
```

#### 3. API Endpoint

```python
# fund_admin/entity_map/views/entity_map_crm_entity_view.py

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from rest_framework.request import Request
from rest_framework.views import APIView

from fund_admin.common.routers import use_database_connection
from fund_admin.common.view.exposed_decorators.dc_exposed import dc_exposed
from fund_admin.entity_map.domain import Graph
from fund_admin.entity_map.entity_map_service import EntityMapService
from fund_admin.http.permissions import IsStaff
from fund_admin.permissions.gp_permissions.permission_classes import (
    HasViewInvestmentsPermission,
    HasViewPartnersPermission,
)


@dataclass
class EntityMapCrmEntityViewQueryParams:
    end_date: date | None = None
    lightweight: bool = False


class EntityMapCrmEntityView(APIView):
    """
    Returns an entity map graph rooted on a CRM Entity.

    URL: GET /crm-entity/{crm_entity_uuid}/entity-atlas/

    Permissions:
    - User must have GP access to at least one firm
    - Only shows funds in firms where user has GP access
    - User must be linked to the requested CRM Entity (enforced in view)
    """

    permission_classes = [
        HasViewInvestmentsPermission & HasViewPartnersPermission | IsStaff
    ]

    @dc_exposed(query_params=EntityMapCrmEntityViewQueryParamsSerializer)
    @use_database_connection.ro()
    def get(
        self,
        request: Request,
        query_params: EntityMapCrmEntityViewQueryParams,
        crm_entity_uuid: UUID,
    ) -> Graph:
        # Validate user can view this CRM Entity (see Permissions section)
        self._validate_crm_entity_access(request.user, crm_entity_uuid)

        # Get firms where user has GP access
        accessible_firm_ids = self._get_accessible_firm_ids(request.user)

        service = EntityMapService.factory(
            lightweight=query_params.lightweight,
        )

        return service.get_crm_entity_tree(
            crm_entity_id=crm_entity_uuid,
            accessible_firm_ids=accessible_firm_ids,
            end_date=query_params.end_date,
        )

    def _validate_crm_entity_access(self, user, crm_entity_uuid: UUID) -> None:
        """
        Validate that the user can view this CRM Entity.

        V1 rule: User can only view CRM Entities they are linked to.
        """
        user_crm_entity_ids = self._get_user_crm_entity_ids(user)
        if crm_entity_uuid not in user_crm_entity_ids:
            raise PermissionDenied("You don't have access to this entity")

    def _get_user_crm_entity_ids(self, user) -> set[UUID]:
        """Get CRM Entity UUIDs linked to this user."""
        # Implementation depends on how user-to-CRM-Entity linking works
        # This may involve looking up the user's organization_id
        # and finding CRM Entities with matching organization_id
        ...

    def _get_accessible_firm_ids(self, user) -> list[int]:
        """Get firm IDs where user has GP access."""
        # Use existing permission infrastructure
        from fund_admin.permissions.services.permission_service import PermissionService
        return PermissionService().get_accessible_firm_ids(user)
```

#### 4. URL Configuration

```python
# fund_admin/entity_map/urls.py

urlpatterns = [
    # ... existing patterns ...

    # New CRM Entity endpoint
    path(
        "crm-entity/<uuid:crm_entity_uuid>/entity-atlas/",
        EntityMapCrmEntityView.as_view(),
        name="entity-map-crm-entity",
    ),
]
```

---

## Permissions

### The Challenge

CRM Entity views cross firm boundaries—a CRM Entity may have positions in funds across multiple firms. Our current permission model is firm-scoped.

### V1 Approach: Conservative and Simple

**Two rules:**
1. **Identity check:** User can only view CRM Entities they are linked to
2. **Firm filter:** Only show funds in firms where user has GP access

> **Implementation note:** The existing `CanEditPortfolio` permission class (`firm_permissions.py:280-312`) already validates user access to a CRM Entity via `portfolio_id`. Consider reusing this pattern.

```python
class CrmEntityPermissionHelper:
    """
    V1 permission logic for CRM Entity views.

    This is conservative—users may not see all their investments if they
    lack GP access to some firms. We can relax this in future iterations.
    """

    def __init__(self, permission_service: PermissionService | None = None):
        self._permission_service = permission_service or PermissionService()

    def validate_access(self, user, crm_entity_uuid: UUID) -> None:
        """Raise PermissionDenied if user cannot view this CRM Entity."""
        if not self._user_owns_crm_entity(user, crm_entity_uuid):
            raise PermissionDenied("You don't have access to this entity")

    def get_accessible_firm_ids(self, user) -> list[int]:
        """
        Get firm IDs where user has GP-level access.

        Uses existing permission infrastructure—we're not inventing new
        permission types for V1.
        """
        # This leverages existing GP permission checks
        return self._permission_service.get_gp_accessible_firm_ids(user.id)

    def _user_owns_crm_entity(self, user, crm_entity_uuid: UUID) -> bool:
        """
        Check if user is linked to this CRM Entity.

        The linking is typically via organization_id matching.
        """
        # Get user's linked CRM Entity IDs from their profile/organization
        user_entity_ids = self._get_user_linked_crm_entities(user)
        return crm_entity_uuid in user_entity_ids

    def _get_user_linked_crm_entities(self, user) -> set[UUID]:
        """
        Get CRM Entity UUIDs that belong to this user.

        Implementation note: This likely involves looking up the user's
        organization in CRM and finding entities with matching organization_id.
        """
        # TODO: Implement based on how user-CRM linking works in your system
        ...
```

### What This Means for Users

| Scenario | Result |
|----------|--------|
| User views their own CRM Entity | Shows funds in firms where they have GP access |
| User views someone else's CRM Entity | 403 Forbidden |
| User has positions in firm without GP access | Those funds are hidden (conservative) |

### Future Iteration

A future version could introduce:
- "Investor view" permission allowing read-only access to funds you're invested in
- Partner-level permissions (see your own position data, not others')

---

## Frontend Integration

The frontend integration is well-understood and follows existing patterns.

### Data Flow

```
Partner Dashboard
    │
    │ init API returns crmEntityId for current user
    │
    ▼
VisualAccountingWrapper.tsx
    │
    │ Passes crmEntityId to Entity Map FARS Component
    │ (firmUuid becomes optional, not passed for CRM Entity views)
    │
    ▼
Entry.tsx (Entity Map)
    │
    │ Props: { crmEntityId: UUID } (no firmUuid)
    │
    ▼
EntityMapContainer.tsx
    │
    │ Detects crmEntityId, renders CrmEntityRootedView
    │
    ▼
CrmEntityRootedView.tsx
    │
    │ Fetches: GET /crm-entity/{uuid}/entity-atlas/
    │
    ▼
FundEntityMap.tsx (reused)
```

### Entry Component Changes

```tsx
// Entry.tsx

type Props = {
    farsMetadata?: FARSMetadata;

    // For CRM Entity views (new)
    crmEntityId?: UuidType;

    // For firm views (existing, now optional)
    firmUuid?: UuidType;

    organizationPk?: string;
};

export const Entry = ({
    farsMetadata,
    crmEntityId,
    firmUuid,
    organizationPk,
}: Props) => {
    // Determine view type based on which ID was provided
    const viewType = crmEntityId ? 'crm_entity' : 'firm';
    const rootId = crmEntityId ?? firmUuid;

    return (
        <EntityMapContextProvider
            viewType={viewType}
            rootId={rootId ?? ''}
            organizationPk={organizationPk ?? ''}
        >
            <MainView farsMetadata={farsMetadata} />
        </EntityMapContextProvider>
    );
};
```

---

## Implementation Plan

### Phase 1: Backend

1. Add `build_for_crm_entity()` to `InvestedInRelationshipGraphBuilder`
2. Add `get_crm_entity_tree()` to `EntityMapService`
3. Create `EntityMapCrmEntityView` with permission checks
4. Add URL routing
5. Write unit tests with factories

### Phase 2: Permissions Integration

1. Implement `_get_user_linked_crm_entities()` based on existing user-CRM linking
2. Implement `_get_accessible_firm_ids()` using existing `PermissionService`
3. Write permission tests

### Phase 3: Frontend

1. Update `Entry.tsx` to accept `crmEntityId` prop
2. Create `CrmEntityRootedView` component
3. Update `EntityMapContainer` routing
4. Update Partner Dashboard to pass `crmEntityId`

### Phase 4: Testing & Polish

1. Integration tests
2. Manual QA with test accounts
3. Error handling and edge cases

---

## Performance Constraints

All database queries **must** follow these rules:

1. **Bulk queries only**: Fetch entities using SQL `IN` clauses, never per-entity lookups
2. **No loops with DB calls**: All data fetching happens upfront
3. **Prefetch related data**: Load Partner records, funds, and metrics in batches

```python
# BAD: N+1 query pattern
for fund_id in fund_ids:
    partners = Partner.objects.filter(fund_id=fund_id)  # Query per fund!

# GOOD: Bulk fetch
partners = Partner.objects.filter(fund_id__in=fund_ids)
partners_by_fund = group_by(partners, key=lambda p: p.fund_id)
```

---

## Open Questions

1. **User-to-CRM-Entity linking:** How exactly do we determine which CRM Entities a user "owns"? Is this via `organization_id` matching?

2. **Legacy Partners:** Some Partners created before CRM entity linking (or via manual processes) have `entity_id=NULL`. These won't appear in CRM Entity-rooted views. Is this acceptable, or do we need a backfill?

3. **InvestedInRelationshipGraph helpers:** The implementation assumes `merge()` and `empty()` methods on `InvestedInRelationshipGraph`. These don't exist today—should we add them, or restructure to avoid needing them?

---

## Future Development

These items are explicitly **out of scope** for V1 but worth considering for future iterations:

### Portfolio Company Nodes

V1 shows funds and their relationships but not the underlying portfolio companies. Adding portfolio company nodes would require:
- Integration with portfolio data sources
- Additional node types and rendering
- Performance consideration for funds with many investments

### Generic Root Type Registry

A plugin system for adding new root types without modifying core code:

```python
class RootRegistry:
    _registry: dict[RootType, RootConfig] = {}

    @classmethod
    def register(cls, root_type: RootType, config: RootConfig) -> None:
        cls._registry[root_type] = config
```

This becomes valuable if we add Portfolio Company views, Fund Family views, etc.

### Abstract RelationshipGraph

A root-agnostic representation that all builders produce:

```python
@dataclass
class RelationshipGraph:
    root_id: UUID
    root_type: RootType
    entity_ids: set[int]
    relationships: dict[tuple[int, int], RelationshipMetadata]
```

Currently, we reuse `InvestedInRelationshipGraph` which is simpler but less flexible.

### Partner Interest Groups (PIGs)

When PIGs ship, they could become another root type—showing all investments across multiple CRM Entities that represent the same economic interest.

### Cross-Firm Visibility

Allow users to see funds they're invested in even without GP access (read-only "investor view"). Requires new permission type.

### Post-Filter Permissions Model

V1 filters by accessible firm IDs *before* building the graph. A future architecture could:

1. Build the subgraph first (agnostic to permissions)
2. Check permissions on each entity in the subgraph
3. Filter out inaccessible entities

This enables finer-grained, per-entity permission checks and centralizes permission logic in one place. The V1 approach is a valid subset—filtering early is functionally equivalent for our current firm-scoped permissions.

### GP Entity Carry Data

Integrate with GP Entity app's carry calculation service (via gRPC) to show carry exposure in node metadata.

---
date: 2026-02-02
description: Status update for CRM Entity-rooted graph views after addressing PR feedback
repository: fund-admin
tags: [entity-map, crm-entity, status-update, pr-feedback, gpe-215]
---

# CRM Entity Graph: Status Update

| | |
|---|---|
| **Jira** | [GPE-215](https://carta1.atlassian.net/browse/GPE-215) |
| **PR** | [#49859](https://github.com/carta/fund-admin/pull/49859) |
| **Branch** | `gpe-215.cartian.crm_entity_graph` |
| **Date** | February 2, 2026 |

---

## Executive Summary

This week we addressed PR feedback from code review, improving test quality, fixing performance issues, and aligning with domain boundary conventions. The PR is ready for re-review with all feedback items resolved.

**Key outcomes:**
- Replaced over-mocked unit tests with real backend integration tests
- Fixed N+1 query in GP entity traversal
- Removed unnecessary parameters and simplified the implementation
- Used proper service abstractions instead of direct model access

---

## Recent History

### Week of January 26-29

**Initial implementation completed:**
- Phase 1: CRM entity-rooted graph views (`build_for_crm_entity()`)
- Phase 2: Firm membership and IDOR validation
- Phase 3: Frontend prep (`crmEntityId` prop)
- Manual API testing: 9 test cases passing

**Documents produced:**
- `20260126-tech-design.md` — Original architecture design
- `20260128-crm-entity-permissions-design.md` — Permission model rationale
- `20260129-crm-entity-api-test-results.md` — Manual API testing results
- `20260128-session-summary-crm-entity-views.md` — Implementation summary

### Week of January 30 - February 2

**PR review feedback received** from @galonsky on January 30. Seven substantive issues identified:

| Issue | Category | Resolution |
|-------|----------|------------|
| Over-mocked unit tests | Testing | Replaced with backend integration tests |
| N+1 query in GP entity traversal | Performance | Bulk query with service method |
| Direct Django model queries | Architecture | Use `CRMEntityService` |
| Unnecessary `include_gp_entity_funds_in_edges` param | Complexity | Removed; GP entities handled by GraphBuilder |
| `HasAllViewPermissions` needed | Security | Updated permission class |
| Conditional assertions in tests | Testing | Made deterministic |
| `poetry.lock` changes | CI | Reverted to master version |

---

## Changes Made This Week

### 1. Test Quality Improvements

**Commit:** `0321666a5fc` — Replace over-mocked unit tests with backend integration tests

The original unit tests mocked everything, providing little value. Replaced with 10 backend integration tests using real database fixtures:

```
tests/backend/fund_admin/entity_map/test_entity_map_service.py (NEW)
├── test_get_crm_entity_tree_basic
├── test_get_crm_entity_tree_with_gp_entity
├── test_get_crm_entity_tree_multi_fund_investor
├── test_get_crm_entity_tree_filters_by_firm
├── test_get_crm_entity_tree_with_end_date
├── test_get_crm_entity_tree_feeder_master_relationship
├── test_get_crm_entity_tree_balance_sheet_metrics
├── test_get_crm_entity_tree_partner_metrics
├── test_get_crm_entity_tree_empty_result
└── test_get_crm_entity_tree_lightweight
```

**Commit:** `4e869eb7bb2` — Fix conditional assertions

Removed Claude-generated conditional assertions that were hiding test failures:

```python
# Before (bad)
if fund_node:
    assert fund_node.name == expected_name

# After (good)
fund_node = next(n for n in nodes if n.type == "fund")
assert fund_node.name == expected_name
```

### 2. Performance Fix

**Commit:** `62a477f2a73` — Fix N+1 query in GP entity traversal

The original implementation queried GP entities one at a time inside a loop:

```python
# Before (N+1)
for fund_id, fund in gp_entity_funds.items():
    gp_entity_uuid = managing_entity_links_service.get_gp_entity_uuid_from_fund(fund_id)
```

Fixed by using existing bulk service method:

```python
# After (bulk)
gp_entity_uuids = managing_entity_links_service.get_managing_entity_uuids_from_funds(
    fund_ids=list(gp_entity_funds.keys())
)
```

### 3. Architecture Alignment

**Commit:** `4fe8bd60056` — Use `CRMEntityService` instead of direct model access

Respects domain boundaries by using the CRM entity service:

```python
# Before (bad - cross-domain model access)
from fund_admin.crm.models import CRMEntity
crm_entity = CRMEntity.objects.get(uuid=crm_entity_uuid)

# After (good - service abstraction)
from fund_admin.crm.services import CRMEntityService
crm_entity = CRMEntityService().get_by_uuid(crm_entity_uuid)
```

**Commit:** `0cb636ee9d6` — Use existing service method for GP entity lookup

Removed custom `get_gp_entity_uuid_from_fund()` method and used existing bulk method with local mapping reversal. This also cleaned up 78 lines of unnecessary test code.

### 4. Simplification

**Commit:** `0f68147b2e8` — Remove `include_gp_entity_funds_in_edges` parameter

The parameter was unnecessary because GP entity nodes are created in `GraphBuilder.build_graph()`, not in the relationship graph builder. The edge creation logic already handled this case correctly.

**Files changed:**
- `entity_map_service.py` — Removed parameter passing
- `graph_builder.py` — Removed parameter and conditional logic
- `invested_in_relationship_graph.py` — Added clarifying comment

---

## Current Status

### PR State

| Aspect | Status |
|--------|--------|
| **Review comments** | 12/14 resolved |
| **CI** | Needs rebase on master |
| **Tests** | All passing locally |
| **Requested reviewers** | @galonsky, vc-prodsec, fund-admin-general-ledger-stewards |

### Unresolved Comments

Two comments remain unresolved but are informational (self-authored notes about IDOR prevention and the GP Entity traversal logic), not requiring code changes.

### What's Complete

| Component | Status | Notes |
|-----------|--------|-------|
| Backend API | Done | `GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/` |
| IDOR protection | Done | Validates CRM entity belongs to firm |
| Graph building | Done | `build_for_crm_entity()` with GP Entity traversal |
| Backend integration tests | Done | 10 tests with real fixtures |
| Unit tests | Done | View and service layer coverage |
| Frontend wrapper | Done | `crmEntityId` prop pass-through |

### What's Pending

| Component | Status | Blocker |
|-----------|--------|---------|
| PR merge | Blocked | Awaiting re-review |
| Entity-map federated module | Ready | Separate repo PR needed |
| Feature flag | Not started | Depends on merge |
| End-to-end testing | Not started | Depends on feature flag |

---

## Short-Term Goals

### 1. Multi-Firm Support

**Current state:** The implementation already supports multi-firm scenarios. When a CRM entity has Partner records across multiple firms, the graph builder:
1. Groups main funds by firm
2. Builds subgraphs per firm
3. Merges into a unified result

**What's needed:**
- End-to-end testing with multi-firm test data
- Verify permission filtering works correctly across firms

**Code location:** `invested_in_relationship_graph.py:424-448`

```python
# Build and merge subgraphs for each firm
merged_graph = InvestedInRelationshipGraph.empty()
for firm_id, fund_ids_in_firm in funds_by_firm.items():
    firm_graph = self.build_for_firm(firm_id=firm_id)
    for fund_id in fund_ids_in_firm:
        subgraph = firm_graph.filtered_to_fund_subgraph(fund_id=fund_id)
        merged_graph = merged_graph.merge(subgraph)
```

### 2. Fine-Grained Permissions

**Current state:** Uses `HasAllViewPermissions` for firm-level gating. This is a conservative approach that requires full GP access to the firm.

**Goal:** Implement fund-level permission checks so users see only the funds they have access to within the graph.

**Design options:**

| Approach | Pros | Cons |
|----------|------|------|
| **Pre-filter** | Simple, fewer nodes to process | May miss connected funds |
| **Post-filter** | Complete graph, then prune | More processing, cleaner separation |
| **Hybrid** | Filter early, validate late | Complex but optimal |

**Recommended approach:** Post-filter model

1. Build the complete subgraph (current behavior)
2. Apply `HasViewInvestmentsPermission` per fund node
3. Remove inaccessible nodes and their edges

**Implementation sketch:**

```python
# In EntityMapService.get_crm_entity_tree()
graph = self._graph_builder.build_graph(relationship_graph)

# Filter nodes by permission
accessible_fund_ids = permission_service.get_accessible_fund_ids(user)
filtered_nodes = [
    n for n in graph.nodes
    if n.type != "fund" or n.fund_id in accessible_fund_ids
]

# Remove orphaned edges
valid_node_ids = {n.id for n in filtered_nodes}
filtered_edges = [
    e for e in graph.edges
    if e.from_node_id in valid_node_ids and e.to_node_id in valid_node_ids
]

return Graph(nodes=filtered_nodes, edges=filtered_edges)
```

**Files to modify:**
- `fund_admin/entity_map/entity_map_service.py`
- `fund_admin/entity_map/views/entity_map_crm_entity_view.py`

### 3. Frontend Integration

**Sequence:**
1. Merge fund-admin PR #49859
2. Create carta-frontend-platform PR with `CrmEntityView` component
3. Add feature flag `GPE_215_CRM_ENTITY_MAP`
4. Wire up Partner Dashboard routing

**Entity-map federated module changes (prepared but not yet PR'd):**

| File | Change |
|------|--------|
| `Entry.tsx` | Accept `crmEntityId` prop |
| `FundAdminContext.tsx` | Add to context |
| `use-get-crm-entity-map.ts` | New API hook |
| `CrmEntityView/CrmEntityView.tsx` | New view component |
| `EntityMapContainer.tsx` | Route to CrmEntityView |

---

## Immediate Next Steps

1. **Rebase on master** — Resolve `poetry.lock` conflicts
2. **Request re-review** — Ping @galonsky for approval
3. **Create frontend PR** — carta-frontend-platform changes
4. **Plan fine-grained permissions** — Technical design for post-filter approach

---

## Reference

### Key Files

| File | Purpose |
|------|---------|
| `invested_in_relationship_graph.py:343-448` | `build_for_crm_entity()` implementation |
| `entity_map_service.py` | Service orchestration |
| `entity_map_crm_entity_view.py` | API view with IDOR validation |
| `tests/backend/.../test_entity_map_service.py` | Integration tests |

### Related Documents

| Document | Purpose |
|----------|---------|
| `20260126-tech-design.md` | Original architecture |
| `20260129-crm-entity-api-test-results.md` | Manual API testing |
| `20260128-crm-entity-permissions-design.md` | Permission model |

### Key UUIDs (Demo Data)

| Entity | UUID |
|--------|------|
| Krakatoa Ventures (firm) | `186fb573-a22d-4c82-8ad3-3186f9095a41` |
| Fund IV GP (primary test) | `4a55f602-375c-4211-a579-09075405de08` |
| Fund III GP | `e96c498b-e329-4e5e-b6b9-eae44e30f70f` |

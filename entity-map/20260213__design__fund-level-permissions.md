---
date: 2026-02-13
description: Design for fund-level permission filtering in the CRM entity (GP portfolio) entity map view
repository: fund-admin
tags: [entity-map, permissions, gp-embedded, design, security]
---

# Fund-Level Permissions for GP Entity Map

## Problem

The CRM entity view (`EntityMapCrmEntityView`) uses `HasAllViewPermissions | IsStaff` as its permission gate. This requires all 5 view permissions on ALL funds in the firm. Most GPs fail this check — they're missing `view_general_ledger` or don't have permissions on every fund. Real GPs hitting the Partner Dashboard entity map get a 403.

Relaxing the gate without adding filtering would leak data — a GP with access to Fund A but not Fund B would see Fund B's structure and financials.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Permission level to gate fund visibility | `view_investments` | The entity map shows investment structure — `view_investments` is the natural fit. Single-permission check, most permissive reasonable gate. |
| Pruning behavior | Hard prune | If a fund is filtered out, its entire subtree disappears. No placeholder nodes, no disconnected orphans. No information leakage about unpermitted fund structure. |
| Per-fund filtering through investment chains | Yes, fund-by-fund | Even if Fund B is reachable from permitted Fund A (A invests in B), Fund B requires its own `view_investments` permission. This matches how permissions are modeled in fund admin. |
| Root node metrics | Aggregate visible funds only | Individual portfolio root metrics sum only funds the GP can see. Must match partner_portfolio summary/entity-list API numbers. |
| Filter insertion point | `InvestedInRelationshipGraph` | Filter the firm graph before subgraph traversal. GraphBuilder and NodeFetcherService never see unpermitted funds. Permissions are a topology constraint. |
| User context passing | Permitted fund UUID set | View queries PermissionService, passes `set[UUID]` through the pipeline. Builder doesn't know about users or permissions — just filters by a set. `None` = no filtering (staff). |
| View scope | CRM entity view only | Firm and fund views keep their existing all-or-nothing checks. Those are admin/CFO views where partial visibility is a different UX question. |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  VIEW LAYER                                                  │
│                                                              │
│  permission_classes = [IsFirmMember | IsStaff]               │
│                                                              │
│  1. Validate CRM entity belongs to firm (IDOR prevention)    │
│  2. Query PermissionService for permitted fund UUIDs         │
│     (view_investments on firm)                               │
│  3. Pass set[UUID] | None to service layer                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SERVICE LAYER (EntityMapService)                            │
│                                                              │
│  Pass-through: routes permitted_fund_uuids to builder        │
│  No permission logic here                                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  RELATIONSHIP GRAPH BUILDER                                  │
│                                                              │
│  1. Build firm graph (all funds)                             │
│  2. NEW: firm_graph.filtered_to_permitted_funds(uuids)       │
│     - Remove unpermitted funds from fund_ids_to_fund         │
│     - Prune edges involving unpermitted funds                │
│     - Remove partner pairs for pruned edges                  │
│  3. BFS subgraph traversal from investor's fund entry points │
│     (naturally stops at permission boundaries)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  GRAPH BUILDER + NODE FETCHER SERVICE                        │
│                                                              │
│  Unchanged — receives pre-filtered relationship graph        │
│  Only fetches data for permitted funds                       │
│                                                              │
│  Exception: IndividualPortfolioNodeFetcher filters its       │
│  partner list by permitted_fund_uuids before aggregating     │
│  root node metrics (via NodeFetchRequest)                    │
└─────────────────────────────────────────────────────────────┘
```

## Changes by File

### `entity_map/views/entity_map_crm_entity_view.py`
- Replace `HasAllViewPermissions` with `IsFirmMember` in permission_classes
- Add `_get_permitted_fund_uuids(user, firm_uuid) -> set[UUID] | None`
- Pass permitted set to `entity_map_service.get_crm_entity_tree()`

### `entity_map/entity_map_service.py`
- Add `permitted_fund_uuids: set[UUID] | None = None` param to `get_crm_entity_tree()`
- Pass through to `build_for_crm_entity()`

### `entity_map/invested_in_relationship_graph.py`
- Add `filtered_to_permitted_funds(permitted_fund_uuids: set[UUID]) -> InvestedInRelationshipGraph` method on `InvestedInRelationshipGraph`
- Add `permitted_fund_uuids: set[UUID] | None = None` param to `build_for_crm_entity()`
- Call `firm_graph.filtered_to_permitted_funds()` after building firm graph, before subgraph traversal

### `entity_map/services/domain.py`
- Add `permitted_fund_uuids: set[UUID] | None = None` to `NodeFetchRequest`

### `entity_map/services/node_fetcher_service.py`
- `IndividualPortfolioNodeFetcher.fetch()`: filter partner list by `request.permitted_fund_uuids` before metric aggregation

### `entity_map/graph_builder.py`
- Pass `permitted_fund_uuids` through to `NodeFetchRequest` in `build_graph()`
- Update `create_for_crm_entity()` or `build_graph()` signature to accept and forward the set

## Test Strategy

### Integration tests: `build_for_crm_entity()` with `permitted_fund_uuids`

Real DB, real factories. Extend existing builder tests.

- GP with full access — graph matches current behavior
- GP with partial access — only permitted fund subgraphs appear
- GP with no access to any invested fund — empty graph
- Staff (`None`) — full graph, unchanged
- GP Entity traversal with partial permissions — permitted main fund appears, unpermitted sibling pruned
- Chain pruning — Fund A → Fund B → Fund C, only A permitted: B and C pruned

### Integration tests: `EntityMapCrmEntityView`

Real permission setup via factories.

- Firm member with partial fund access — 200 with filtered graph, root metrics reflect visible funds only
- Staff user — full graph, no filtering
- IDOR prevention unchanged — CRM entity from different firm still returns 403

### What doesn't need new tests

- `GraphBuilder` — inputs are pre-filtered, no new code paths
- Other node fetchers — only receive identifiers for permitted funds
- Firm/fund views — untouched

## Performance

The permission query (`get_funds_user_has_gp_permission_for`) is 2 indexed DB lookups — the same pattern every fund-level view already runs. Returns a queryset; we call `.values_list('uuid', flat=True)` for a set of ~5-20 UUIDs.

Filtering the firm graph is dict comprehensions over the `InvestedInRelationshipGraph` dataclass (typically <50 funds). Negligible.

The real performance win: filtering before node fetching means we never query partner metadata, balance sheets, or issuer metrics for unpermitted funds. Fewer funds in the graph = fewer DB round trips in the expensive stage.

## Security Notes

- The permission relaxation (`HasAllViewPermissions` → `IsFirmMember`) MUST ship with the filtering. Without filtering, `IsFirmMember` alone would expose all funds in the firm to any firm member.
- IDOR validation (`_validate_crm_entity_in_firm`) is unchanged — still prevents cross-firm access.
- `None` means staff/no-filter, `set()` means "user has no fund permissions" → empty graph. These are distinct and both handled correctly.

---
date: 2026-02-25
description: Implementation plan for restructuring CRM entity graph building to work root-outward instead of leaf-inward
repository: fund-admin
tags: [entity-map, plan, architecture, permissions, graph-builder]
---

# Graph Building Architecture Fix (Option B)

## Problem statement

The entity map graph for CRM entity (portfolio) views is built backwards. The current code starts from LP funds (the outermost layer), filters there, and tries to reverse-discover GP entities. The correct approach is to start from the CRM entity, expand outward through GP entities, then to LP funds, checking permissions at each layer.

See `20260225__investigation__graph-building-inversion-bug.md` for the full root cause analysis.

## Design principles

1. **Build from root outward.** For portfolio views, the root is the CRM entity. The first expansion is to directly associated funds (typically GP entities). The next expansion is to funds those entities manage. Each layer is permission-checked before the next expansion begins.

2. **Traversal pattern is configurable.** The firm view needs a different traversal: start from all funds in the firm, exclude GP entities from the main graph, then decorate with GP entity nodes. The architecture must support both patterns (and potentially more) without conditional logic scattered through shared code.

3. **Don't break the firm view.** The firm-level entity map, fund-level views, and investment relationship views must continue to work exactly as they do today. Changes to shared machinery must be additive — new parameters and graph layers, not changed defaults.

4. **Permission filtering is layer-aware.** Instead of a single `filtered_to_permitted_funds()` pass on the entire graph, permissions are checked per layer. GP entity nodes are filtered by GP fund permissions. LP fund nodes are filtered by LP fund permissions. The individual_portfolio root always appears if any child node survives filtering.

## Scope

### Branch
New branch based on master: `gpe-299.cartian.graph_building_root_outward` (or similar).

### This branch should also include
- The `view_investments`-only permission change (currently on the Option A branch). This is a view-layer change that applies regardless of graph architecture.

## Architecture

### Graph traversal as a strategy

Introduce a traversal strategy that controls how the graph is built. The firm view and CRM entity view each use a different strategy.

The CRM entity strategy:
1. **Root layer**: Create individual_portfolio node for the CRM entity.
2. **Direct associations layer**: Find funds where the CRM entity has Partner records. For GP Entity funds, create GP entity nodes. For regular funds, create fund nodes. Filter by viewer permissions.
3. **Managed funds layer**: For each GP entity, find the LP funds it manages. Create fund nodes. Filter by viewer permissions.
4. **Investment relationships layer**: For each fund, find feeder/master relationships. Create fund and partner nodes.

The firm strategy (existing behavior, preserved):
1. Build full `InvestedInRelationshipGraph` for the firm (excludes GP entities by default).
2. Discover GP entities by reverse-lookup from LP funds.
3. Create all nodes and edges.
4. No per-layer permission filtering (firm view is staff/admin only today).

### Where the strategy lives

The strategy could be:
- A method on `GraphBuilder` (e.g. `build_graph_for_crm_entity()` vs `build_graph()`)
- A separate builder class per traversal pattern
- A composable pipeline of graph layers

The pipeline approach is the most extensible but may be over-engineering for two strategies. A separate method or subclass is simpler and sufficient for now.

### Key constraint: NodeFetcherService

`NodeFetcherService.fetch_nodes()` takes a flat list of `NodeIdentifier` objects and fetches all node data in one batch. The traversal strategy determines which identifiers to collect, but the fetching is always batched. This is a performance-critical constraint — we must not introduce per-node or per-layer fetching.

For the CRM entity strategy, this means we need to collect all identifiers across all layers first, then fetch once. The layer structure is about permission filtering and edge construction, not about when data is fetched.

## Files affected

### Must change (core logic)
1. `fund_admin/entity_map/graph_builder.py` — new method or subclass for root-outward traversal
2. `fund_admin/entity_map/invested_in_relationship_graph.py` — may need to support GP entity funds in the graph, or may be bypassed entirely for the CRM entity path
3. `fund_admin/entity_map/entity_map_service.py` — wire up the new traversal strategy for CRM entity views

### May change (downstream)
4. `fund_admin/entity_map/views/entity_map_crm_entity_view.py` — permission logic may move or change shape
5. `fund_admin/entity_map/services/node_fetcher_service.py` — may need adjustments if node identifier collection changes
6. `fund_admin/entity_map/views/firm_funds_list_view.py` — if `build_for_firm()` changes defaults, this needs protection

### Test files (8-12 files)
- Unit tests for `InvestedInRelationshipGraphBuilder`
- Backend integration tests for `EntityMapService`
- View tests for `EntityMapCrmEntityView`
- May need new tests for the root-outward traversal

### Total estimate: 15-22 files

This is above the 15-file PR comfort zone. Consider splitting into:
- **PR 1**: Introduce the traversal strategy interface and CRM entity implementation (graph_builder changes)
- **PR 2**: Wire it into the service and view layers, update tests
- **PR 3**: Clean up — remove the Option A workaround, consolidate GP entity discovery

## Open questions

1. **Should `InvestedInRelationshipGraph` include GP entity funds?** The CRM entity strategy could bypass the relationship graph entirely for the GP entity layer, or the graph could be extended to include GP entities as first-class members. The latter would address TODO(GPE-215) but changes `build_for_firm()` defaults.

2. **How to handle the batched fetch constraint?** If we build layers incrementally, we need all node identifiers before fetching. One option: collect identifiers in a first pass (cheap — just queries for fund IDs and relationships), then fetch all node data in a second pass.

3. **Should the firm view eventually use the same architecture?** The firm view could also benefit from a traversal strategy, but changing it is unnecessary risk right now.

## Execution plan

This work starts in a fresh session. Context is preserved in:
- `20260225__investigation__graph-building-inversion-bug.md` — root cause analysis
- `20260225__guide__portfolio-association-and-permissions.md` — how users connect to portfolios
- This document — implementation plan
- `breadcrumbs/fund-admin.md` — session state

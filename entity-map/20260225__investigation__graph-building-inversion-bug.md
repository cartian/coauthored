---
date: 2026-02-25
description: Root cause analysis of the empty entity map graph for non-staff GP users
repository: fund-admin
tags: [entity-map, bug, permissions, graph-builder, investigation]
---

# Graph Building Inversion Bug

## The symptom

When a non-staff GP user (e.g. John Daley) views their entity map, the API returns an empty graph — no nodes, no edges. Staff users see the full graph for the same CRM entity.

## The root cause

The entity map builds its graph backwards. It starts from the outermost layer (LP funds), applies permission filtering there, and then tries to work inward to discover GP entities. When the LP fund layer is empty after filtering, everything collapses.

The correct traversal would start at the root (the CRM entity / portfolio) and expand outward: first to GP entities (where the user actually has Partner records and permissions), then to the LP funds those GP entities manage.

## The chain of failure

### Step 1: build_for_crm_entity() discovers GP entities, then discards them

`InvestedInRelationshipGraphBuilder.build_for_crm_entity()` finds John Daley's Partner records in GP Entity funds (Fund II GP, III GP, IV GP). It then traverses GP Entity → managed LP funds to resolve the "main" funds (Fund II, Fund III, Fund IV, Feeder IV). It builds a relationship graph containing **only the LP funds** and throws away the GP entity fund information.

This is by design — GP entity nodes are supposed to be added later by `GraphBuilder.build_graph()`.

### Step 2: Permission filter empties the graph

`EntityMapService.get_crm_entity_tree()` calls `filtered_to_permitted_funds()` on the LP-only relationship graph. The permitted fund UUIDs come from `_get_permitted_fund_uuids()`, which queries FundPermission records. John Daley's permissions are on GP Entity funds, not LP funds. The filter compares GP fund UUIDs against LP fund UUIDs — zero overlap — and the graph becomes empty.

### Step 3: build_graph() early-returns

`GraphBuilder.build_graph()` receives the empty relationship graph and hits the early return at line 127: `if not funds_dict: return Graph(nodes=[], edges=[])`. It never reaches the code that would create individual_portfolio or GP entity nodes.

### Step 4: GP entity rediscovery would fail anyway

Even without the early return, the GP entity discovery path in `build_graph()` works backwards: it calls `ManagingEntityLinksService.get_managing_entity_uuids_from_funds(non_gp_entity_funds)` — "which GP entities manage these LP funds?" With zero LP funds, this returns nothing.

## Why the architecture is inverted

The `InvestedInRelationshipGraph` was designed for the firm-level entity map view, where the graph naturally starts from funds and shows investment relationships between them. GP entities are decorative nodes layered on top. The CRM entity view was added later, reusing the same infrastructure.

For the firm view, the flow makes sense: build the full fund graph, optionally filter, then decorate with GP entities. For the CRM entity view, the flow is backwards: the user connects to GP entities first, and LP funds are one layer further out. But the code starts at LP funds and tries to reverse-discover GP entities.

## The fix (Option A — pragmatic)

Thread GP entity fund UUIDs from `build_for_crm_entity()` through to `build_graph()` so that GP entity nodes can be created directly without reverse-discovery from LP funds.

Changes:
1. `build_for_crm_entity()` returns a `CrmEntityBuildResult` containing the LP graph + GP entity fund UUIDs
2. `get_crm_entity_tree()` passes GP entity fund UUIDs through, filtering them by the viewer's permissions
3. `build_graph()` accepts `crm_entity_gp_fund_uuids` and creates "standalone" GP entity nodes from them when their managed LP funds aren't in the graph
4. The early return is relaxed when CRM entity context is present

This fix is committed on `gpe-299.cartian.gpva_only_view_investments_permission`.

## The fix (Option B — architectural)

Restructure graph building to work root-outward for CRM entity views. See `20260225__plan__graph-building-architecture-fix.md`.

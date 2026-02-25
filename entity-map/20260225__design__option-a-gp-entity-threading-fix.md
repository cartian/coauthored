---
date: 2026-02-25
description: Design notes for the pragmatic fix that threads GP entity fund UUIDs through graph building
repository: fund-admin
tags: [entity-map, design, permissions, graph-builder]
---

# Option A: GP Entity Threading Fix

## What it does

Threads GP entity fund UUIDs from `build_for_crm_entity()` through to `build_graph()` so that GP entity and individual_portfolio nodes are produced even when the LP fund portion of the graph is empty after permission filtering.

## Why it's needed

### How the entity map graph engine works today

The entity map graph is built in three stages by two cooperating classes:

**Stage 1 — Relationship graph (`InvestedInRelationshipGraphBuilder`).**
This stage discovers which funds exist and how they're connected by investment relationships (fund A is an LP in fund B). For a CRM entity view, `build_for_crm_entity()` starts by finding the CRM entity's Partner records, which tell us which funds the investor is in. It then builds a graph of those funds and their investment connections. Critically, this graph only contains "main" funds — LP funds, feeders, master funds. GP Entity funds are intentionally excluded because they represent managing entities, not investment vehicles. The graph is a data structure called `InvestedInRelationshipGraph`.

**Stage 2 — Permission filtering (`EntityMapService`).**
The service takes the relationship graph from stage 1 and removes any funds the viewer doesn't have permission to see. This is a simple set intersection: keep only funds whose UUID appears in the viewer's permitted fund set. The result is a smaller (or empty) relationship graph.

**Stage 3 — Node building (`GraphBuilder`).**
This stage takes the filtered relationship graph and produces the actual visual graph (nodes and edges). It creates fund nodes from the relationship graph, then separately discovers GP entity nodes by asking "which GP entity manages each fund?" via `ManagingEntityLinksService`. It also creates the individual_portfolio root node for CRM entity views and connects everything with edges. If the relationship graph is empty, the method returns immediately with no nodes.

### Where it breaks

The problem is in how stages 1 and 3 handle GP entities.

In stage 1, `build_for_crm_entity()` finds that John Daley has Partner records in GP Entity funds (Fund II GP, Fund III GP, Fund IV GP). It uses these to traverse GP Entity → managed LP funds, finding the LP funds those GP entities manage (Fund II, Fund III, Fund IV, Feeder IV). It builds the relationship graph from these LP funds and discards the GP entity fund information — it's served its purpose as a stepping stone to the "real" funds.

In stage 2, the permission filter checks the viewer's permissions. John Daley has `view_investments` on the GP Entity funds, not the LP funds. The filter compares his GP fund UUIDs against the LP fund UUIDs in the graph. There's zero overlap, so every fund is removed. The graph is now empty.

In stage 3, `build_graph()` receives the empty graph. It checks `if not funds_dict: return Graph(nodes=[], edges=[])` and exits immediately. It never reaches the code that would create GP entity nodes or the individual_portfolio root. Even if it did reach the GP entity discovery code, that code works backwards — it asks "which GP entity manages each LP fund in the graph?" Since there are no LP funds, it would find nothing.

The information needed to build the correct graph (the GP entity fund UUIDs) existed at stage 1 but was discarded before stage 3 could use it.

### What the fix does

The fix preserves the GP entity fund UUIDs from stage 1 and threads them through stage 2 to stage 3, so that `build_graph()` can create GP entity and individual_portfolio nodes directly from the CRM entity's own data instead of trying to reverse-discover them from LP funds that may not be in the graph.

## Changes

### invested_in_relationship_graph.py

New `CrmEntityBuildResult` dataclass wraps the existing `InvestedInRelationshipGraph` with a `gp_entity_fund_uuids: list[UUID]` field. `build_for_crm_entity()` now returns this instead of a bare graph.

All early-return paths return the result with appropriate GP entity UUIDs — empty list when no GP entities found, populated list even when no managed LP funds exist.

### entity_map_service.py

`get_crm_entity_tree()` unpacks the build result. The LP graph is filtered by permissions as before. The GP entity fund UUID list is also filtered: only UUIDs that appear in the viewer's permitted fund set survive. Both are passed to `build_graph()`.

### graph_builder.py

`build_graph()` accepts a new optional `crm_entity_gp_fund_uuids` parameter. When provided alongside `crm_entity_uuid`:

1. The early returns on empty `funds_dict` / `non_gp_entity_funds` are skipped.
2. GP entity UUIDs not already discovered from LP funds are treated as "standalone" — their node ID uses the GP entity's own UUID as both parts of the composite ID (`to_gp_entity_node_id(gp_uuid, gp_uuid)`).
3. Node identifiers are collected for standalone GP entities and fetched alongside everything else.
4. Standalone GP entity nodes are added to the graph without edges to LP funds (since those LP funds aren't in the graph).
5. `_find_root_targets()` connects the individual_portfolio root to GP entity nodes via `metadata["fund_uuid"]` matching — this works because the GP entity node's fund_uuid metadata is the GP entity fund's own UUID, which matches the partner fund UUIDs in the root node's metadata.

### Unit test updates

Four tests in `TestInvestedInRelationshipGraphBuilderBuildForCrmEntity` updated to access `result.graph.*` instead of `result.*` and to assert on `result.gp_entity_fund_uuids`.

## Permission model

- **individual_portfolio node**: appears whenever any GP entity or LP fund node survives filtering
- **GP entity nodes**: appear if the viewer has `view_investments` on the GP Entity fund
- **LP fund nodes**: appear if the viewer has `view_investments` on the LP fund directly
- **No inference**: having permissions on a GP fund does not grant visibility on its managed LP funds

## What it doesn't fix

The underlying architecture is still inverted — LP funds are built first, GP entities are layered on second. This fix patches the CRM entity path by threading GP entity info through the existing plumbing. The proper architectural fix (Option B) will restructure graph building to work root-outward.

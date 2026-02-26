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

Two issues combine to produce the empty graph.

**Primary cause: overly restrictive permission intersection.** The view gated fund visibility on `view_investments ∩ view_partners ∩ view_fund_performance`. GPs typically have permissions on LP funds, but only 2 of 6 standard roles (`gp_principal`, `audit`) bundle all three. The most common roles — `fund_admin`, `fund_performance`, `investments` — are each missing at least one. A GP with `fund_admin` (which includes `view_investments` + `view_fund_admin_data`) sees zero funds because they lack `view_partners` and `view_fund_performance`.

**Structural issue: GP entity funds excluded from the relationship graph.** `build_for_crm_entity()` calls `build_for_firm()` with the default exclusion list, which drops GP entity funds from the graph. GP entity funds are invisible to `filtered_to_permitted_funds` — they're never permission-checked. Today this doesn't cause the empty-graph symptom (because the permission intersection failing on LP funds is the actual gate), but it means GP entity funds live entirely outside the permission model.

## The chain of failure

### Step 1: build_for_crm_entity() discovers GP entities, then excludes them from the graph

`InvestedInRelationshipGraphBuilder.build_for_crm_entity()` finds John Daley's Partner records in GP Entity funds (Fund II GP, III GP, IV GP). It traverses GP Entity → managed LP funds to resolve the "main" funds (Fund II, Fund III, Fund IV, Feeder IV). It then calls `build_for_firm()` with the default exclusion, which drops GP entity funds from the relationship graph.

This is by design — GP entity nodes are supposed to be rediscovered later by `GraphBuilder.build_graph()` via `ManagingEntityLinksService`.

### Step 2: Permission filter empties the graph

`EntityMapService.get_crm_entity_tree()` calls `filtered_to_permitted_funds()` on the relationship graph. The permitted fund UUIDs come from `_get_permitted_fund_uuids()`, which queries FundPermission records for the intersection of `view_investments`, `view_partners`, and `view_fund_performance`. GPs have permissions on LP funds, but most GP roles don't bundle all three. The intersection is empty, so every fund is filtered out.

### Step 3: build_graph() early-returns

`GraphBuilder.build_graph()` receives the empty relationship graph and hits the early return at line 127: `if not funds_dict: return Graph(nodes=[], edges=[])`.

## Why the architecture has this gap

The `InvestedInRelationshipGraph` was designed for the firm-level entity map view, where the graph naturally starts from funds and shows investment relationships between them. GP entities are decorative nodes layered on top by `GraphBuilder`. The CRM entity view was added later, reusing the same infrastructure.

For the firm view, excluding GP entities from the relationship graph is correct — they're rediscovered from LP funds. For the CRM entity view, this exclusion means GP entity funds (where the CRM entity's Partner records live) are outside the permission-filtered graph entirely.

## The fix (implemented)

Two changes on `gpe-299.cartian.gpva_only_view_investments_permission` ([PR #51788](https://github.com/carta/fund-admin/pull/51788)):

**1. Relax the permission intersection.** Drop `view_partners` from the required permissions. The CRM entity view is scoped to a single investor and already excludes the `fund_partners` node. The gate is now `view_investments ∩ view_fund_performance`, which passes for the `fund_performance`, `gp_principal`, and `audit` roles.

**2. Keep GP entities in the CRM entity relationship graph.** `build_for_crm_entity()` now passes `exclude_entity_types=[MANAGEMENT_CO, ELIMINATION]` to `build_for_firm()` instead of using the default (which also excludes `GP_ENTITY`). GP entity funds stay in `fund_ids_to_fund`, so `filtered_to_permitted_funds` applies to them uniformly. The old branching logic that separated GP entity funds from regular funds is replaced with a single `seed_fund_ids` set. `_connect_fund_trees_by_invested_in_relationship` in `GraphBuilder` skips edges involving fund IDs not in the node ID map (GP entity funds don't have rendered nodes — the visual connection is handled by ManagingEntityLinksService discovery).

## Earlier approaches considered

**Option A (abandoned): CrmEntityBuildResult threading.** Thread GP entity fund UUIDs from `build_for_crm_entity()` through to `build_graph()` via a new `CrmEntityBuildResult` dataclass. This worked but added CRM-specific parameters to shared graph building code.

**Option B: Root-outward graph building.** Restructure the traversal to start from the CRM entity and expand outward. See `20260225__plan__graph-building-architecture-fix.md`. More architecturally correct but larger scope — may be worth revisiting if the entity map needs more view-specific traversal strategies.

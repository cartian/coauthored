---
date: 2026-02-11
description: Implementation plan to fix arbitrary partners[0] selection in CRM entity map views for multi-fund investors
repository: fund-admin
tags: [entity-map, crm-entity, graph-builder, pr-50628, bug-fix]
---

# Fix `partners[0]` arbitrary selection for multi-fund investors

## Context

PR #50628 (`gpe-263.cartian.crm_entity_map_response_follow_up`) adds CRM entity (investor) views to the entity map. When a CRM entity is invested in multiple funds, `IndividualPortfolioNodeFetcher` arbitrarily picks `partners[0]`, bakes that partner's single `fund_uuid` into the root node metadata, and `GraphBuilder._find_root_target()` uses it to create **one** edge. Other funds in the graph are orphaned from the root.

This was flagged by carta-claude's automated review as a "Severity 7 - Data correctness issue" and is still an unresolved review thread on the PR. Galonsky is likely to object to it.

**Problem flow:**
```
IndividualPortfolioNodeFetcher.fetch()
  → partners = PartnerService.list_domain_objects(crm_entity_ids=[uuid])
  → partner = partners[0]                              ← arbitrary
  → node.metadata["fund_uuid"] = partner_fund.uuid     ← single fund baked in

GraphBuilder.build_graph()
  → _find_root_target(nodes, root_node.metadata["fund_uuid"])  ← reads it back
  → creates ONE edge from root to that fund/GP entity          ← other funds orphaned
```

**Goal:** The individual_portfolio root node should have edges to ALL fund entry points, not just one arbitrary fund. Metrics stay from the first partner for now (v1 limitation — same person, same name across all partner records).

**Frontend impact:** None. `individual_portfolio` only appears in auto-generated schema types (`snakedSchemaTypes.ts`, `camelizedSchemaTypes.ts`), not in any hand-written frontend components. The metadata key rename is safe.

## Files to modify

| File | Change |
|------|--------|
| `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py` | `gp_entity_fund_uuid: UUID` → `fund_uuids: list[str]`, metadata `fund_uuid` → `fund_uuids` |
| `fund_admin/entity_map/services/node_fetcher_service.py` | Resolve all partners' fund UUIDs, pass list to builder |
| `fund_admin/entity_map/graph_builder.py` | `_find_root_target` → `_find_root_targets` (returns list), edge creation loops |
| `tests/unit/.../test_individual_portfolio_node_builder.py` | Update signature + metadata assertions |
| `tests/backend/.../test_entity_map_service.py` | Add root-edge assertions to multi-fund test |

## Step-by-step

### 1. `IndividualPortfolioNodeBuilder.build_node()` — change interface

**File:** `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py`

- Rename param `gp_entity_fund_uuid: UUID` → `fund_uuids: list[str]`
- Update docstring param
- Metadata: `"fund_uuid": str(gp_entity_fund_uuid)` → `"fund_uuids": fund_uuids`

### 2. `IndividualPortfolioNodeFetcher.fetch()` — resolve all fund UUIDs

**File:** `fund_admin/entity_map/services/node_fetcher_service.py` (lines 431-479)

- After getting `partners` (line 442-445), build `fund_uuids` list by resolving each partner's fund via `self._fund_service.get_by_fund_id()`
- Keep `partner = partners[0]` for name/metrics (same person, same CRM entity)
- Keep existing metrics fetch for `partners[0]`'s fund only (v1 limitation)
- Pass `fund_uuids=fund_uuids` to builder instead of `gp_entity_fund_uuid=partner_fund.uuid`

### 3. `GraphBuilder._find_root_target()` → `_find_root_targets()`

**File:** `fund_admin/entity_map/graph_builder.py` (lines 291-315)

- Accept `partner_fund_uuids: list[str]` instead of `partner_fund_uuid: str | None`
- Return `list[str]` instead of `str | None`
- Same two-pass logic (prefer gp_entity, fallback to fund) but for each fund UUID in the list

### 4. `GraphBuilder.build_graph()` edge creation block

**File:** `fund_admin/entity_map/graph_builder.py` (lines 221-235)

- Call `_find_root_targets(nodes, root_node.metadata.get("fund_uuids", []))`
- Loop over targets to create one edge per target

### 5. Unit test: `test_individual_portfolio_node_builder.py`

**File:** `tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py`

- Update `build_node` calls: `gp_entity_fund_uuid=uuid` → `fund_uuids=[str(uuid)]`
- Update metadata assertion: `fund_uuid` → `fund_uuids` (now a list)

### 6. Integration test: `test_entity_map_service.py`

**File:** `tests/backend/fund_admin/entity_map/test_entity_map_service.py`

- `test_get_crm_entity_tree_with_investor_in_multiple_funds` (line 2686): Add assertions that root node has 3 outgoing edges, each connecting to a GP entity node for fund_a/fund_b/fund_c
- `test_get_crm_entity_tree_includes_individual_portfolio_node` (line 2341): Verify still produces exactly 1 edge (single-fund backward compat)

## Verification

```bash
# Format & lint
poetry run ruff format \
  fund_admin/entity_map/services/node_fetcher_service.py \
  fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py \
  fund_admin/entity_map/graph_builder.py

poetry run ruff check --fix \
  fund_admin/entity_map/services/node_fetcher_service.py \
  fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py \
  fund_admin/entity_map/graph_builder.py

# Unit test
poetry run pytest tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py -xvs

# Integration tests (key ones first, then full suite)
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestEntityMapService::test_get_crm_entity_tree_includes_individual_portfolio_node -xvs
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestEntityMapService::test_get_crm_entity_tree_with_investor_in_multiple_funds -xvs
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py -x
```

## Not in scope

- **Metrics aggregation** across all fund investments (v1 limitation — `partners[0]` still used for metrics/name since it's the same person)
- **Frontend changes** (no frontend code reads `individual_portfolio` metadata yet)
- **CRM-specific conditionals in GraphBuilder** (separate concern — `if crm_entity_uuid:` branching in `build_graph` is a broader architecture issue Galonsky may also push back on)

## Estimated size

~30 lines net delta across 5 files. Single-fund investors produce identical behavior (one UUID in list → one edge).

## Related

- [20260205__design__individual-portfolio-node.md](20260205__design__individual-portfolio-node.md) — Original design that introduced the individual_portfolio node with single-fund assumption this plan corrects

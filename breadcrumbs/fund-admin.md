# fund-admin — Session 2026-02-22

## What we shipped
- **PR #50962** — `fix(entity-map): Connect individual_portfolio root to all fund entry points` (merged Feb 17)
- **PR #51129** — `fix(entity-map): aggregate individual_portfolio metrics across all funds` (merged Feb 17)
- **PR #51165** — `feat(entity-map): fund-level permissions for CRM entity view` (merged Feb 19)
- **PR #51382** — `feat(entity-map): use earliest LP sharing date as end_date for CRM entity view` (merged Feb 19)
- **PR #51415** — `fix(entity-map): aggregate GP entity fund metrics on individual_portfolio node` (merged Feb 19)
- **PR #19928** — `fix(entity-map): hide firm-admin UI in GP portfolio view` (merged, carta-frontend-platform)

Six PRs merged since the last breadcrumb. The CRM entity view pipeline is now complete: multi-fund root edges → aggregated metrics → fund-level permissions → sharing date cutoff → GP entity fund metrics.

## What's in flight

### Backend (fund-admin)
- **PR #50989** (`gpe-263.cartian.fetcher_registry_factory_classmethods`) — open, independent refactor
- **PR #50927** (`gpe-263.cartian.entity_map_architecture_readme`) — open, docs-only
- **Carry branch** (`gpe-276.cartian.carried_interest_on_entity_map`) — 4 commits ahead of master, awaiting PR creation
  - Adds `carried_interest_accrued` metric, carry gate integration tests, carry gate for hidden funds, backend carry gate removal (frontend controls visibility)
  - PR #51174 was closed — needs a fresh PR after rebase

### Open investigation
- **Partner portfolio entity list discrepancy**: CRM entity view shows only "Krakatoa IV GP" when three connected nodes exist in the entity map graph. Initial analysis (this session):
  - Not a permissions issue (staff user, `permitted_fund_uuids=None`)
  - `_find_root_targets` connects root to fund/gp_entity nodes by matching `fund_uuids` from the `individual_portfolio` node metadata
  - GP entity funds are excluded from `non_gp_entity_funds` in `GraphBuilder.build_graph()` (line 131-134) — they never become `fund` nodes, only `gp_entity` nodes attached to the main fund they manage
  - Need to determine: is the "entity list" a separate UI component reading from a different data path, or is it the graph edges themselves? Also need to check whether the partner actually has records in three funds or if the "three connected nodes" includes non-fund nodes (portfolio, fund_partners)

## What's next
- **Resolve the entity list investigation** — clarify what UI component shows the list and trace its data source
- **Open carry PR** — rebase carry branch on master, open fresh PR (old #51174 was closed)
- **Simplify sharing dates plan** exists at `docs/plans/2026-02-19-simplify-sharing-dates.md` but was superseded by PR #51382 which took the simplified approach and merged. The plan doc is now stale — consider deleting from the repo.

## Key decisions made
- **Three-permission intersection** for fund visibility: `view_investments ∩ view_partners ∩ view_fund_performance` (PR #51165)
- **Graph as single source of truth**: fetcher consults `invested_in_relationship_graph.fund_ids_to_fund` for scope, no separate `permitted_fund_uuids` on `NodeFetchRequest` (PR #51165)
- **Earliest sharing date wins**: single `end_date` from `min(lp_sharing_to_date)` across all visible funds, replaces per-fund sharing date plumbing (PR #51382)
- **GP entity fund metrics included**: `IndividualPortfolioNodeFetcher` resolves GP entity funds not in the relationship graph and includes them in metric aggregation (PR #51415)
- **Carry gate: frontend controls visibility**: backend removed carry gate, frontend handles show/hide based on fund permissions (carry branch)

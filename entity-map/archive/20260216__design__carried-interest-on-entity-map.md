---
date: 2026-02-16
description: Design for adding carried interest accrued metric to entity map nodes
repository: fund-admin
tags: [entity-map, carried-interest, gp-embedded, metrics, design]
---

# Carried Interest on Entity Map Nodes

## Goal

Add carried interest accrued as a metric on entity map nodes. This is the headline GP metric — what GPs see on their dashboard and care about most. Scoped to aggregate carry (a single number per node) for v1.

## Approach

Add `PartnerCapitalCarriedInterestAccrued` to the existing `INCLUDED_METRICS` list in `constants.py`. The metric flows through the existing partner metrics pipeline — fetched by `PartnerAccountMetricsService`, compiled into `MetricsOverTime`, attached to partner nodes, and aggregated to the root node via `MetricsOverTime.__add__()`.

### Why this works cheaply

`PartnerAccountMetricsService.calculate_metrics_with_custom_grouping()` loads the partner transactions dataframe **once per call**, then computes all requested metrics over that in-memory dataframe. Adding one more metric type to the list adds zero additional DB queries.

## Carry Gate

The partner portfolio dashboard gates carry display behind `should_show_carry_metrics_for_fund()`, which checks `GPE_172_PARTNER_DASHBOARD_R1` and per-fund carry info sharing configuration. The entity map respects this same gate.

### Key semantic: absent vs zero vs null

- **Key present, `Decimal` value** → fund has carry, here's the value
- **Key present, `None`** → carry couldn't be calculated (existing metric semantic)
- **Key absent from `end_metrics`** → carry not applicable or not permitted for this node

For funds where the carry gate returns `False`, the `carried_interest_accrued` key is **removed entirely** from the partner's `MetricsOverTime` dicts — not zeroed. This prevents false "0" values and gives the frontend three distinct display states (value, "—", nothing).

### Aggregation behavior

`MetricsOverTime._add_dicts()` unions keys across both operands. If Fund A has carry and Fund B doesn't (key absent), the root node's aggregated carry only reflects Fund A. Correct behavior per design decision: "sum visible funds only."

### Implementation location

`DefaultPartnerMetricsHandler.get_partner_metadata_for_funds()` — after building the per-fund metadata dict, batch-check `show_carry_metrics_by_fund_ids()` for all fund IDs, then strip the carry key from partners in hidden-carry funds using `MetricsOverTime.filtered_by_keys()`.

## Files Changed

| File | Change |
|------|--------|
| `fund_admin/entity_map/constants.py` | Add `PartnerCapitalCarriedInterestAccrued` to `METRIC_KEY_TO_NAME` |
| `fund_admin/entity_map/metrics/partner_metrics_handler.py` | Add carry gate post-processing in `get_partner_metadata_for_funds()` |
| `tests/backend/fund_admin/entity_map/` | Tests for carry metric presence and carry gate filtering |

## Future Work: Deal-Level Carry Breakdowns

The `CarryAttributionService` in `fund_admin/gp_entities/deal_specific/` provides per-deal carry attribution data (deal name, gains, percent of gains). This is currently in development and will layer on top of the aggregate number added here.

Integration path when ready:
- Extend `GPEntityNodeFetcher` or add a new fetcher to call `CarryAttributionService.get_aggregated_attribution()`
- Attach deal-level data to GP Entity node `metadata` dict (e.g., `metadata["carry_attributions"]`)
- The aggregate `carried_interest_accrued` metric from this design remains as the summary number; deal breakdowns provide the drill-down

The entity map's node `metadata: dict[str, Any]` field and the existing fetcher/builder pattern make this additive — no schema changes required.

## Decisions Made

- **Aggregate carry only for v1** — deal-level breakdowns are future work
- **Respect existing carry gate** — `should_show_carry_metrics_for_fund()` per fund, consistent with dashboard
- **Sum visible funds only** — root node aggregates carry from funds where the gate passes; hidden funds don't contribute
- **Remove key (not zero)** — absent key means "not applicable/permitted," zero means "no carry," null means "couldn't calculate"

## Related

- [20260216__plan__carried-interest-on-entity-map.md](20260216__plan__carried-interest-on-entity-map.md) — Implementation plan for adding carry metrics
- [20260213__status__mvp.md](20260213__status__mvp.md) — MVP status document referencing carry as key metric

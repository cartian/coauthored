---
date: 2026-03-03
description: Investigation into why carried_interest_accrued differs between the CRM entity map individual_portfolio node and the partner portfolio summary, and the fix needed to synchronize them
repository: fund-admin
tags: [entity-map, carried-interest, carry-gate, partner-portfolio, metrics-parity]
---

# Carried Interest Accrued: Entity Map vs Partner Portfolio Summary Parity

## Problem

The CRM entity map's `individual_portfolio` node and the partner portfolio summary both display `carried_interest_accrued` for an investor. Both are summaries of the same underlying data, but they can produce different totals for the same investor.

## Root Cause

Both paths use the same metric class (`PartnerCapitalCarriedInterestAccrued`, which sums only `CARRIED_INTEREST_ACCRUED` transactions), but the **partner portfolio summary** applies a visibility gate that the **entity map** does not.

### The carry gate

`fund_admin/partner_portfolios/feature_flags.py::should_show_carry_metrics_for_fund(fund_id)`:

1. If `GPE_172_PARTNER_DASHBOARD_R1` is **disabled** -> show carry for all funds (backward compat)
2. If **enabled** -> only show carry for funds where `GPEntityConfigurationService().fund_is_configured_for_carry_info_sharing(fund_id)` returns `True`

### How each path handles it

| Dimension | Entity map `individual_portfolio` | Partner portfolio summary |
|---|---|---|
| **Carry gate** | None -- always includes carry | `should_show_carry_metrics_for_fund()` -- excludes carry for non-configured funds |
| **Sharing date** | Single `end_date` = min across all visible funds | Per-fund: each fund's own `lp_sharing_to_date` independently |
| **PAMS method** | `calculate_metrics_with_custom_grouping(group_by=["uuid"])` | `calculate_detailed_partner_metrics()` |

### Consequence

If an investor is in 3 funds and only 1 is configured for carry info sharing:
- Portfolio summary shows carry from 1 fund
- Entity map sums carry from all 3

Since `GPE_172_PARTNER_DASHBOARD_R1` is the flag that enables the Partner Dashboard where the entity map appears, these should always agree when the flag is on.

## Fix

Apply the carry gate during NAV aggregation in `IndividualPortfolioNodeFetcher.fetch()`.

The fetcher already iterates per-fund when collecting `PartnerMetadata` (it has `all_funds` and `partner_uuid_by_fund_id`). The fix is to:

1. Batch-lookup carry visibility using `show_carry_metrics_by_fund_ids([f.id for f in all_funds])`
2. Before aggregating `nav_metrics`, zero out `carried_interest_accrued` for funds that don't pass the gate
3. `NAVMetrics.with_subtracted_component()` already exists for this

### Key files

- `fund_admin/entity_map/services/node_fetcher_service.py` -- `IndividualPortfolioNodeFetcher.fetch()` (aggregation logic)
- `fund_admin/partner_portfolios/feature_flags.py` -- `show_carry_metrics_by_fund_ids()` (batch carry gate)
- `fund_admin/entity_map/domain.py` -- `NAVMetrics.with_subtracted_component()` (zeroing mechanism)

### Import boundary note

This creates a dependency from `entity_map` -> `partner_portfolios.feature_flags`. If import-linter contracts prohibit this, the carry gate functions could be lifted to a shared location (e.g., `fund_admin/feature_flags/` or `fund_admin/gp_entities/`).

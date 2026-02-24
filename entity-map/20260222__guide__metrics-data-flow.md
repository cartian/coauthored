---
date: 2026-02-22
description: How the entity map retrieves financial metrics (carry, NAV, distributions) from the database to the API response
repository: fund-admin
tags: [entity-map, metrics, carry, nav, data-flow, explainer]
---

# Entity Map Metrics Data Flow

How carry accrued, carry earned, NAV, and distributions get from the database to the entity map API response — and where discrepancies with the portfolio can arise.

---

## The Chain

Every node fetcher follows the same path to get financial metrics:

```
Capital Account Transactions (DB)
  ↓
PartnerTransactionsServiceV2.get_partner_transactions()
  ↓
PartnerAccountMetricsService.calculate_metrics_with_custom_grouping()
  ↓
PartnerMetricsWithNAVComponentsMetricsHandler._build_partner_metadata()
  ↓
PartnerMetadataFetcher.get_partner_metadata_for_funds()
  ↓
IndividualPortfolioNodeFetcher / FundNodeFetcher / GPEntityNodeFetcher
  ↓
Node (with metrics + nav_metrics)
```

`IndividualPortfolioNodeFetcher`, `FundNodeFetcher`, and `GPEntityNodeFetcher` all go through the same `PartnerMetadataFetcher` → `PartnerMetricsWithNAVComponentsMetricsHandler` path. The handler calls `PartnerAccountMetricsService`, which queries partner transactions from the capital account tables.

---

## Where Each Metric Lives on the Node

| Metric | Location on Node | Transaction type(s) |
|---|---|---|
| Carry accrued | `nav_metrics.nav_components["Carried interest accrued"]` | `CARRIED_INTEREST_ACCRUED` |
| Carry earned | `nav_metrics.nav_components["Carried interest earned"]` | `CARRIED_INTEREST_EARNED` |
| NAV | `nav_metrics.ending_nav` | Sum of all rollforward line items |
| Distributions | `metrics.end_metrics["distribution"]` | `DISTRIBUTION`, `IN_KIND_DISTRIBUTION`, `RECALLABLE_DISTRIBUTION` |
| Commitment | `metrics.end_metrics["commitment"]` | `COMMITMENT` |
| Called capital | `metrics.end_metrics["called_capital"]` | `CALLED_CAPITAL` |
| Unrealized G/L | `metrics.end_metrics["unrealized_gain_loss"]` | Unrealized gain/loss transactions |

There are two metric containers on each `Node`:

- **`metrics: MetricsOverTime`** — summary-level metrics (commitment, called_capital, distribution, dpi, tvpi, rvpi, unrealized_gain_loss). Defined in `entity_map/constants.py` as `METRIC_KEY_TO_NAME`.
- **`nav_metrics: NAVMetrics`** — NAV waterfall breakdown. `ending_nav` is the total; `nav_components` is a dict of every LP rollforward line item (contributions, fees, unrealized, carry accrued, carry earned, distributions, transfers, etc.).

---

## How the Two Containers Get Populated

### `MetricsOverTime` (summary metrics)

`DefaultPartnerMetricsHandler.metric_types_to_fetch()` returns `INCLUDED_METRICS` — seven metric classes:

```python
INCLUDED_METRICS = [
    partner_metrics.Commitment,
    partner_metrics.CalledCapital,
    partner_metrics.Distribution,
    partner_metrics.DPI,
    partner_metrics.TVPI,
    partner_metrics.RVPI,
    partner_metrics.UnrealizedGainLoss,
]
```

These get passed to `PartnerAccountMetricsService.calculate_metrics_with_custom_grouping()`, which runs each metric class against the partner transactions dataframe. Results are mapped to display names via `METRIC_KEY_TO_NAME` and packed into `MetricsOverTime(start_metrics, end_metrics, change_metrics)`.

### `NAVMetrics` (NAV + waterfall components)

`PartnerMetricsWithNAVComponentsMetricsHandler` extends the base handler by overriding `metric_types_to_fetch()` to also include `NAV_COMPONENT_METRICS` — the full set of LP rollforward line items.

`NAV_COMPONENT_METRICS` is derived from the LP rollforward metrics group (`reporting/reports/lp_rollforward/metrics_groups.py`). This includes every line item in the LP capital account statement: beginning balance, contributions, fees, unrealized gains, carry accrued, carry earned, distributions, transfers, ending balance, and more.

In `_build_partner_metadata()`, the handler:

1. Filters `end_metrics` to only keys in `NAV_COMPONENT_METRICS`
2. Pulls `ending_nav` from the ending balance line item
3. Strips summary rows (beginning balance, ending balance, total distributions, total unrealized G/L) to get `nav_components`
4. Builds `NAVMetrics(ending_nav, nav_components)`

---

## Carry Metrics Specifically

### Carry accrued (`PartnerCapitalCarriedInterestAccrued`)

- **Definition**: `fund_admin/metrics/partner/auditable.py` — `ComposableSumMetric` that sums all `CARRIED_INTEREST_ACCRUED` transactions
- **What it represents**: Unrealized carry allocation — carry that has been calculated and allocated on the capital account but not yet distributed
- **Transaction type**: `"Carried interest accrued"`
- **Appears in**: `nav_components` (as an LP rollforward line item)

### Carry earned (`PartnerCapitalCarriedInterestEarned`)

- **Definition**: `fund_admin/metrics/partner/auditable.py` — `ComposableSumMetric` that sums all `CARRIED_INTEREST_EARNED` transactions
- **What it represents**: Carry that has been earned/realized — distinct from carry distributed
- **Transaction type**: `"Carried interest earned"`
- **Appears in**: `nav_components` (as an LP rollforward line item)

### Carry distributed

There is no separate "carry distributed" metric class in the codebase. The closest concepts are:

- `CARRIED_INTEREST_EARNED` — carry earned transactions on partner capital accounts
- `DISTRIBUTION_LLC_INTEREST` and `IN_KIND_DISTRIBUTION_LLC_INTEREST` — carry distributions that flow through the regular distributions bucket

These are distinct transaction types. Whether "carry distributed" in product language maps to `CARRIED_INTEREST_EARNED`, the LLC interest distribution types, or some combination is an open question (project scope item #11).

---

## Aggregation

### Per-fund aggregation (FundNodeFetcher, GPEntityNodeFetcher)

The fetcher gets `PartnerMetadata` for every partner in the fund, then the node builder aggregates:

```python
metrics = sum(
    (pm.metrics for pm in partner_metadata_list),
    start=DEFAULT_METRICS,
)
nav_metrics = sum(
    (pm.nav_metrics for pm in partner_metadata_list if pm.nav_metrics),
    start=NAVMetrics.empty(),
)
```

This works because `MetricsOverTime.__add__()` and `NAVMetrics.__add__()` union keys and sum values.

### Cross-fund aggregation (IndividualPortfolioNodeFetcher)

The root node aggregates across all of the GP's funds using the same `sum()` pattern. It collects `PartnerMetadata` for the GP's partner record in each fund, then sums them all into one set of metrics.

---

## Where Discrepancies Can Arise

If the entity map shows different numbers than the partner portfolio, the underlying data source is the same (`PartnerAccountMetricsService` → capital account transactions). The divergence comes from what each consumer passes to that service:

### 1. Which partners are included

`PartnerMetadataFetcher` can exclude GP/managing member partners via `exclude_gp_and_managing_member`. The portfolio app uses `filter_accepted_partner=True` and excludes deleted funds. If the two paths include different partner records, the aggregated totals will differ.

**File**: `entity_map/partner_metadata_fetcher.py`

### 2. What date is used

The entity map resolves a single `end_date` from `min(lp_sharing_to_date)` across all visible funds. The portfolio app groups partners by sharing date and calculates metrics per group, potentially using different dates for different funds. If any fund has a different sharing date, the two will compute different metric values for that fund.

**File**: `entity_map/entity_map_service.py` — `get_crm_entity_tree()` resolves sharing dates before calling `build_graph()`

### 3. Which funds are in scope

The entity map builds an `InvestedInRelationshipGraph` and filters it by permissions. If a fund is excluded from the graph (permissions, GP entity resolution edge cases), its metrics won't appear in the `IndividualPortfolioNodeFetcher` aggregation.

**File**: `entity_map/services/node_fetcher_service.py` — `IndividualPortfolioNodeFetcher.fetch()`

### 4. GP entity fund resolution

`IndividualPortfolioNodeFetcher` separately resolves GP entity funds that aren't in the `InvestedInRelationshipGraph`. If this resolution finds different funds than the portfolio sidebar's entity list, the totals will diverge.

**File**: `entity_map/services/node_fetcher_service.py` — lines 500-530 of the fetcher

---

## Key Files

| File | Role |
|------|------|
| `entity_map/services/node_fetcher_service.py` | All fetchers — where metrics are requested |
| `entity_map/partner_metadata_fetcher.py` | Coordinates partner lookup + metrics handler |
| `entity_map/metrics/partner_metrics_handler.py` | `DefaultPartnerMetricsHandler` and `PartnerMetricsWithNAVComponentsMetricsHandler` |
| `entity_map/constants.py` | `METRIC_KEY_TO_NAME` mapping |
| `metrics/partner/auditable.py` | Metric class definitions (carry accrued, carry earned, etc.) |
| `metrics/partner/services.py` | `PartnerAccountMetricsService` |
| `reporting/reports/lp_rollforward/metrics_groups.py` | `NAV_COMPONENT_METRICS` source (rollforward line items) |
| `capital_account/constants.py` | Transaction type constants |
| `entity_map/domain.py` | `Node`, `MetricsOverTime`, `NAVMetrics` dataclasses |

---
date: 2026-02-13
description: Plan for aligning entity map CRM entity view metrics with the partner portfolio dashboard by using per-fund lp_sharing_to_date
repository: fund-admin
tags: [entity-map, crm-entity, sharing-dates, nav-discrepancy, metrics]
---

# Use per-fund sharing dates in CRM entity view metrics

## Context

The entity map shows John Daley's NAV as $1.865M while the partner portfolio dashboard shows $1,000,568.18. Root cause: the dashboard uses each fund's `lp_sharing_to_date` (from `CorporationService` gRPC call) as the `information_sharing_date` parameter on `PartnerAccountMetricsService`, filtering transactions to only those the LP should see. The entity map passes a single `end_date` (defaults to today) as `to_date`, including transactions beyond some funds' sharing dates.

Stacked on `gpe-276.cartian.aggregate_individual_portfolio_metrics` (PR #51129).
New branch: `gpe-276.cartian.use_sharing_dates_in_crm_entity_view`.

## How the dashboard does it (reference implementation)

`partner_portfolio_service.py:142-148` — resolves sharing dates:
```python
corporations = self._corporation_service.list_corporation(corporation_ids=fund_uuids)
sharing_dates_by_fund_uuid = {c.uuid: c.lp_sharing_to_date or date.today() for c in corporations if c}
```

`partner_portfolio_service.py:298-323` — groups by sharing date, one metrics call per group:
```python
for sharing_date, partners_for_date in self._group_partners_by_sharing_date(context).items():
    pams = PartnerAccountMetricsService(
        fund_uuids=fund_uuids_for_date,
        partner_uuids=partner_uuids_for_date,
        information_sharing_date=sharing_date,  # NOT to_date
    )
```

Key detail: `information_sharing_date` on `PartnerAccountMetricsService` filters transactions at the dataframe loading level in `get_partner_transactions_df()` (services.py:1081-1098). This is separate from `to_date` which is the reporting end date.

## Approach

1. Resolve sharing dates in `EntityMapService.get_crm_entity_tree()` using `CorporationService`
2. Thread `sharing_dates_by_fund_id` through `NodeFetchRequest` → fetchers → `PartnerMetadataFetcher`
3. In `PartnerMetadataFetcher`, group funds by sharing date and call the metrics handler once per group with `information_sharing_date` instead of `to_date` — matching the dashboard pattern exactly
4. Non-CRM views (fund view, firm view) are unaffected — they don't pass `sharing_dates_by_fund_id`

## Files to modify

### 1. `fund_admin/entity_map/services/domain.py`
Add `sharing_dates_by_fund_id: dict[int, date] | None = None` to `NodeFetchRequest`.

### 2. `fund_admin/entity_map/entity_map_service.py`
In `get_crm_entity_tree()`:
- Add `CorporationService` dependency to `__init__`
- After building `invested_in_relationship_graph`, resolve sharing dates:
  ```python
  funds_dict = invested_in_relationship_graph.fund_ids_to_fund
  fund_uuids = [str(f.uuid) for f in funds_dict.values() if f.uuid]
  corporations = self._corporation_service.list_corporation(corporation_ids=fund_uuids)
  sharing_dates_by_fund_uuid = {c.uuid: c.lp_sharing_to_date or date.today() for c in corporations if c}
  sharing_dates_by_fund_id = {
      f.id: sharing_dates_by_fund_uuid.get(str(f.uuid), date.today())
      for f in funds_dict.values() if f.uuid
  }
  ```
- Pass `sharing_dates_by_fund_id` to `crm_graph_builder.build_graph()`

### 3. `fund_admin/entity_map/graph_builder.py`
- `build_graph()`: accept `sharing_dates_by_fund_id: dict[int, date] | None = None`, pass through to `NodeFetchRequest`

### 4. `fund_admin/entity_map/partner_metadata_fetcher.py`
- Add `sharing_dates_by_fund_id: dict[int, date] | None = None` to `IPartnerMetadataFetcher.get_partner_metadata_for_funds()` and both implementations
- In `PartnerMetadataFetcher.get_partner_metadata_for_funds()`, when `sharing_dates_by_fund_id` is provided:
  - Group funds by sharing date (same pattern as dashboard's `_group_partners_by_sharing_date`)
  - For each group, call `self._partner_metrics_handler.get_partner_metadata_for_funds(funds_group, partners_group, end_date=None, information_sharing_date=sharing_date)`
  - Merge results
- `NoopPartnerMetadataFetcher`: accept and ignore the param

### 5. `fund_admin/entity_map/metrics/partner_metrics_handler.py`
Add `information_sharing_date: date | None = None` through the handler call chain:
- `IPartnerMetricsHandler.get_partner_metadata_for_funds()` — add param to interface
- `DefaultPartnerMetricsHandler.get_partner_metadata_for_funds()` — pass to `_get_partner_metadata_by_uuid()`
- `DefaultPartnerMetricsHandler._get_partner_metadata_by_uuid()` — pass to `_fetch_partner_metrics()`
- `DefaultPartnerMetricsHandler._fetch_partner_metrics()` — pass `information_sharing_date` to `PartnerAccountMetricsService`:
  ```python
  metrics_service = PartnerAccountMetricsService(
      fund_uuids=fund_uuids,
      partner_uuids=partner_uuids,
      start_date=None,
      to_date=end_date,
      information_sharing_date=information_sharing_date,
  )
  ```
- `NoopPartnerMetricsHandler`: accept and ignore
- `PartnerMetricsWithNAVComponentsMetricsHandler`: inherits `_fetch_partner_metrics`, no changes needed

### 6. `fund_admin/entity_map/services/node_fetcher_service.py`
Each fetcher that calls `partner_metadata_fetcher.get_partner_metadata_for_funds()` passes `sharing_dates_by_fund_id=request.sharing_dates_by_fund_id`:
- `FundNodeFetcher.fetch()` (line 162)
- `GPEntityNodeFetcher.fetch()` (line 235)
- `FundPartnersNodeFetcher.fetch()` (line 303) — disabled in CRM view but add for completeness
- `IndividualPortfolioNodeFetcher.fetch()` (line 476)

Also in `NodeFetcherService.fetch_nodes()` (line 649): copy `sharing_dates_by_fund_id` to sub-requests.

### 7. `tests/backend/fund_admin/entity_map/test_entity_map_service.py`
New integration test: `test_get_crm_entity_tree_uses_sharing_dates`
- Create 2 funds with different sharing dates
- Mock `CorporationService.list_corporation` (external gRPC — must mock per testing standards) to return different `lp_sharing_to_date` values
- Create commitment transactions that span beyond the earlier fund's sharing date
- Assert that the individual_portfolio root node's metrics only include transactions up to each fund's sharing date

## What this does NOT change

- **Non-CRM views** (fund view, firm view, journal impact) — no `sharing_dates_by_fund_id` passed, behavior identical
- **Balance sheets** — fund-level GP data, not affected by LP sharing dates
- **Portfolio/issuer nodes** — use `IIssuerMetricsHandler`, not partner metrics
- **GP entity fund sharing dates** — if a GP entity fund has no sharing date in Corporation, falls back to `date.today()` (same as current behavior)

## Verification

```bash
# Format & lint all changed files
poetry run ruff format \
  fund_admin/entity_map/services/domain.py \
  fund_admin/entity_map/entity_map_service.py \
  fund_admin/entity_map/graph_builder.py \
  fund_admin/entity_map/partner_metadata_fetcher.py \
  fund_admin/entity_map/metrics/partner_metrics_handler.py \
  fund_admin/entity_map/services/node_fetcher_service.py

poetry run ruff check --fix \
  fund_admin/entity_map/services/domain.py \
  fund_admin/entity_map/entity_map_service.py \
  fund_admin/entity_map/graph_builder.py \
  fund_admin/entity_map/partner_metadata_fetcher.py \
  fund_admin/entity_map/metrics/partner_metrics_handler.py \
  fund_admin/entity_map/services/node_fetcher_service.py

# Integration tests
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -xvs

# Manual: curl John Daley's entity map and compare NAV with dashboard
curl -s -H "x-carta-user-id: 25" \
  "http://localhost:9000/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/?firm_uuid=186fb573-a22d-4c82-8ad3-3186f9095a41" \
  | python3 -m json.tool
```

---
date: 2026-03-03
description: Investigation into why carried interest values differ between the portfolio summary and entity map, tracing both code paths from raw data to rendered value
repository: fund-admin
tags: [carry, entity-map, portfolio-summary, information-sharing-date, data-paths]
---

# Carry discrepancy: entity map vs portfolio summary

## The question

An investor (Dominic Toretto) shows **$2.6M** carried interest accrued in the portfolio summary but **$450K** in the entity map's individual portfolio node. Both surfaces claim to use `PartnerAccountMetricsService`. Why are the numbers different?

## Architecture: both surfaces share a single data pipeline

Both the portfolio summary and entity map calculate carry through the same service. The difference is exclusively in how they parameterize the date filter.

```
                         Portfolio Summary          Entity Map
                         ────────────────           ──────────
                         per-fund sharing           global min(sharing_dates)
                         date, today() fallback     across ALL visible funds
                                │                           │
                                ▼                           ▼
                    ┌───────────────────────────────────────────┐
                    │       PartnerAccountMetricsService        │
                    │  .calculate_metrics_with_custom_grouping()│
                    └─────────────────┬─────────────────────────┘
                                      │
                    ┌─────────────────▼─────────────────────────┐
                    │       get_partner_transactions()          │
                    │  routes by fund's partner_transaction_    │
                    │  source property                          │
                    └─────────────────┬─────────────────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                     ▼
          ┌───────────┐      ┌──────────────┐      ┌──────────────┐
          │   CATS     │      │  carta_gl    │      │partner_records│
          │  (direct)  │      │  (combined)  │      │  (PR table)  │
          └─────┬─────┘      └──────┬───────┘      └──────────────┘
                │                   │
                │          ┌────────┴──────────────────────┐
                │          │    _get_from_combined()        │
                │          │                                │
                │          │  1. GL journal lines           │
                │          │     (contributions,            │
                │          │      distributions only)       │
                │          │                                │
                │          │  2. manually_allocated CATs    │
                │          │     (carry, fees, unrealized,  │
                │          │      realized, etc.)           │
                │          └───────────────────────────────┘
                │
                ▼
      Carry ALWAYS comes from the CAT table,
      regardless of transaction source.
```

### Key insight: carry lives in the CAT table for all fund types

Even for `carta_gl` funds, the GL only stores contributions and distributions. Carry accruals, unrealized gains, fees, and all other "manually allocated" transaction types are stored as `CapitalAccountTransaction` records. The `_get_from_combined()` method chains GL results with `manually_allocated_cats_only()` results — and carry passes through the latter.

This means the raw data source for carry is identical across both surfaces. Any discrepancy must come from the date filter.

## The date filter: `information_sharing_date`

Both surfaces pass their resolved date as `information_sharing_date` to `PartnerAccountMetricsService`. This triggers a split filter on carry CATs:

```
for_information_sharing_date() filter:
─────────────────────────────────────

  INFO_SHARING_TYPES                    ALL_DATES_BUCKETS
  (carry, unrealized, fees, etc.)       (contributions, distributions)
           │                                      │
           ▼                                      ▼
  date <= information_sharing_date       NO date filter
  (gated)                               (always included)
```

`CATTypes.INFO_SHARING_TYPES` includes `CARRIED_INTEREST_ACCRUED`. So carry CATs are only included when `cat.date <= information_sharing_date`.

### How each surface resolves the date

**Portfolio summary** — per-fund sharing dates:

```python
# Each fund gets its own sharing date from carta-web Corporation
# Falls back to today() if no sharing date is configured
for fund in funds:
    sharing_date = corporation.lp_sharing_to_date or date.today()
    # Carry included if cat.date <= sharing_date
```

**Entity map** — global minimum across all funds:

```python
# entity_map_service.py lines 195-207
corporations = self._corporation_service.list_corporation(
    corporation_ids=fund_uuids   # ALL funds in the relationship graph
)
sharing_dates = [
    c.lp_sharing_to_date
    for c in corporations
    if c and c.lp_sharing_to_date   # None values are SKIPPED
]
if sharing_dates:
    earliest_sharing_date = min(sharing_dates)
    if end_date is None or end_date > earliest_sharing_date:
        end_date = earliest_sharing_date  # clamp down
```

The entity map queries `list_corporation` for **every fund** in the investor's relationship graph — LP funds, GP funds, growth funds. It filters out `None` sharing dates, then takes `min()` of whatever remains.

## The discrepancy mechanism

```
Fund                        lp_sharing_to_date   In graph?
────                        ──────────────────   ─────────
Krakatoa Ventures Fund I    2025-12-31           yes (LP)
Krakatoa Ventures Fund II   2025-12-31           yes (LP)
Krakatoa Ventures Fund III  2025-12-31           yes (LP)
Krakatoa Growth Fund I      None                 yes (LP)
Krakatoa Fund I GP          None                 yes (GP)
Krakatoa Fund II GP         None                 yes (GP)
Krakatoa Fund III GP        None                 yes (GP)
Krakatoa Fund IV GP         None                 yes (GP)

Entity map sharing_dates (non-None only):
  [2025-12-31, 2025-12-31, 2025-12-31]

min(sharing_dates) = 2025-12-31
→ end_date clamped to 2025-12-31
→ All carry CATs dated <= 2024-12-31 pass the filter
→ Expected: full $2.6M
```

With these sharing dates, the entity map **should** show the same $2.6M. The $450K we observed likely points to an additional filtering step or a subset of funds making it through the individual portfolio node's aggregation — an area for further investigation.

### When this mechanism DOES cause real discrepancies

Before we updated the sharing dates, the situation was:

```
Fund                        lp_sharing_to_date
────                        ──────────────────
Krakatoa Ventures Fund I    2018-12-18  ← !!!!
Krakatoa Ventures Fund II   2021-03-31
Krakatoa Ventures Fund III  2020-12-31

min(sharing_dates) = 2018-12-18

Carry CATs:
  Fund I GP:   2022-12-31  $450K  ← AFTER 2018-12-18, filtered out
               2023-12-31  $680K  ← filtered out
               2024-12-31  $920K  ← filtered out
  Fund II GP:  2023-12-31  $180K  ← filtered out
               2024-12-31  $310K  ← filtered out
  (etc.)

Entity map carry: $0
Summary carry: $2.6M (per-fund dates, all pass)
```

One fund with an early sharing date (Fund I at 2018-12-18) pulled the global `min()` back to before any carry CATs existed, zeroing out carry for the entire entity map.

## The carry gate (PR #52234)

Separate from the date filter, the entity map's `IndividualPortfolioNodeFetcher` applies a per-fund carry visibility gate:

```python
# node_fetcher_service.py lines 552-567
carry_visibility = show_carry_metrics_by_fund_ids([f.id for f in all_funds])

for fund in all_funds:
    nav = metadata.nav_metrics
    if not carry_visibility.get(fund.id, True):
        carry_amount = nav.nav_components.get("Carried interest accrued", Decimal(0))
        nav = nav.with_subtracted_component("Carried interest accrued", carry_amount)
    aggregated_nav = aggregated_nav + nav
```

`show_carry_metrics_by_fund_ids` checks:
1. Is `GPE_172_PARTNER_DASHBOARD_R1` feature flag enabled?
2. Does the fund have a `Configuration` record with `name='gp entity carry info sharing'` and `value={'gp entity carry info sharing': True}`?

If the flag is on but the configuration is missing, carry is zeroed for that fund. The portfolio summary applies the same gate at its own layer.

## Debugging checklist

When carry differs between summary and entity map:

1. **Check sharing dates** — `lp_sharing_to_date` in carta-web for all funds in the investor's graph. Look for early dates that would pull `min()` back.

   ```python
   # In carta-web shell
   from eshares.corporations.models import Corporation
   for cid in [fund_corp_ids]:
       c = Corporation.objects.get(id=cid)
       print(f"{cid}: {c.legal_name} | sharing={c.lp_sharing_to_date}")
   ```

2. **Check carry gate config** — does each GP fund have carry info sharing enabled?

   ```python
   # In fund-admin shell
   from fund_admin.entity_config.models import Configuration
   Configuration.objects.filter(
       name='gp entity carry info sharing'
   ).values('fund__carta_id', 'value')
   ```

3. **Check transaction source** — what path does each fund use?

   ```python
   from fund_admin.fund_properties.properties.models.general import GeneralProperties
   for fund in funds:
       gp = GeneralProperties.objects.get(fund=fund)
       print(f"{fund.carta_id}: {gp.partner_transaction_source}")
   ```

4. **Check raw CAT data** — what carry entries exist and what dates?

   ```python
   from fund_admin.capital_account.models.cat import CapitalAccountTransaction
   CapitalAccountTransaction.objects.filter(
       partner__entity_id='<entity_uuid>',
       transaction_type='Carried interest accrued',
   ).values('partner__fund__carta_id', 'date', 'cash_cents').order_by('date')
   ```

5. **Compare resolved dates** — what `information_sharing_date` does each surface use?
   - Summary: per-fund `lp_sharing_to_date` or `today()`
   - Entity map: `min(non-null sharing dates)` across all funds in graph, or the request's `end_date` if smaller

## Known limitations (follow-up work planned)

The `min(sharing_dates)` global date in the entity map is a known architectural limitation. It means one fund with a stale sharing date can suppress data for all funds. The planned fix is to use per-fund sharing dates in the entity map, matching the portfolio summary's approach. This is tracked as follow-up to the carry gate work.

## Key file reference

| File | What it does |
|------|-------------|
| `fund_admin/entity_map/entity_map_service.py:195-207` | Resolves global `min(sharing_dates)` for entity map |
| `fund_admin/entity_map/services/node_fetcher_service.py:530-567` | Individual portfolio node: fetches metrics, applies carry gate |
| `fund_admin/entity_map/metrics/partner_metrics_handler.py:146-158` | Passes `information_sharing_date` to metrics service |
| `fund_admin/capital_account/services/partner_transactions_v2.py:684-708` | `_get_from_combined()`: GL + manual CATs for carta_gl funds |
| `fund_admin/capital_account/models/cat.py` | `manually_allocated_cats_only()`, `for_information_sharing_date()` |
| `fund_admin/partner_portfolios/feature_flags.py` | `show_carry_metrics_by_fund_ids()` carry gate lookup |
| `fund_admin/entity_config/models.py` | `Configuration` model for carry info sharing settings |

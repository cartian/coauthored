---
date: 2026-03-03
description: Consolidated investigation into carry discrepancies between entity map and portfolio summary, the carry gate fix, and the cross-system architecture that underpins both surfaces
repository: fund-admin
tags: [carry, entity-map, portfolio-summary, information-sharing-date, cross-system, carta-web, carry-gate]
---

# Carry Metrics & Cross-System Architecture

This document consolidates three investigations from the 2026-03-03 session:
- Why carried interest values differed between entity map and portfolio summary
- The carry gate fix (PR #52234) that brought the two surfaces into parity
- The cross-system architecture (fund-admin <-> carta-web) that both surfaces depend on

## Part 1: Cross-System Architecture

### The Corporation UUID = CRM Entity UUID invariant

The partner portfolio init endpoint bridges carta-web and fund-admin:

```
GET /partner-portfolios/<corp_pk>/app/init
```

Data flow:
1. carta-web renders the portfolio page for Corporation PK (e.g., 2472)
2. carta-web calls fund-admin at `/partner-portfolios/2472/app/init`
3. fund-admin's `PartnerPortfolioService.get_partner_dashboard_init_metadata(acceptor_id=2472)`:
   - Calls gRPC back to carta-web: `CorporationServiceStub.list_corporations_using_cw_ids([2472])`
   - Gets back Corporation data including its UUID
   - **Uses that UUID directly as the CRM Entity ID**: `crm_entity_id = UUID(cw_corporations[0].uuid)`
   - Looks up partners via CRM entity

**If the carta-web Corporation UUID doesn't match the fund-admin CRM Entity UUID, the lookup returns nothing and the endpoint 404s.** For real data, the sharing flow synchronizes these UUIDs naturally. For seeded data, you must set them explicitly.

### Required records for LP portfolio

**fund-admin:**

| Model | Purpose |
|-------|---------|
| CRMOrganization | Container for the CRM entity |
| CRMEntity | The legal identity (UUID = Corporation UUID) |
| IndividualEntityInfo + LPCRMFullLegalName | Name and DOB |
| PartnerInterestGroup | Groups partners by entity+fund, needs `accepted_date` and `sent_date` |
| Partner | Individual fund position, needs `accepted_date` and `sent_date` |
| CommitmentTransaction | Commitment amount per partner |
| CapitalAccountTransaction | Contributions, distributions, gains, fees |
| PartnerContact | Primary contact with email |
| PartnerContactPermission | Boolean flags for document access types |
| CarriedInterestAssignment / PartnerCarriedInterestAssignment | GP carry (GP entities only) |
| FundJournal / FundJournalLine | GL entries (GP entities only) |

**carta-web:**

| Model | Purpose | Key fields |
|-------|---------|------------|
| User | Login identity | email, username, password |
| Organization | Container org | `organization_type='individual'` (NOT default 'investment_firm') |
| Corporation | LP entity | `uuid` MUST match CRM Entity UUID, `type='Personal'`, `can_hold=True` |
| EntityOrgPermission | Links Corp to Org | `entity=corp, organization=org` |
| OrganizationMembership | Links User to Org | Need both LP user and admin user |
| CapitalAccount | Bridges to fund-admin | `fundadmin_partner_id`, `fundadmin_partner_uuid`, `sent_date`, `accepted_date` |

### Common pitfalls

- **Organization type defaults to 'investment_firm'** — routes to firm portfolio view instead of individual
- **Multiple admin users** — use `User.objects.get(id=25)` not `email='admin@esharesinc.com'`
- **Docker container name** — carta-web's main container is `python`, not `app`
- **accepted_date / sent_date** — PIGs and Partners need both set for permissions and bulk_accept

### Key code paths

- `fund_admin/partner_portfolios/services/partner_portfolio_service.py` — `get_partner_dashboard_init_metadata()`
- `fund_admin/capital_account/services/corporation_services.py` — `CorporationService.list_corporations_using_cw_ids()` (gRPC)
- `fund_admin/partner_portfolios/views.py` — `PartnerPortfolioInitAPIView`

## Part 2: Carry Metrics Pipeline

Both the portfolio summary and entity map calculate carry through the same service. The difference is exclusively in how they parameterize the date filter.

```
                         Portfolio Summary          Entity Map
                         ----------------           ----------
                         per-fund sharing           global min(sharing_dates)
                         date, today() fallback     across ALL visible funds
                                |                           |
                                v                           v
                    +-----------------------------------------------+
                    |       PartnerAccountMetricsService             |
                    |  .calculate_metrics_with_custom_grouping()     |
                    +---------------------+-------------------------+
                                          |
                    +---------------------v-------------------------+
                    |       get_partner_transactions()               |
                    |  routes by fund's partner_transaction_source   |
                    +---------------------+-------------------------+
                                          |
                 +------------------------+--------------------+
                 v                        v                    v
          +-----------+        +----------------+      +----------------+
          |   CATS    |        |   carta_gl     |      | partner_records|
          | (direct)  |        |  (combined)    |      |  (PR table)   |
          +-----+-----+        +-------+--------+      +----------------+
                |                       |
                |              +--------+------------------------+
                |              |    _get_from_combined()          |
                |              |                                  |
                |              |  1. GL journal lines             |
                |              |     (contributions, distros)     |
                |              |                                  |
                |              |  2. manually_allocated CATs      |
                |              |     (carry, fees, unrealized)    |
                |              +---------------------------------+
                |
                v
      Carry ALWAYS comes from the CAT table,
      regardless of transaction source.
```

### Key insight: carry lives in CATs for all fund types

Even for `carta_gl` funds, the GL only stores contributions and distributions. Carry accruals, unrealized gains, fees, and all other "manually allocated" transaction types are stored as `CapitalAccountTransaction` records. The `_get_from_combined()` method chains GL results with `manually_allocated_cats_only()` results. Any carry discrepancy must come from the date filter or the carry gate — not the raw data.

## Part 3: Two Sources of Discrepancy

### Source 1: The `information_sharing_date` filter

Both surfaces pass their resolved date as `information_sharing_date` to `PartnerAccountMetricsService`. This triggers a split filter on carry CATs:

```
for_information_sharing_date() filter:

  INFO_SHARING_TYPES                    ALL_DATES_BUCKETS
  (carry, unrealized, fees, etc.)       (contributions, distributions)
           |                                      |
           v                                      v
  date <= information_sharing_date       NO date filter
  (gated)                               (always included)
```

**How each surface resolves the date:**

| Dimension | Portfolio Summary | Entity Map |
|-----------|------------------|------------|
| Date resolution | Per-fund `lp_sharing_to_date`, falls back to `today()` | `min(non-null lp_sharing_to_date)` across ALL funds in graph |
| Scope | Only the fund being rendered | Every fund in the investor's relationship graph |

The entity map's global `min()` means **one fund with a stale sharing date poisons carry for all funds**. This was the root cause of the $450K vs $2.6M discrepancy:

```
Before fix (original sharing dates):

Fund                        lp_sharing_to_date
----                        ------------------
Krakatoa Ventures Fund I    2018-12-18  <-- pulls min() to 2018
Krakatoa Ventures Fund II   2021-03-31
Krakatoa Ventures Fund III  2020-12-31

min(sharing_dates) = 2018-12-18
-> All carry CATs dated after 2018-12-18 filtered out
-> Entity map carry: $0

After fix (sharing dates updated to 2025-12-31):
-> Entity map carry: $2,605,000 (matches portfolio summary)
```

### Source 2: The carry gate (PR #52234)

Separate from the date filter, the portfolio summary applies a per-fund carry visibility gate that the entity map originally did not.

`should_show_carry_metrics_for_fund(fund_id)` checks:
1. Is `GPE_172_PARTNER_DASHBOARD_R1` enabled? If not, show carry for all funds (backward compat)
2. If enabled, does the fund have a `Configuration` record with `name='gp entity carry info sharing'` and `value={'gp entity carry info sharing': True}`?

**The fix** (PR #52234) applies this gate in `IndividualPortfolioNodeFetcher.fetch()`:

```python
carry_visibility = show_carry_metrics_by_fund_ids([f.id for f in all_funds])

for fund in all_funds:
    nav = metadata.nav_metrics
    if not carry_visibility.get(fund.id, True):
        carry_amount = nav.nav_components.get("Carried interest accrued", Decimal(0))
        nav = nav.with_subtracted_component("Carried interest accrued", carry_amount)
    aggregated_nav = aggregated_nav + nav
```

Import boundary note: this creates a dependency from `entity_map` -> `partner_portfolios.feature_flags`. If import-linter contracts prohibit this, the carry gate functions could be lifted to a shared location.

## Debugging Checklist

When carry differs between summary and entity map:

1. **Check sharing dates** — `lp_sharing_to_date` in carta-web for all funds in the investor's graph. Look for early dates pulling `min()` back.

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
   - Entity map: `min(non-null sharing dates)` across all funds in graph

## Known Limitations

The `min(sharing_dates)` global date is a known architectural limitation. The planned fix is per-fund sharing dates in the entity map, matching the portfolio summary's approach. This would eliminate the class of bug where one stale fund poisons carry for the entire graph.

## Key File Reference

| File | What it does |
|------|-------------|
| `fund_admin/entity_map/entity_map_service.py:195-207` | Resolves global `min(sharing_dates)` |
| `fund_admin/entity_map/services/node_fetcher_service.py:530-567` | Individual portfolio node: fetches metrics, applies carry gate |
| `fund_admin/entity_map/metrics/partner_metrics_handler.py:146-158` | Passes `information_sharing_date` to metrics service |
| `fund_admin/capital_account/services/partner_transactions_v2.py:684-708` | `_get_from_combined()`: GL + manual CATs |
| `fund_admin/capital_account/models/cat.py` | `manually_allocated_cats_only()`, `for_information_sharing_date()` |
| `fund_admin/partner_portfolios/feature_flags.py` | `show_carry_metrics_by_fund_ids()` carry gate lookup |
| `fund_admin/partner_portfolios/services/partner_portfolio_service.py` | `get_partner_dashboard_init_metadata()` cross-system bridge |

## Test Data Reference

Dominic Toretto (seeded LP):
- CRM Entity UUID / carta-web Corporation UUID: `6ad327a3-cfe4-4326-932f-c02709f71c9b`
- carta-web Corporation ID: 2472, Organization ID: 165153
- carta-web User: dom@krakatoa.vc (id=77737)
- Portfolio URL: `/investors/individual/2472/portfolio/`

John Daley (known working LP):
- carta-web Corporation ID: 2470, UUID: `a2f23ebe-...`
- Organization ID: 163153, type: 'individual'
- Portfolio URL: `/investors/individual/2470/portfolio/`

Krakatoa fund mapping:

| carta_id | Fund | Type |
|----------|------|------|
| 59 | Fund I | LP |
| 58 | Fund II | LP |
| 497 | Fund III | LP |
| 498 | Fund IV | LP |
| 124 | Growth Fund I | LP |
| 90 | Fund I GP | GP |
| 127 | Fund II GP | GP |
| 501 | Fund III GP | GP |
| 502 | Fund IV GP | GP |

## Related

- [Seed script](20260303__guide__seed-dominic-toretto.py) — creates the full Dominic Toretto test data
- [R1 testing guide](20260304__test__r1-testing-session-guide.md) — manual test plan covering carry gate behavior
- [Graph building inversion bug](20260225__investigation__graph-building-inversion-bug.md) — related permission/graph issue
- [Portfolio association and permissions](20260225__guide__portfolio-association-and-permissions.md) — permission model reference
- [PR #52234](https://github.com/pccarta/fund-admin/pull/52234) — carry gate implementation

# fund-admin — Session 2026-03-03

## What we shipped
- PR #52234: carry gate in `IndividualPortfolioNodeFetcher.fetch()` — suppresses `carried_interest_accrued` per-fund based on `show_carry_metrics_by_fund_ids` + `gp entity carry info sharing` Configuration
- Updated `lp_sharing_to_date` in carta-web for Krakatoa LP funds (59, 58, 497, 498) → 2025-12-31, unblocking carry in entity map
- Enabled carry info sharing Configuration for GP funds 90, 127, 501, 502
- Deactivated duplicate Dominic Toretto partners (entity `341dc35e` seed re-run, entity `3322fc5b` pre-existing)
- Created intra-firm partner link for Fund I GP → Fund I LP (partner_pk=4134, `partner_type='general_partner'`)
- Updated seed script in coauthored with idempotency guard, import fix (`PartnerContactPermission` from `partner_contact`), field name fix (`annual_and_quarterly_reports`)
- Investigation doc: `20260303__investigation__carry-discrepancy-entity-map-vs-portfolio-summary.md`

## What's in flight
- Branch `gpe-333.cartian.apply_carry_gate_to_entity_map` — PR #52234 open, ready for review

## What's next
- Follow-up: replace `min(sharing_dates)` global date with per-fund sharing dates in entity map
- Consider adding carry info sharing config + sharing date setup to seed script
- Fund II GP appears twice in graph (intra-firm links to both Fund II LP and Silver Spurs) — cosmetic but worth investigating

## Key decisions made
- Carry gate uses existing `show_carry_metrics_by_fund_ids` batch lookup, zeroes via `NAVMetrics.with_subtracted_component()`
- Idempotency check uses `Partner.name` (reliable) not `IndividualEntityInfo.legal_name` (not populated for carta-web-synced entities)
- Entity map graph is hierarchical (gp_entity → fund → portfolio branches), not flat connections

## Root cause: $450K vs $2.6M carry discrepancy (RESOLVED)
The entity map's `min(non-null lp_sharing_to_date)` across ALL funds in the graph was being pulled down by Fund IV LP (carta_id=498) which had `lp_sharing_to_date=2023-09-30`. This clamped `end_date` to 2023-09-30, causing `for_information_sharing_date()` to filter out all carry CATs dated after 2023-09-30. Only Fund I GP's 2022-12-31 CAT ($450K) survived. Updating Fund IV LP's sharing date to 2025-12-31 resolved it — entity map now shows $2,605,000 carry, matching the portfolio summary.

Key lesson: any single fund with a stale `lp_sharing_to_date` poisons the entire entity map via `min()`. The planned per-fund sharing date fix would eliminate this class of bug.

## Key data references
- CRM Entity UUID: `6ad327a3-cfe4-4326-932f-c02709f71c9b`
- carta-web Corporation ID: 2472 (uuid matches CRM Entity)
- carta-web User: dom@krakatoa.vc (id=77737)
- Admin user: id=25 (admin@esharesinc.com)
- Firm UUID: `186fb573-a22d-4c82-8ad3-3186f9095a41`
- GP fund carta_ids: 90 (Fund I GP, pk=668), 127 (Fund II GP, pk=676), 501 (Fund III GP, pk=698), 502 (Fund IV GP, pk=699)
- LP fund carta_ids: 59 (Fund I, pk=693), 58 (Fund II, pk=60), 497 (Fund III, pk=694), 498 (Fund IV, pk=695), 124 (Growth Fund I, pk=673)

## Key artifacts
- `~/Projects/coauthored/entity-map/20260303__investigation__carry-discrepancy-entity-map-vs-portfolio-summary.md`
- `~/Projects/coauthored/entity-map/20260303__guide__seed-dominic-toretto.py`
- `~/Projects/coauthored/entity-map/20260303__investigation__carry-gate-parity-entity-map-vs-portfolio-summary.md`

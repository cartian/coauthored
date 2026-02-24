---
date: 2026-02-18
description: Follow-up plan for fund-admin PR #51174 — remove backend carry stripping, move visibility control to the frontend
repository: fund-admin
tags: [entity-map, carried-interest, carry-gate, nav-components]
---

# Backend Carry Gate Follow-up: PR #51174

## Problem

PR #51174 strips `Carried interest accrued` from `nav_components` on the backend when the carry gate is `False`. Galonsky correctly identified that this breaks the NAV waterfall invariant: `nav_components` entries should sum to `ending_nav`. Removing one component without adjusting the total means the numbers no longer reconcile.

The carry gate should control **display visibility**, not data integrity. NAV should still be shown even when carry is hidden — the frontend decides which `nav_components` keys to surface.

## What to change

### Remove `_apply_carry_gate` from `partner_metrics_handler.py`

Delete the `_apply_carry_gate` method and its call site in `get_partner_metadata_for_funds` (line 144). The backend should return `nav_components` with all its line items intact, including carried interest. Also remove the `CARRY_METRIC_NAME` constant and the `show_carry_metrics_by_fund_ids` import.

The carry gate still matters — it just belongs on the frontend. The frontend PR (carta-frontend-platform #19953) is being reworked to add a `displayNavComponents` field to `FundViewContext` that controls which `nav_components` keys render on node cards. The CRM Entity view will include `'Carried interest accrued'` only when the carry gate permits it.

### Update tests

- Delete `test_get_crm_entity_tree_hides_carry_when_fund_gate_is_false`
- Delete `test_get_crm_entity_tree_carry_aggregation_with_partial_visibility`
- Keep `test_get_crm_entity_tree_includes_carried_interest_metric` — carry should always be present in the data

### Open question

How does the frontend know the carry gate status? Options:

1. **Separate API field** — the entity map API response includes a `carry_visible: bool` (or per-fund map) alongside the node data. Frontend reads this to populate `displayNavComponents`.
2. **Existing feature flag check** — if the frontend already has access to `GPE_172_PARTNER_DASHBOARD_R1` + per-fund config, it can make the determination itself.
3. **Backend curates a display hint** — the API response includes a `display_nav_components: string[]` field that tells the frontend which keys to show. This pushes the gate logic back to the backend but as metadata, not data mutation.

Option 3 is cleanest: the backend owns the business rule (which funds allow carry visibility) and communicates it as a display hint without corrupting the data. The frontend just reads the hint into `displayNavComponents`.

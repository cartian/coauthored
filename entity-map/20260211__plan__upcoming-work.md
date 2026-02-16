---
date: 2026-02-11
description: Tracked upcoming work items for the GP Embedded Entity Map
repository: fund-admin
tags: [entity-map, gp-embedded, planning, upcoming]
---

# GP Embedded Entity Map: Upcoming Work

## MVP

### Fund-level permissions for GPs

**Problem:** The entity map CRM entity endpoint requires `HasAllViewPermissions | IsStaff`. Most GPs fail this check — they're missing `view_general_ledger` (Gate 1) or don't have permissions on every fund in the firm (Gate 2). A real GP hitting the Partner Dashboard entity map today gets a 403.

**What needs to happen:**
- Accept the requesting user's ID into the graph builder
- Query `PermissionService` for the set of funds this user has view access to
- Filter graph nodes to only include permitted funds
- Prune orphaned sub-trees when a fund is filtered out
- Relax the permission class from `HasAllViewPermissions` to `IsFirmMember`

**Key files:**
- `fund_admin/entity_map/views/entity_map_crm_entity_view.py` — permission class on the view (line 46)
- `fund_admin/permissions/gp_permissions/permission_classes.py` — `HasAllViewPermissions` (line 587)
- `fund_admin/entity_map/invested_in_relationship_graph.py` — graph builder, where filtering would live

**Risk:** If we relax permissions without adding filtering, a GP with access to Fund A but not Fund B would see Fund B's structure and financials. Data leak. The filtering must ship with the permission relaxation.

### Fix individual portfolio metrics (math)

The financial metrics on the individual portfolio root node are wrong. The math doesn't add up from the GP Entity level to the GP member level — the numbers the GP sees for their own position don't reflect a correct aggregation of the underlying GP Entity data. Will diagnose the specific field mapping issues against real customer API responses.

### Fix GP partner visibility (edges)

The GP's own partner record is missing from the GP Entity partner list. The partner fetching logic excludes managing members/GPs from `fund_partners` children — correct for firm-level view, wrong when the GP is the graph subject.

### Flipper feature flag configuration

The frontend checks `GPE_215_CRM_ENTITY_MAP` via Flipper. For dogfooding and early rollout, we need to target the flag by whatever ID is in the portfolio page URL (likely a CRM entity ID or carta ID) so we can enable the entity map for specific GPs/accounts without a broad rollout. Need to figure out which identifier Flipper is evaluating against and set up targeting rules accordingly.

### End-to-end wiring

Feature flag, Partner Dashboard entry point, and full render pipeline haven't been tested as a connected flow with an actual GP (not staff).

## Post-MVP

### Remove firm-scoped CRM entity API URL

The firm-scoped variant (`firm/<firm_uuid>/entity-atlas/crm-entity/<crm_entity_uuid>/`) is dead code — we'll always use the firmless endpoint and let the backend derive the firm from the CRM entity's partner data. Remove the URL pattern (line 34-37 in `entity_map/urls.py`) and any frontend references to it.

### Multi-firm support (firmless endpoint)

**Problem:** A GP invested in funds across multiple firms only sees one firm. The firmless endpoint (`entity-atlas/crm-entity/<uuid>/`) queries all partner records, then picks `partners[0].fund_id` and derives a single firm from it. Partners in other firms are silently dropped. No error, no indication of omitted data.

**What needs to happen:**
- Group partner records by firm (the data is already fetched at the view layer, just not grouped)
- Call `build_for_crm_entity()` once per firm
- Return either multiple graphs keyed by firm or a merged graph with a cross-firm root
- Run permission checks per-firm; decide whether partial results (2 of 3 firms) are acceptable or misleading

**Key files:**
- `fund_admin/entity_map/views/entity_map_crm_entity_view.py` — `_get_firm_uuid_from_crm_entity()` (line 56) is where the single-firm assumption lives
- `fund_admin/entity_map/invested_in_relationship_graph.py` — `build_for_crm_entity()` takes a single `firm_id`

**Note:** The graph builder doesn't need to change. This is N calls to the existing builder, not a refactor of the builder itself. The open question is the response shape and what to do with partial permission failures. ~80% of customers are single-firm, so this is a real but minority case.

### Carried interest

The number GPs care about most. Not in the entity map yet — carry calculation lives in the GP Entity app's service layer. Requires integration with the carry service to surface it as a metric on the investor root node.

### Metrics and analytics

This is a product decision, not just a technical one. We need to decide what we measure and why — what questions are we trying to answer about GP engagement with the entity map? Usage counts and performance baselines are table stakes, but the interesting decisions are around engagement signals: what tells us this feature is valuable to GPs vs. just rendered and ignored? What metrics would inform whether to invest further?

Frontend has ~45 Snowplow events already instrumented. Backend has zero. The backend instrumentation (StatsD/DataDog for endpoint hit counts, graph build duration, permission denied rate, graph size distribution) should be in place before customer rollout to establish performance baselines. But the product framing of what success looks like needs to come first.

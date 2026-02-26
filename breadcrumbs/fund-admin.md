# fund-admin — Session 2026-02-26

## What we shipped
- Built and iterated on GP permission analysis Jupyter notebook (`~/Desktop/gp-permission-analysis.md`)
  - 13 cells surveying `view_investments` and `view_fund_performance` across 31 target firms
  - Aggregate coverage tables, per-firm breakdowns, GP Entity vs LP fund gap analysis
  - Portfolio deep dive cell (Cell 12) for single CRMEntity UUID lookup
  - Firm deep dive cell (Cell 13) for per-member permission audit by carta_id
- Created Carta-branded HTML export (`~/Downloads/gp_fund_permissions_branded.html`)
  - Stripped Jupyter boilerplate, applied Carta brand guidelines (Playfair Display, Plus Jakarta Sans, IBM Plex Mono)
  - Full-width tables breaking out of 960px container, left-aligned headers
- Wrote CRMEntity reference doc (`~/Projects/coauthored/reference/20260226__guide__what-is-a-crm-entity.md`)
  - Multiple explanatory angles: relational, lifecycle, analogy, gotchas
  - Includes CRMEntity vs PartnerInterestGroup comparison and three-layer hierarchy

## What's in flight

### GPE-299: Permission gate fix (pushed)
Branch: `gpe-299.cartian.gpva_only_view_investments_permission` (pushed to remote)
PR: #51788 (draft)

Two-commit fix:
1. Permission gate: `view_investments ∩ view_fund_performance` (dropped `view_partners`)
2. Architecture: pass `exclude_entity_types=[MANAGEMENT_CO, ELIMINATION]` to `build_for_firm` in CRM entity path, keeping GP entities in the relationship graph for uniform permission filtering

**Status**: Pushed and PR updated, but manual QA found a new bug. User has permissions on GP entity funds but not the LP funds they manage. After `filtered_to_permitted_funds`, only GP entities survive. `build_graph` filters those out, returns empty graph.

### Carry branch
`gpe-276.cartian.carried_interest_on_entity_map` — 4 commits ahead of master, needs fresh PR.

### Other open PRs
- PR #50989 (fetcher registry refactor) — open
- PR #50927 (architecture readme) — open, docs-only

## What's next
- Decide permission transitivity model based on notebook findings
- Key finding from notebook: 97.5% of users have `view_investments` on GP Entity funds, 87.5% have `view_fund_performance`. Only 1 user (0.4%) has LP fund access but is missing permissions. The permission gap is largely theoretical.
- 46.5% of GP-permitted users have no LP-only fund access at all (firms use GP+LP funds, not separate LP funds)
- Open carry PR (rebase carry branch first)

## Key decisions made
- **`view_investments ∩ view_fund_performance`** as permission gate. `view_partners` dropped because CRM entity view is scoped to one investor's data.
- **Keep GP entities in firm graph** for CRM entity path via `exclude_entity_types` parameter.
- **FirmMember has no name field** — only `contact_email`, `user_id`, `title`. Names live in carta-web's User model.
- **CRMEntity is not polymorphic** — it's always "the legal identity behind a fund commitment." `entity_type` is a tax classification (Individual, LLC, Trust, etc.), not a role. The CRMEntity UUID maps to carta-web Corporation UUID after sharing.

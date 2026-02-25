# fund-admin — Session 2026-02-25

## What we shipped
- Committed `fix(entity-map): require only view_investments for CRM entity fund visibility` on `gpe-299.cartian.gpva_only_view_investments_permission`
- Committed `fix(entity-map): show GP entity and portfolio nodes when LP funds are filtered out` on the same branch

## What's in flight

### GPE-299: Permission fixes (current branch)
Branch: `gpe-299.cartian.gpva_only_view_investments_permission`
Two commits ahead of master. Fixes two permission bugs in the CRM entity view:
1. Simplified fund visibility to require only `view_investments` (was three-permission intersection)
2. Threaded GP entity fund UUIDs through graph building so individual_portfolio and GP entity nodes appear even when LP funds are filtered out by permissions

**Not yet pushed.** Needs manual QA with John Daley user (user_id 77743) to verify the graph renders correctly.

### GPE-299: Architecture fix (planned, separate branch)
Will be a new branch based on master. Restructures graph building to work root-outward (CRM entity → GP entities → LP funds) instead of the current inverted approach (LP funds → reverse-discover GP entities). See `20260225__plan__graph-building-architecture-fix.md` for details.

### Carry branch
`gpe-276.cartian.carried_interest_on_entity_map` — 4 commits ahead of master, still needs fresh PR.

### Other open PRs
- PR #50989 (fetcher registry refactor) — open
- PR #50927 (architecture readme) — open, docs-only

## What's next
- Push Option A branch, open draft PR for GPE-299
- Manual QA: verify John Daley sees individual_portfolio + GP entity nodes
- Start Option B (architecture fix) on new branch from master
- Open carry PR (rebase carry branch first)

## Key decisions made
- **`view_investments` only** for CRM entity fund visibility. `view_partners` and `view_fund_performance` dropped — this is a "my portfolio" view scoped to the investor's own data, not other partners' information.
- **GP entity nodes always visible** if the viewer has `view_investments` on the GP Entity fund, regardless of whether they have permissions on the managed LP funds.
- **Don't infer LP permissions from GP permissions.** Having permission on Fund IV GP does not automatically grant visibility on Fund IV LP.
- **Option A (pragmatic) now, Option B (architecture) later.** Option A threads GP entity info through existing plumbing. Option B will restructure graph building to work root-outward, addressing the underlying design inversion.

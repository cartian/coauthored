# fund-admin — Session 2026-02-16

## What we shipped
- **PR #51154** review feedback addressed: switched `unittest.mock.MagicMock` to `mocker.MagicMock()` per codebase standards (carta-claude finding). Pushed.

## What's in flight

### Backend (fund-admin)
- **PR #50962** (multi-fund root edges) — open, awaiting merge
- **PR #51129** (aggregate root metrics) — open, stacked on #50962, approved by galonsky
- **PR #51154** (per-fund sharing dates) — open, stacked on #51129, review feedback addressed
- **PR #51165** (fund-level permissions) — open, 5 commits / 8 files, targets master. Mergeable but blocked on approvals.
- **PR #50989** (factory classmethods refactor) — open, independent

### Frontend (carta-frontend-platform)
- **PR #19928** (strip firm-admin UI from GP view) — open as **draft**, 11 files. Hides PartnerNodeFooter, FundNodeFooter, AssetNodeFooter in CRM view; fixes ErrorView; adds DocumentsTable empty state.

### Merge order
#50962 → #51129 → #51154 can merge sequentially (stacked).
#51165 targets master directly (was rebased off the stack).
#19928 is independent (frontend repo).

## What's next
- **Carried interest on root node** — the last missing MVP feature. Headline GP metric. Scoped to single carry figure on the individual_portfolio root node for v1. The carry calculation lives in the GP Entity carry attribution service. Open question from the status doc: total carry only on root, or per-fund carry from the start?
- **Metrics validation** — verify each node shows correct metrics against the Visual Accounting Test Account spreadsheet (Teamworthy, Old Vine Capital, QED Ventures)
- **Mark cfp #19928 ready for review** once manual QA passes

## Key decisions made
- Sharing date alignment: `information_sharing_date` on `PartnerAccountMetricsService`, not `to_date`
- Fund-level permissions: `view_investments` as single-permission gate, hard prune at `InvestedInRelationshipGraph` before subgraph traversal
- `NAVMetrics.__add__()` derives `ending_nav` from component sums
- MVP target: week of Feb 17, feature-flagged to specific GPs via Flipper + carta_id

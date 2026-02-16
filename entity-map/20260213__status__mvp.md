---
date: 2026-02-13
description: GP Embedded Entity Map status snapshot for product and design stakeholders
repository: fund-admin
tags: [entity-map, gp-embedded, status, mvp, planning]
---

# GP Embedded Entity Map: Status & Release Plan

**Date:** Feb 13, 2026
**Target:** MVP to customers the week of Feb 17

---

## MVP goal

A GP opens their Partner Dashboard and sees an interactive graph of their portfolio: the funds they're in, the GP entities they invest through, and their financial metrics. The graph is filtered to only the funds they have permission to see. The data matches what they see on their portfolio page, and every visible node has coherent, internally consistent data.

The first metric we're building onto the graph is **carried interest accrued**, since it's what GPs see on their dashboard and what they care about most. **Total value** should be straightforward to add after that. The graph needs to respect permissions. The numbers need to be right.

## How we're validating

I'm testing against real customer data using the [Visual Accounting Test Account spreadsheet](https://docs.google.com/spreadsheets/d/1XaTBrn--QZR3MCBNR02DeYLTP8lMnsmUBkVUXx5zsKs/edit?gid=1635741327#gid=1635741327) Greg provided. I've picked a few GPs that seem representative of different portfolio shapes:

- **Teamworthy** | Thomas D. Lehrman
- **Old Vine Capital** | Guillermo Borda
- **QED Ventures** | Alex Taub

If there are specific customers or GP profiles we want to validate against, let me know. Happy to add them.

I don't fully know what the permission model will cause graphs to look like yet. Some GPs may see a subset of their funds, and the graph shape will vary. But matching the surrounding portfolio context and having internally consistent data is the right bar for now.

UI controls like layer selection and date filtering are things I want to include but am deferring until the core graph structure and math are solid.

On the UI cleanup side, I'll be jettisoning things that don't belong in the GP context. There are one or two things I already have in mind, but I've been deep in backend graph code for a while and I'm likely to miss details about panels inside modals inside node cards somewhere in this graph. I'd really appreciate a second pair of eyes here (Brian?) to keep me honest on the frontend surface area.

## What's shipped

Five PRs merged across `fund-admin` and `carta-frontend-platform` since Jan 28:

- [**#49859**](https://github.com/carta/fund-admin/pull/49859) (Feb 3) -- CRM entity-rooted graph views. Given an investor UUID, builds their fund investment graph with IDOR protection and a firmless endpoint.
- [**#50628**](https://github.com/carta/fund-admin/pull/50628) (Feb 11) -- Individual portfolio root node. The GP appears at the top of their graph with personal financial metrics.
- **#19451** (Feb 4) -- CRM entity view support in the Partner Dashboard behind feature flag.
- **#19703** (Feb 10) -- React Flow components for the individual portfolio node type.
- **#19914** (merged Feb 13) -- Feature flag targeting. Passes `carta_id` to Flipper so we can enable the entity map for specific GPs without a broad rollout.

## In review

Three PRs in review, all on the critical path:

- [**#50962**](https://github.com/carta/fund-admin/pull/50962) -- Connects the root node to all of the GP's fund entry points instead of picking one arbitrarily. Galonsky has reviewed the approach ("looks good"), one question to resolve.
- [**#51129**](https://github.com/carta/fund-admin/pull/51129) -- Aggregates root node metrics across all funds and fixes GP partner visibility (the GP's own partner record now shows up in GP Entity nodes). Stacked on #50962. Approved by galonsky.
- [**#51154**](https://github.com/carta/fund-admin/pull/51154) -- Uses per-fund sharing dates for CRM entity view metrics so fund metric dates are consistent with what the GP sees on their portfolio page. Just opened.

Without #50962 and #51129, multi-fund GPs see an incomplete graph with incorrect totals. #51154 ensures the dates on fund metrics match the partner portfolio context.

## Remaining work

**Not started:**
- **Fund-level permissions** -- see below.
- **Carried interest** -- see below.
- **Strip firm-admin-only UI** -- The entity map was built for fund admins. Some firmUuid-dependent components and admin-only controls will look broken in the GP context and need to be removed from our entry point.
- **Metrics validation** -- Verify that each node shows the right metrics and that values are consistent with the portfolio around it.

## Fund-level permissions

The largest remaining piece. Today the endpoint requires all 5 view permissions on every fund in the firm, so most GPs fail this and get a 403. We have a [design proposal](entity-map/20260213-fund-level-permissions-design.md) written up. Here's the short version:

We gate fund visibility on `view_investments`, the most common permission GPs already hold and the one that maps most naturally to what the entity map shows. The view layer queries the permission service for the GP's permitted funds and passes that set into the graph builder. Funds the GP can't see get hard-pruned before we ever fetch node data, so there's no information leakage about fund structure and no wasted DB queries. Root node metrics only aggregate the visible funds, so the numbers match what the GP sees elsewhere in their portfolio.

This only applies to the CRM entity (GP) view. Firm and fund views keep their existing all-or-nothing checks, since partial visibility is a different UX question for admin/CFO users.

Feedback welcome. Is `view_investments` the right bar, or should we consider a different permission?

## Carried interest

Carry is the headline metric for GPs and isn't in the entity map yet. The carry calculation lives in the GP Entity carry attribution service.

I'm owning this. Scoped to a single carry figure on the root node for v1. The carry service API exists and the integration point is well-defined, so this can be parallelized with another engineer if we want to move faster.

**Open question:** Total carry on the root node for MVP, with per-fund carry as a follow-up? Or is per-fund required from the start?

## Feedback needed

- **Permission model** -- I've proposed using `view_investments` as the per-fund gate (see above). Does that feel right, or should we consider a different permission or combination? This is the biggest open design question.
- **Frontend analytics** -- There are existing Snowplow events instrumented for the entity map. We should verify they fire correctly for the GP view. Backend instrumentation is good to have but not blocking launch.

## Post-MVP

- Multi-firm portfolio aggregation
- Tailored GP persona UI
- Historical comparison across quarter-ends
- Dead code cleanup (firm-scoped CRM entity URL)

## Summary

Feature flag targeting just merged. Three PRs in review cover multi-fund correctness (#50962, #51129, galonsky has approved the approach) and date consistency (#51154). After those land: fund-level permissions (largest piece, `view_investments` proposal above), carried interest (scoped, parallelizable), and a UI audit pass where I could use help.

We need feedback on the permission model, a decision on carry scope, and ideally a frontend buddy to help catch UI issues I'm likely to miss. Let me know if there are other test accounts to validate against.

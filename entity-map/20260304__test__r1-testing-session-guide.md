---
date: 2026-03-04
description: Testing session guide for R1 pre-release of the Portfolio Entity Map
repository: fund-admin
tags: [entity-map, testing, r1, pre-release]
---

# Portfolio Entity Map — R1 Testing Session

## Background

The Portfolio Entity Map is a new feature embedded in the Partner Dashboard that gives GPs a visual graph of their investment portfolio. Starting from the investor as the root node, it expands through GP entities, funds, and portfolio companies — with financial metrics at every level. This is our first investor-facing release.

**Feature flags:** `GPE_172_PARTNER_DASHBOARD_R1` (Partner Dashboard) and `GPE_215_CRM_ENTITY_MAP` (entity map section) must both be enabled.

## R1 Scope

R1 delivers the read-only entity map for GP users viewing their own portfolio. Specifically:

- Individual portfolio root node with aggregated commitment, called capital, distributions, and performance multiples (DPI, TVPI, RVPI)
- GP entity and fund nodes showing NAV breakdowns (contributions, fees, unrealized gains, carry, distributions)
- Portfolio company nodes under each fund
- Fund-level permission filtering — only funds the user has `view_investments` AND `view_fund_performance` access to appear
- Carry metrics gated per-fund based on carry info sharing configuration
- As-of date displayed in the response

**Not in R1:** per-fund LP sharing dates (global minimum is used), multi-firm picker, backend instrumentation, historical timeline views.

## Test Data

- **Firm:** Krakatoa Ventures (`186fb573-a22d-4c82-8ad3-3186f9095a41`)
- **Test GP investor:** John Daley (Corporation ID 2470)
- **Test LP/GP hybrid investor:** Dominic Toretto (Corporation ID 2472, portfolio URL `/investors/individual/2472/portfolio/`)

## What to Test

### Graph structure and navigation
- Does the graph render from the individual portfolio root through GP entities, funds, and portfolio companies?
- Are fund-to-fund relationships (feeder → master) represented correctly?
- Do intra-firm investments show as fund-to-fund edges rather than appearing under fund_partners?

### Metrics accuracy
- Do root node metrics (commitment, called capital, distributions, DPI/TVPI/RVPI) look reasonable and consistent with existing portfolio summary numbers?
- Do fund-level NAV components (contributions, management fees, unrealized gains, carry accrued/earned, distributions) align with what you'd expect from the underlying accounting?
- Cross-check a fund's carry numbers against the Portfolio Summary view — they should agree when carry info sharing is configured.

### Permissions
- Do you only see funds you have permission to view? (Roles like `gp_principal` and `audit` should see funds; `fund_admin` and `investments`-only roles should not.)
- Does the graph correctly exclude funds you shouldn't have access to, without breaking the overall structure?

### Carry gate
- For funds where carry info sharing is **not** configured, carry metrics should be suppressed (zeroed out or absent).
- For funds where it **is** configured, carry accrued and carry earned should appear in the NAV components.

### Edge cases and known limitations
- **Sharing date clamp:** All metrics use the earliest `lp_sharing_to_date` across visible funds as a global cutoff. If one fund has a stale date, all fund metrics will be clamped to that date. Flag this if you notice metrics that seem outdated — it's a known issue with a planned follow-up fix.
- **Duplicate GP entity nodes:** Fund II GP may appear twice in the graph due to multiple intra-firm links. Note if you see this.
- **Empty or missing data:** If a fund has no portfolio companies or no partner transactions, does the graph degrade gracefully?

### General UX
- Does the as-of date display clearly?
- Is the graph readable for a firm with 4-5 funds and multiple GP entities?
- Does the feature feel completely absent when the feature flag is off?

## Feedback Format

For each finding, note:
1. **What you observed** (screenshot if possible)
2. **What you expected**
3. **Which investor/fund/node** was involved
4. **Severity:** blocking (can't ship), important (should fix before GA), minor (backlog)

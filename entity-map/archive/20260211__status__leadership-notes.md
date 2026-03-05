---
date: 2026-02-11
description: Status notes on the GP Embedded Entity Map — last two weeks of work, current state, what's not working yet
repository: fund-admin
tags: [entity-map, gp-embedded, status, leadership, in-progress]
---

# GP Embedded Entity Map: Status Update

## Context

The Entity Map is an existing feature in Carta's fund administration platform — an interactive graph that visualizes a firm's entire investment structure: funds, GP entities, portfolios, investors, and the capital flowing between them. The firm-level version is live behind a feature flag, built for CFOs and fund administrators who need to see an entire firm's structure.

GPs don't use that view. GPs are portfolio holders — they come to Carta to see their own position: what funds they're in, through what structures, with what financial exposure. Linking them to a firm-wide entity map doesn't make sense for how they work.

The current work is a **GP-specific version of the entity map, embedded directly in the Partner Portfolio view.** It shows one investor's portfolio as an interactive graph — their funds, GP entities, portfolio companies, and financial metrics — surfaced contextually within the GP's existing workflow.

This is the first "embedded" deployment of the entity map engine. The same graph technology gets reconfigured for a different persona and rendered within a different product surface. The architecture is designed so that other teams can build their own views on top of the same engine.

### Multiple Consumer Teams

The GP Entity team isn't the only consumer. The **LPPA team** is also building entity map views for LP fund-of-funds. They have their own backend and aren't working on the `fund_admin/entity_map` engine directly — but they're a parallel consumer of the entity map frontend and visualization layer. The work we're doing on the GP embedded version is establishing patterns that both teams (and future consumer teams) will use.

## Background: How Carta Fund Permissions Work

Understanding the permissions problem in this project requires understanding how Carta's fund permission model works.

### Per-fund, per-user, per-role

Permissions in fund administration are not firm-level. They're **fund-level**. A GP member gets **roles** assigned to **specific funds** within a firm. Each role carries a set of permission keys.

There are five standard roles:

| Role | View Permissions Included |
|------|--------------------------|
| **Investments** | `view_investments` |
| **Fund Admin** | `view_fund_admin_data`, `view_investments` |
| **Partners** | `view_partners` |
| **Fund Performance** | `view_fund_performance`, `view_fund_admin_data`, `view_investments` |
| **Audit** | `view_general_ledger`, `view_partners`, `view_fund_admin_data`, `view_investments` |

A GP member might have the Investments and Partners roles on Fund A, the Fund Performance role on Fund B, and no access to Fund C — all within the same firm.

### Five view permissions

The entity map shows investments, partners, fund financials, balance sheets, and GL-derived metrics. To prevent partial data exposure, the current entity map endpoints require **all five view permission categories**:

1. `view_investments`
2. `view_partners`
3. `view_fund_performance`
4. `view_general_ledger`
5. `view_fund_admin_data`

### Why most GPs fail this check

The entity map requires all five permissions on **every fund in the firm** (`HasAllViewPermissions`). This is a double gate:

**Gate 1 — Right permissions:** Common GP role combinations are typically missing at least one. A GP with the standard "Edit" level roles (Investments + Partners + Fund Admin + Fund Performance) has 4 of 5 — they're missing `view_general_ledger`. The only role that includes GL access is Audit, which most non-auditor GPs don't have.

**Gate 2 — Right scope:** Even if a GP somehow has all five permissions, they need them on every non-deleted fund in the firm. At a firm with 10 funds, a GP with access to 3 of them fails — the check compares `{3 funds} == {10 funds}` and returns false. It's binary: all or nothing.

Most real GPs fail on at least one gate. This is why the current entity map is effectively staff-only.

## What We've Shipped (Jan 28 - Feb 11)

Five PRs merged to master across two repositories in two weeks:

### Backend (fund-admin) — 2 PRs

**PR #49859 — CRM entity-rooted graph views** (merged Feb 3)

The core question: given a specific investor (a "CRM entity" in our system), show them a graph of their fund investments within a firm.

This is harder than it sounds because GP members usually don't invest directly in funds. Their money flows through GP Entity structures — a legal vehicle that manages the fund. So the system has to:

1. Find the investor's partner records (their positions)
2. Discover that those positions are in GP Entity funds, not main funds
3. Traverse from GP Entity to the main fund it manages
4. Pull in feeder funds and other connected entities
5. Build the graph with financial metrics at each node

What shipped:
- `build_for_crm_entity()` — the investor-rooted relationship graph builder
- Two API endpoints: firm-scoped and firmless (derives the firm from the investor's data)
- IDOR protection and defense-in-depth security verification
- 10 backend integration tests with real database fixtures

What got reworked during review (7 items addressed):
- Replaced over-mocked unit tests with real integration tests
- Fixed an N+1 query in GP entity traversal
- Removed direct Django model access in favor of service abstractions
- Simplified unnecessary parameters

**PR #50628 — Individual portfolio root node** (merged Feb 11)

The first PR gave us the graph, but the investor had no representation of themselves — the graph just started at funds and GP entities. This PR adds an "individual portfolio" root node so the GP sees themselves at the top of their own graph, with personal financial metrics (commitment, called capital, distributions, NAV).

What shipped:
- `IndividualPortfolioNodeBuilder` and `IndividualPortfolioNodeFetcher` — plugged into the existing fetcher pipeline via strategy pattern
- Factory method on `GraphBuilder` that configures the pipeline for investor views without forking the graph-building code
- 11 new CRM entity integration tests (117 total), 207 unit tests passing

What happened during review:
The reviewer (galonsky, senior engineer) pushed back on the original approach — a separate `CrmEntityGraphBuilder` class that wrapped the existing builder. His feedback: this creates a parallel composition layer, fetches data we'd just throw away, and violates dependency inversion. The fix was recognizing that the existing pipeline already supports a strategy pattern for node fetching. We just needed to swap out which fetchers are registered, not create a new builder. The refactored version deletes ~200 lines and adds ~130.

### Frontend (carta-frontend-platform) — 3 PRs

**PR #19451 — CRM entity-rooted view support** (merged Feb 4)

Enabled the entity map in the GP Portfolio behind a feature flag. Added a `CrmEntityView` component, API hook for the new CRM entity endpoint, and routing in `EntityMapContainer` to render the investor view when `crmEntityId` is present.

**PR #19608 — Entity Map Debugger** (merged Feb 5)

A development-only tool for visualizing and debugging Entity Map API responses. Two-panel layout with mock data, custom JSON paste, and direct API explorer. Dev mode only — doesn't ship to production. This has been valuable for testing different graph structures without standing up full test data.

**PR #19703 — Individual portfolio node components** (merged Feb 10)

Added purpose-built React Flow components for the investor portfolio view: a root node renderer for the `individual_portfolio` type (so it doesn't fall through to the default fund renderer) and null-safe fund node handling for the portfolio context.

### How Code Review Shaped the Architecture for Consumer Teams

The review process on PR #50628 had an impact beyond the immediate PR. The original approach — creating a separate `CrmEntityGraphBuilder` — would have established a pattern where every new view type forks the pipeline. If the LPPA team, an accountant view team, and a founder view team each created their own builder class, you'd end up with parallel composition layers that drift apart over time.

The reviewer pushed toward a "configure, don't fork" pattern: the graph-building pipeline stays uniform, and new view types are expressed as fetcher registry configurations. `NodeFetcherService` gets factory classmethods (`default()`, `for_crm_entity()`, and eventually `for_lp()`, `for_accountant()`, etc.) that assemble the right set of fetchers. Consumer teams add their view by registering fetchers and building node types — not by subclassing or wrapping the pipeline.

This means:
- Consumer teams contribute node types and fetchers, not builder forks
- The graph assembly logic stays in one place and improves for everyone
- New views are additive — they don't carry the maintenance burden of a parallel pipeline
- The interface between the engine and consumer teams is the fetcher registry, which is well-defined and testable

## What Doesn't Work Yet

Being direct: if you opened the GP's portfolio view in a browser today, it renders but it's not correct.

**The individual portfolio node shows numbers, but they're wrong.** The root node renders with financial metrics, but the values displayed are incorrect. The backend returns partner-level metrics, but the frontend mapping between the API response fields and the card renderer isn't right. This isn't a $0 display — you see numbers, they're just the wrong numbers.

**The GP's own partner record is missing from the GP Entity's partner list.** When you expand the GP Entity node to see its partners, the GP themselves should appear in that list (they're a partner in the GP Entity fund). Currently they don't. This is a data filtering issue — the partner fetching logic excludes managing members and GPs from the `fund_partners` children, which is correct for the firm-level view (you don't want GP entities in the LP list) but wrong when the GP is the subject of the graph.

**GP Carried Interest isn't there.** This is the number GPs care about most — their share of fund profits above the hurdle rate. It's not in the entity map yet. Carry calculation lives in the GP Entity app's service layer, and the integration hasn't been built. For now, the investor sees commitment, called capital, distributions, and NAV — but not carry.

**Multi-firm support isn't there.** If a GP is invested in funds across multiple firms, the system only shows one firm at a time. The firm-scoped URL shows the correct firm, but there's no aggregated cross-firm portfolio view and no firm picker. The firmless URL picks an arbitrary firm. ~80% of customers are single-firm, so this isn't a blocker for most — but it's an incomplete experience for the rest.

**We have not implemented fund-level permissions.** The current implementation requires all three view permissions (investments, partners, fund performance) to access the entity map at all. The intended design is fund-level permission gating — a GP should see only the funds they have access to within the graph, with inaccessible funds filtered out. This requires a post-fetch permission filter and per-node access checks, which haven't been built.

**No end-to-end dogfooding path.** The backend is functional. The frontend components exist. But the feature flag wiring, the Partner Dashboard entry point, and the full rendering pipeline haven't been tested as a complete flow. The pieces exist independently but aren't connected end-to-end.

## What's Actually Working

The backend pipeline is solid. Given an investor UUID and a firm, the API returns a correct, complete graph with:
- The investor as a root node with their financial metrics
- GP entities they invest through
- Funds those GP entities manage
- Feeder funds and related fund structures
- Portfolio companies within those funds
- Correct metrics at every node (commitment, called capital, distributions, NAV, DPI, TVPI, balance sheets)
- Proper security: firm-scoped access, IDOR protection, no data leakage across firms

For single-firm, single-fund investors — the common case — the graph renders in the frontend with the correct structure. The node card values are wrong, but the graph topology and relationships are right.

The architecture has been through two rounds of serious code review and is in good shape. The strategy pattern for node fetching means adding new view types (LP views, accountant views) is additive — consumer teams register fetchers, they don't fork pipelines.

Test coverage: 117 backend integration tests, 207 unit tests. A development debugger tool for testing graph rendering against arbitrary payloads.

## What's Left Before It's Demoable

1. **Fix individual portfolio metrics mapping** — frontend card renderer needs to read the correct fields from the API response
2. **Fix GP partner visibility** — the GP's own record should appear in the GP Entity partner list when they're the graph subject
3. **End-to-end wiring** — feature flag, Partner Dashboard entry point, full render test as a connected flow

After those three, you'd have something you could show to internal stakeholders.

## What's Left Before Customer Rollout

Everything above, plus:
- Carried interest visualization (headline metric for GPs, requires integration with GP Entity carry service)
- Fund-level permission scheme (per-node access filtering, post-fetch permission checks)
- Multi-firm UX (disable firmless URL or add firm picker)
- Internal dogfooding period
- Select customer rollout with feedback loop

## Deep Dive: The Permissions Problem

As described in the Background section, the entity map currently requires all five view permissions on every fund in the firm — a check that most real GPs fail. This is intentional: the graph builder returns all of the investor's connected funds with no per-user filtering. If we relaxed the permission check without adding data filtering, a GP with access to Fund A but not Fund B would still see Fund B's structure and financial metrics. That's a data leak.

The current posture: rather than show data the user shouldn't see, we block access entirely until we can filter properly.

### What's solved now?

- **Firm-level isolation**: IDOR protection validates the CRM entity belongs to the firm in the URL. A user in Firm A cannot see Firm B's data, period. Defense-in-depth verification at the data layer confirms partner-to-fund-to-firm membership.
- **Staff bypass**: Staff users (like `ian.wessen@carta.com`) pass via `IsStaff`, which is correct for internal use and development.
- **The permission infrastructure exists**: Carta's `FundPermission` model and `PermissionService.list_funds_with_all_permissions_for_firm_and_user()` already return the set of funds a user can access. The plumbing is there — it just isn't wired into the graph builder yet.

### What needs to be built?

Fund-level permission filtering inside the graph builder:

1. Accept the requesting user's ID into the graph builder
2. Query `PermissionService` for the set of funds this user has view access to
3. Filter the graph nodes and edges to only include funds in the allowed set
4. Prune orphaned sub-trees (if a fund is removed, its feeder funds and portfolio companies should also be removed unless they're reachable via another permitted fund)

Once that's in place, the permission class relaxes from `HasAllViewPermissions` to `IsFirmMember` — any firm member can access the endpoint, and the data layer ensures they only see what they're allowed to.

### When does this need to be solved?

**Before any customer rollout.** This is not a nice-to-have — it's a prerequisite. The current "block everyone who isn't staff or a super-permissioned GP" posture is safe but means most real GPs can't access the feature. For internal dogfooding and demos, the current posture works fine.

## Deep Dive: What Would a GP Actually See?

### The current demo is a staff experience

When we demo the entity map as `ian.wessen@carta.com`, we're seeing a staff user's experience. `IsStaff` bypasses every permission check. The graph loads, the data renders, the API responds. This is fine for development and internal testing.

A real GP hitting this feature today would encounter two gates:

**Gate 1: Feature flag.** The frontend checks `GPE_215_CRM_ENTITY_MAP` (via Flipper). If the flag is off for the user, the `EntityMapSection` component returns `null` — the GP sees nothing. No error, no placeholder — the section doesn't render in the Partner Dashboard at all.

**Gate 2: Permissions.** If the flag is on, the frontend makes an API call to the CRM entity endpoint. The backend checks `HasAllViewPermissions | IsStaff`. Most GPs don't hold all five view permissions on every fund in their firm. They'd get a **403 Forbidden** — and the frontend renders a `PermissionDeniedView`.

So realistically: **a GP today either sees nothing (flag off) or gets a permission error (flag on)**. Even if they passed both gates (a GP with unusually broad permissions at a single-fund firm), the experience would be the same graph with the same data — the backend doesn't filter or alter the graph based on who's requesting it. It's the same response whether you're staff or GP.

### What changes before rollout?

1. Feature flag enabled for target customers
2. Permission class relaxed to `IsFirmMember` (after fund-level filtering is implemented)
3. Graph builder filters to the user's permitted funds
4. GP sees only their funds, with correct metrics, in the Partner Dashboard — no permission error, no staff bypass needed

### Impersonation

Staff impersonation exists in the fund-admin platform (`ImpersonateDropdown` / `ImpersonateProvider`), but the entity map views don't have special handling for it. A staff user could impersonate a GP to see permission errors, but impersonation doesn't currently simulate the GP's graph experience because the backend doesn't filter data by user.

## Deep Dive: Metrics and Monitoring

### What exists today

**Frontend: instrumented.** The entity map frontend already has Snowplow analytics via `@carta/fep-analytics`, with ~45 tracking events covering:
- Page/view renders (`EntityMap.FundView`, `EntityMap.CrmEntityView`, `EntityMap.ErrorView`, `EntityMap.PermissionDeniedView`)
- User interactions (layout toggles, layer selections, node search, date filter changes, node card expansions)
- Cross-product navigation (clicks through to Capital Activity, Journals, Schedule of Investments, Partner Rollforward, KYC Dashboard, Asset Tearsheets)

This is a solid foundation. We can already answer "how many people are loading the entity map" and "what are they clicking on" from existing Snowplow events.

**Backend: not instrumented.** The entity map backend has zero analytics — no StatsD counters, no DataDog metrics, no structured logging, no performance tracing. The infrastructure exists (DataDog APM, `ddtrace`, `statsd` via the `fund_admin.common.datadog` helper) and other features in fund-admin use it extensively, but entity map hasn't been wired up.

### What we'd want to track

**Usage (are people using it?):**
- Endpoint hit counts by view type (firm/fund/crm_entity) and by user role (staff vs. GP)
- Unique users and unique firms per week
- Return visits — is the same GP coming back?
- Permission denied rate — how many real GPs are hitting the wall?

**Performance (is it fast?):**
- API response time by endpoint and graph size
- Graph build duration (how long does `build_for_crm_entity` take?)
- Node fetch duration by fetcher type (partner metrics, balance sheets, issuer metrics)
- Graph size distribution (node count, edge count) — are some firms hitting pathological sizes?

**Engagement (is it useful?):**
- Cross-product click-through rate — how often does a user click from an entity map node into a cap table, 409A, or fund financial report?
- Interaction depth — how many nodes does a user expand? Do they use search? Do they change date filters?
- Time on page (if measurable through Snowplow session data)
- Feature layer usage (Financial Reporting overlay, KYC overlay)

**Errors (is it breaking?):**
- Graph build failures
- Frontend rendering errors
- Empty graph responses (valid request but no data)

### When to instrument

Backend metrics should be added before customer rollout — we need performance baselines before real traffic arrives. Frontend analytics are already in place and will start producing data as soon as the feature flag is enabled for users.

## Vision

### Where we are: MVP for simple GPE cases

The immediate goal is a coherent graph for the common case — a GP invested in funds through a single firm. One firm, correct numbers, correct structure, correct relationships. The GP opens their Partner Dashboard, sees a graph of their portfolio, and the data is right.

This is what "demoable" means: a single-firm GP sees themselves at the top of the graph, the GP entities they invest through, the funds those entities manage, and their personal financial metrics. The graph topology is correct. The numbers match what they'd see in their quarterly statements.

### Where we're going: all portfolios, tailored experience

The MVP uses the same graph engine and visualization components as the firm-level entity map — reconfigured, not rebuilt. That's the right starting point, but the GP experience should eventually diverge from the CFO experience in meaningful ways:

**Near-term (post-MVP):**
- Carried interest as the headline metric — this is the number GPs actually think about
- Fund-level permission filtering so any GP can use it, not just super-permissioned ones
- Correct handling of multi-fund investors within a single firm
- Backend performance instrumentation and usage baselines

**Medium-term:**
- Multi-firm portfolio aggregation — a GP sees their full cross-firm exposure in one graph
- Tailored UI for the GP persona — the card layouts, metric hierarchies, and interaction patterns should reflect what GPs care about (carry, distributions, unrealized value) rather than what CFOs care about (balance sheets, GL entries, compliance overlays)
- Historical comparison — portfolio graph at different quarter-ends, showing how exposure has changed over time

**Longer-term:**
- Portfolio analytics layer — concentration risk alerts, vintage diversification, exposure thresholds
- Complex portfolio structures — GPs who invest through multiple vehicles, across fund families, with co-investment positions alongside the main fund
- LP-facing views — white-labeled portfolio graphs that GPs share with their LPs
- API access for institutional reporting

The graph engine and fetcher registry pattern we've built are designed to support this progression. Each new persona or capability is a new set of fetchers and node types, not a new pipeline.

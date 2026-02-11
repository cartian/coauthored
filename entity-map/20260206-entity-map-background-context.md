---
date: 2026-02-06
description: Central background document for the Entity Map project — product vision, architecture, business case, and development context. This is a primary context document for all future entity map development and agent sessions.
repository: fund-admin
context-level: primary
tags: [entity-map, background, product-vision, gp-entity, embedded-entity-map, architecture, permissions, context-document]
---

# Entity Map — Background Document

## What is the Entity Map

The Entity Map is a visual representation of Carta's private capital network. Carta holds a unique dataset spanning company cap tables (capitalization structure and ownership), fund administration services (accounting data), and 409A valuations. Together, this data covers individual companies (assets), private equity firm portfolios and financials, and the documents and relationships connecting assets, funds, and holders.

The Entity Map visualizes this network — using space, position, color, and connection — in ways that condense information far more rapidly than tabular views. It surfaces not only direct involvement but network connections beyond what a table of investments can show.

A useful analogy: **Google Maps for private equity**. Like Google Maps, it provides a wholly new visualization layer over a rich dataset. Unlike Google Maps, where most data is public and the experience appears the same for everyone, much of the Entity Map's data is restricted, sensitive, conditional, or still being finalized by accounting. What gets shown to whom, and when, is a core design challenge.

## Why Private Equity Needs a Map

Private equity is one of the least visually served corners of finance. Public markets have Bloomberg terminals and real-time charting. Private markets have spreadsheets, PDF side letters, and quarterly reports that arrive weeks after period close.

PE's complexity is also inherently graphical. Fund structures — with their feeder vehicles, blocker entities, multiple vintages, LP bases, GP entities, and portfolio companies — form a network, not a table. The most valuable insights are about connections: concentration risk, capital flow paths, overlapping exposure, related-party relationships. These are graph questions that require a graph tool.

The data itself presents unique challenges. Private market data is periodic and often provisional — NAVs are quarterly, valuations are event-driven, accounting may not be finalized at the time of query. A visualization tool for PE must represent data in various states of completeness, which is fundamentally different from mapping a world of settled facts.

And private markets are called "private" for a reason — there is no public ticker, no EDGAR filing, no shared price discovery. Every participant sees only their own slice. An LP knows their commitments but not the full fund capitalization (though large institutional LPs with negotiated information rights may see aggregated performance data and LP lists). A GP knows fund positions but may not see every portfolio company's cap table. A founder knows their cap table but not the fund economics of their investors. This fragmentation means nobody has been able to see the full picture.

**Why now.** Carta sits at the intersection of all three data sources — cap tables, fund accounting, and valuations — for thousands of funds and tens of thousands of companies. No other entity administers the fund, manages the cap table, and performs the valuation under one roof. The Entity Map is the product that makes this convergence visible.

## Carta Context

Carta is a financial technology platform positioned as an **ERP for Private Capital**. The company manages over $4 trillion in total assets on its platform, serves 50,000+ companies and 8,800+ funds and SPVs, and administers $203B+ in fund assets.

Carta's product spans three pillars:

- **Fund Administration** — Carta's flagship product and technology-leading position in emerging and mid-market PE/VC. Full back-office operations for private funds: capital calls, distributions, management fee calculations, K-1 tax preparation, financial reporting, and LP portal access. Carta combines software with professional services (dedicated fund accountants, tax specialists, valuation experts), serving 2,500+ venture capital funds and 650+ private equity firms. This represents Carta's core strength in the emerging manager and growth-stage segments, where automation and integration create competitive advantage over traditional administrators like SS&C and Citco.
- **Equity Management** — Cap table management, scenario modeling, waterfall analysis, equity plan administration, and liquidity solutions for private companies.
- **409A Valuations** — Independent fair market value assessments, a certified valuation provider.

The integration of all three pillars under one platform is Carta's core differentiator. Fund administrators see their portfolio companies' cap tables. Valuations feed directly into fund accounting. The Entity Map draws from data across all three systems, making this integration visible and navigable.

## Origin and History

The Entity Map grew out of internal exploration and whiteboarding sessions within Carta leadership. A dedicated team was assembled from across the organization for a temporary assignment to build it. That team has remained small and lean, with membership shifting over time.

The first version was a prototype built roughly a year ago. It has been worked on continuously since then and has a sophisticated frontend. The original version is a top-level pane in the navigation menu that shows **all** entities within a firm — funds, investors, assets, and their variations (limited partners, general partners, companies, feeder funds, blocker funds, etc.). This was designed as a landing page for the highest-level administrators and fund controllers, such as the CFO of a PE firm's management company.

## Users and Personas

The Entity Map's potential user base spans everyone who uses Carta:

- **Private Equity CFOs** — firm-wide oversight
- **General Partners** — investment decisions, carry, portfolio exposure
- **Fund Accountants and Fund Administrators** — financial reporting and reconciliation
- **Founders** — company-level cap table visibility
- **Limited Partners** — investment positions and fund performance
- **Shareholders and Investors** — holdings and returns
- **Board Members** — governance and strategic oversight

Each persona requires a different view of the graph with finely controlled permissions. The full-firm entity map is currently restricted to staff and the highest-level administrators (users with all three view permissions: investments, partners, and fund performance). Future versions will expose tailored subgraphs to each persona.

## The GP Embedded Entity Map (Current Work)

### What It Is

The current development effort is an **embedded** version of the Entity Map, tailored for General Partners. Rather than living as a top-level navigation page, it is embedded within the existing **Partner Portfolio** view (the `partner_portfolio` app in `carta-frontend-platform`). It shows a simpler, more restricted subgraph: the individual portfolio, the fund structure, and the assets (companies the fund invests in).

This is the first instance of an embedding, but the plan is to leverage the Entity Map across many other parts of the product where similar variations will be employed.

### Why Embedded, Not Filtered

Several factors drove the decision to embed rather than link GPs to the existing full map:

- **Fundamentally different persona and permissions** — a GP's view of the world is different from a CFO's
- **GPs typically only look at their portfolio in Carta** — introducing a separate top-level screen makes no sense for a single view
- **Separate instance, entry point, and graphing layer** gives more control and cleaner encapsulation of the use case

From the user perspective, the embedded map appears contextually within their existing workflow rather than requiring navigation to a separate application. The technical architecture differs through the use of Module Federation with three separate entry points (`./App` for firm views, `./LppaApp` for LP portal views, and `./PortfolioApp` for investor CRM entity views), each with independent initialization and feature flag gating.

### MVP Scope

The MVP must show a coherent graph for a variety of GPs with sensible data:

- The **individual portfolio** (the GP's own position)
- The **fund structure** (the fund and its relationships)
- The **assets** (individual companies the fund invests in)

Not everything originally scoped will be in the MVP. Speed and pragmatism are the priority in the 0-to-1 phase. Specific features cut from the initial MVP include advanced carry visualization with waterfall breakdowns, historical timeline views showing fund evolution, and interactive scenario modeling for hypothetical investments. These remain in the roadmap for future iterations once the core visualization proves its value.

### Carried Interest

Carried interest is the primary compensation mechanism for GPs. The standard structure provides 20% of fund profits above a hurdle rate (typically 8% preferred return), but real-world implementations include numerous variations: catch-up provisions (commonly 80/20 splits allowing GPs to "catch up" to their full 20% share once the hurdle is met), clawback reserves held against future underperformance, and different waterfall structures (deal-by-deal vs. whole fund, American vs. European).

Carry calculation involves tracking hurdle achievement, catch-up zones, crystallization events, and potential clawback obligations — far more nuanced than a simple percentage. The Entity Map's technical implementation captures "Carried interest accrued/earned" as one of 23 NAV components in the `PartnerMetricsWithNAVComponentsMetricsHandler`, though the full complexity of waterfall mechanics is calculated upstream in the accounting layer.

Carry is a supremely important metric for the GP Dashboard. The entity map will eventually visualize carry, including the grant-driven version calculated by the `partner_portfolio` app. This is a later milestone, not MVP.

## Fund Structures Explained

Private equity fund structures appear as entities in the Entity Map with specific relationships:

**Feeder funds** are pass-through vehicles that aggregate capital from specific investor classes (often distinguished by geography or tax status) and feed that capital into a master fund. They appear in the graph as fund nodes connected via investment relationships to the master fund.

**Blocker entities** are corporate structures (typically C-corps or offshore corporations) used to prevent Unrelated Business Taxable Income (UBTI) for tax-exempt investors like university endowments and pension funds. They appear as intermediary nodes between LP investors and the underlying portfolio companies or funds.

**Vintage** refers to the year a fund begins investing, not a separate structural entity. Multiple funds from different vintages may appear in the same firm's Entity Map.

**GP entities** are the management entities that operate the fund — the general partner of record. In the Entity Map architecture, GP entities have their own node type (`gp_entity`) with composite node IDs (`{fund_uuid}_{gp_entity_uuid}`) to prevent cross-contamination when the same management entity operates multiple funds.

Currently, the Entity Map represents six node types: `fund`, `portfolio`, `asset`, `partner`, `gp_entity`, `fund_partners`, and `individual_portfolio`. Feeders and blockers are represented as fund nodes (with potential subtype metadata), not distinct node types in the graph structure.

## Data Freshness and Provisional Accounting

The Entity Map visualizes data that exists in different states of finality. Unlike real-time financial markets, private equity data is:

**Periodic** — NAV calculations occur quarterly, not daily. The system accepts an optional `end_date` parameter for all graph queries, defaulting to the most recent available data.

**Event-driven** — Valuations trigger on funding rounds, not regular schedules. Companies may have valuations from different dates within the same fund portfolio.

**Provisional** — Accounting may not be finalized when the map is queried. Fund administrators distinguish between draft, unaudited, and audited financials. The Entity Map currently does not surface these distinctions visually (there is no "provisional" badge or data freshness indicator in the UI), though the underlying data includes audit status via `FundAuditReport` domain objects in the financial reporting layer.

When accounting adjustments retroactively change values, the graph reflects those changes on subsequent queries. There is no automatic notification to users that previously viewed data has been revised. This is a known limitation — users viewing carry or NAV at one point in time may see different values when they return, with no indication that the data changed versus their memory being imperfect.

The technical implementation uses `audit_flag=False` in journal impact calculations to include unaudited data, and the financial reporting service tracks estimated due dates for annual and quarterly reports. But translating these backend signals into user-facing clarity remains future work.

## Architecture Overview

The entity map backend is a Django app (`fund_admin/entity_map/`) with a layered architecture:

- **Domain models** define graph data structures: `Node`, `Edge`, `Graph`
- **Six node types**: `fund`, `portfolio`, `asset`, `partner`, `gp_entity`, `fund_partners`, `individual_portfolio`
- **Graph builders** construct full or filtered subgraphs from investment relationships
- **Node builders** create individual node types with associated metadata and metrics
- **Metrics handlers** enrich nodes with financial data (commitment, called capital, distributions, DPI, TVPI, RVPI, NAV, balance sheets)
- **A lightweight mode** returns structure without metrics for fast initial loads (~80% faster for structure-only views), with node data fetched incrementally via batch endpoints

The subgraph filtering system (`InvestedInRelationshipGraph`) supports fund-centric, investor-centric, and firm-wide views through bidirectional traversal of investment relationships.

Performance characteristics: Lightweight mode focuses on minimizing initial page load. The architecture uses batch fetching via type-specific fetchers (`FundNodeFetcher`, `GPEntityNodeFetcher`, `PortfolioNodeFetcher`) to avoid N+1 query problems. Absolute query latency depends on firm size and graph complexity, with the system designed to scale to large PE firms with 50+ funds and 500+ portfolio companies, though specific latency benchmarks have not been formally established.

## Permissions Model

Permissions are a defining challenge. The system uses Django REST Framework permission classes in a hierarchical RBAC model: Provider > Firm > Fund.

Key architectural decisions documented in project records:

- **Firm-level gating** (`IsFirmMember | IsStaff`) for future CRM entity views, with current V1 using `HasAllViewPermissions | IsStaff` until fine-grained permission filtering is implemented
- **"Door-and-room" separation** — view permissions are the door lock (can you enter?), service-level filtering determines what you see inside
- **Three-layer IDOR defense** — permission classes at the view level, query-level filtering by firm, and explicit defense-in-depth verification using `FundService.get_fund_id_to_firm_id_map` to ensure entities belong to the correct firm context
- **GP entity node scoping** — composite node IDs (`{fund_uuid}_{gp_entity_uuid}`) prevent unintended cross-contamination between subgraphs

For LP access to shared funds: two LPs in the same fund do not see identical graphs. Each LP sees an investor-rooted view showing only their own positions and metrics. The graph structure may appear similar (same funds, same portfolio companies), but the financial data (capital called, distributions, NAV allocation) is filtered to the requesting LP's partnership interest. This is enforced through the `InvestedInRelationshipGraphBuilder.build_for_crm_entity()` method, which constructs subgraphs rooted at a single investor UUID.

Fund-level permission granularity for the GP embedded version remains an ongoing design decision.

## Team and Stakeholders

- **One engineer** working on the GP embedded version, with significant support from Claude Code (an AI pair programming assistant). This creates meaningful key-person risk and potential technical debt accumulation. The codebase has been developed rapidly with shifting requirements, prioritizing speed over long-term maintainability during the 0-to-1 phase. Scaling to support multiple personas and feature expansion will require team growth or substantial refactoring for sustainability.
- **Two very senior designers** driving the look and feel
- **The original entity map team** remains small and lean, with a close working relationship to the GP Entity team
- **Executive sponsorship** is strong — the CEO, the board, and all executives are excited about this work

## Business Case

### Competitive Position

Carta's competitive position is best understood by segment. Traditional fund administrators (SS&C administers $2+ trillion in alternative assets, with Citco and Apex each managing hundreds of billions) dominate the mega-fund and established PE market through operational scale and institutional relationships. These firms have deep accounting data and decades of industry presence.

Carta competes on **technology leadership and integration** in the emerging manager and growth-stage segments. With $203B under administration across 8,800+ funds and SPVs, Carta's market positioning emphasizes automation, modern software architecture, and the ERP-style integration of fund admin, cap tables, and valuations. This positions Carta as the technology-forward alternative to legacy administrators, not a scale competitor to incumbents.

The Entity Map value proposition depends on cross-product integration. Not all of Carta's 650 PE firm clients use all three services (fund admin, cap table management, and valuations). The percentage of firms with full data convergence is not currently quantified. For customers using only fund administration, the Entity Map can still visualize fund structures, GP entities, and LP relationships, but lacks the portfolio company cap table detail that makes the full graph compelling. The product's strategic value grows with Carta's ability to cross-sell and capture more of each customer's data footprint.

### The Defensibility Question

Could SS&C, Citco, or other incumbents build a similar entity map visualization? Technically, yes. The visualization technology (React Flow, ELK.js for automatic layout) is not proprietary. What creates defensibility is **data integration under one platform**, not visualization innovation alone.

SS&C could partner with or acquire a cap table provider. Juniper Square has fund admin and LP portal data. Allvue has fund accounting and analytics. The Entity Map's moat is not that competitors can't replicate the graph visualization, but that replicating the unified dataset requires either building three distinct product lines in-house or orchestrating complex data-sharing partnerships between independent platforms — both expensive, time-consuming endeavors with integration fragility.

Carta's advantage is structural: the data already exists in one system, maintained by a single engineering organization, with unified data models and permission systems. Competitors face a build-or-integrate decision that Carta has already solved.

However, this moat only holds if customers value integration over best-of-breed tools. If a PE firm prefers Juniper Square's LP portal, SS&C's accounting depth, and Pulley's cap table experience, the Entity Map's integration value becomes moot. The "platform lock-in" flywheel depends on Carta maintaining competitive-or-better standalone products in each category.

### Strategic Value

- **Navigation** — rapid access not just to entities but to Carta products and services: valuations, document stores, financial records, cap tables, and more; a GP can click from their carry summary into the fund, into a portfolio company, into the cap table or its latest 409A, without ever leaving the visual context
- **Comprehension** — a CFO can see the entire firm structure at a glance instead of mentally assembling it from dozens of spreadsheet tabs; an LP can see their exposure across funds and underlying assets in a way no quarterly report provides
- **Decision-making** — concentration risk, co-investment overlap, related-party exposure, and capital flow paths become immediately apparent when rendered as a graph rather than described in footnotes
- **Product adoption** — the map serves as a hub that directs users into deeper Carta products; every node is a doorway into the relevant detail view, increasing engagement across the platform (though baseline engagement metrics for the Partner Portfolio view have not been established, making it difficult to measure incremental impact)
- **Brand and marketing** — a reflection of engineering quality, creativity, and craftsmanship; the kind of product that gets shown in board meetings and partner offsites, generating organic visibility for Carta
- **Platform lock-in** — the more data on the platform, the richer the map; the richer the map, the more indispensable the platform; this is a flywheel that rewards Carta's scale

### Monetization Model

The Entity Map's business model is not currently defined as a standalone revenue driver. It functions as a **retention and expansion play** — a premium experience bundled with existing fund administration contracts to increase platform stickiness and reduce churn.

There is no immediate plan to offer the Entity Map as a paid add-on or separate SKU. The strategic value is assumed to manifest through improved customer retention, higher Net Revenue Retention (NRR) from reduced downgrades, and increased cross-sell success for Carta's other products (particularly cap table adoption among portfolio companies and valuation services).

The total addressable market for "visual entity mapping in private equity" as a standalone category is unknown. This is not a product category that PE professionals have historically requested because the enabling condition (unified fund admin + cap table + valuation data) has not existed before. The Entity Map is a "build it and they will come" bet that assumes latent demand will emerge once the capability is available and demonstrated.

If user research validates strong demand, future monetization options include tiered access (basic graph free, advanced analytics paid), premium features for institutional LPs, or white-labeled entity maps for fund administrators to offer their clients.

### Development Philosophy

The project is in the 0-to-1 phase, optimizing for speed before care. Requirements are shifting. The upside is very high. But the codebase has been developed quickly with changing requirements, so the approach going forward must balance speed with **caution, care, and compassion** for the existing code.

## Rollout

1. Feature flag (current)
2. Internal dogfooding
3. Select customers
4. General availability

## Success Criteria

In six months, success looks like:

**Qualitative goals:**
- **Word of mouth fire in the private equity community** — GPs and CFOs proactively mention the Entity Map in conversations with peers, generating inbound interest
- GPs excited to visit Carta to see their carry numbers update
- A polished, professional, and delightful GP Dashboard experience that visualizes General Partner exposure, value, risk, and involvement

**Clarification on "whimsical"**: The original phrasing "polished, professional, whimsical" requires precision. In the context of a GP Dashboard showing compensation and portfolio risk, "whimsical" means **delightful micro-interactions and thoughtful visual design** — not frivolity. Think: smooth animations when expanding nodes, color-coded visual hierarchies that feel intuitive rather than clinical, and confidence-inspiring data presentation that feels modern and considered. The goal is a product that feels human-designed and pleasant to use, not corporate-sterile, while maintaining absolute seriousness about the financial data being presented.

**Quantified success metrics** (aspirational, not yet measured):
- **Active GP users**: Target 30%+ of eligible GPs access the embedded Entity Map at least once per month
- **Session frequency**: Return usage — GPs who view the map return at least quarterly (aligned with NAV update cycles)
- **NPS impact**: Entity Map users score 10+ points higher on product NPS than non-users
- **Cross-product engagement**: Users who interact with the Entity Map are 2x more likely to click through to portfolio company cap tables or request 409A valuations

These quantitative goals require establishing baseline metrics for Partner Portfolio engagement, which do not currently exist. The success criteria acknowledge that early adoption is qualitative and belief-driven — measurable ROI will come later.

**Ultimate measure:**
- Users who **trust and admire** the Carta product because of what the Entity Map shows them

## Future Vision

The GP embedded version is the first of many. Planned future embeddings include:

- **LP views for fund-of-funds** (the LPPA team is exploring this with their own backend)
- **Accountant views** visualizing their operational scope
- **Founder/company views** showing investor relationships and fund lineage
- **Board member dashboards** with governance-focused graph filters
- **Other persona-specific subgraphs** as the product matures

Each will be a distinct subgraph with its own permissions, entry point, and graphing configuration — all powered by the shared entity map backend.

**Three-year product roadmap** (indicative, not committed):
- **Year 1**: GP embedded map general availability, LP fund-of-funds pilot, baseline metrics collection
- **Year 2**: Founder/company views, accountant operational scopes, advanced carry visualization with waterfall modeling, historical timeline views
- **Year 3**: Predictive analytics layer (concentration risk alerts, exposure thresholds), white-label entity maps for third-party administrators, API access for institutional LPs to pull graph data into their own systems

Engineering investment required: Scaling from one engineer to a sustained 3-4 person team to support multiple personas, reduce technical debt from the 0-to-1 phase, and build the analytics and API layers for institutional use cases.

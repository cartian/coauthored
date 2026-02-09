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

And private markets are called "private" for a reason — there is no public ticker, no EDGAR filing, no shared price discovery. Every participant sees only their own slice. An LP knows their commitments but not the full fund capitalization. A GP knows fund positions but may not see every portfolio company's cap table. A founder knows their cap table but not the fund economics of their investors. This fragmentation means nobody has been able to see the full picture.

**Why now.** Carta sits at the intersection of all three data sources — cap tables, fund accounting, and valuations — for thousands of funds and tens of thousands of companies. No other entity administers the fund, manages the cap table, and performs the valuation under one roof. The Entity Map is the product that makes this convergence visible.

## Carta Context

Carta is a financial technology platform positioned as an **ERP for Private Capital**. The company manages over $4 trillion in total assets on its platform, serves 50,000+ companies and 8,800+ funds and SPVs, and administers $203B+ in fund assets.

Carta's product spans three pillars:

- **Fund Administration** — Carta's flagship product and leading market position. Full back-office operations for private funds: capital calls, distributions, management fee calculations, K-1 tax preparation, financial reporting, and LP portal access. Carta combines software with professional services (dedicated fund accountants, tax specialists, valuation experts), serving 2,500+ venture capital funds and 650+ private equity firms.
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

Each persona requires a different view of the graph with finely controlled permissions. The full-firm entity map is currently restricted to staff and the highest-level administrators. Future versions will expose tailored subgraphs to each persona.

## The GP Embedded Entity Map (Current Work)

### What It Is

The current development effort is an **embedded** version of the Entity Map, tailored for General Partners. Rather than living as a top-level navigation page, it is embedded within the existing **Partner Portfolio** view (the `partner_portfolio` app in `carta-frontend-platform`). It shows a simpler, more restricted subgraph: the individual portfolio, the fund structure, and the assets (companies the fund invests in).

This is the first instance of an embedding, but the plan is to leverage the Entity Map across many other parts of the product where similar variations will be employed.

### Why Embedded, Not Filtered

Several factors drove the decision to embed rather than link GPs to the existing full map:

- **Fundamentally different persona and permissions** — a GP's view of the world is different from a CFO's
- **GPs typically only look at their portfolio in Carta** — introducing a separate top-level screen makes no sense for a single view
- **Separate instance, entry point, and graphing layer** gives more control and cleaner encapsulation of the use case

### MVP Scope

The MVP must show a coherent graph for a variety of GPs with sensible data:

- The **individual portfolio** (the GP's own position)
- The **fund structure** (the fund and its relationships)
- The **assets** (individual companies the fund invests in)

Not everything originally scoped will be in the MVP. Speed and pragmatism are the priority in the 0-to-1 phase.

### Carried Interest

Carried interest is the primary compensation mechanism for GPs — typically 20% of fund profits above a hurdle rate. It is a supremely important metric for the GP Dashboard. The entity map will eventually visualize carry, including the grant-driven version calculated by the `partner_portfolio` app. This is a later milestone, not MVP.

## Architecture Overview

The entity map backend is a Django app (`fund_admin/entity_map/`) with a layered architecture:

- **Domain models** define graph data structures: `Node`, `Edge`, `Graph`
- **Six node types**: `fund`, `portfolio`, `asset`, `partner`, `gp_entity`, `fund_partners`, `individual_portfolio`
- **Graph builders** construct full or filtered subgraphs from investment relationships
- **Node builders** create individual node types with associated metadata and metrics
- **Metrics handlers** enrich nodes with financial data (commitment, called capital, distributions, DPI, TVPI, RVPI, NAV, balance sheets)
- **A lightweight mode** returns structure without metrics for fast initial loads, with node data fetched incrementally

The subgraph filtering system (`InvestedInRelationshipGraph`) supports fund-centric, investor-centric, and firm-wide views through bidirectional traversal of investment relationships.

## Permissions Model

Permissions are a defining challenge. The system uses Django REST Framework permission classes in a hierarchical RBAC model: Provider > Firm > Fund.

Key architectural decisions documented in project records:

- **Firm-level gating** (`IsFirmMember | IsStaff`) for V1 of CRM entity views, with future extensibility for fund-level filtering
- **"Door-and-room" separation** — view permissions are the door lock (can you enter?), service-level filtering determines what you see inside
- **Three-layer IDOR defense** — permission classes at the view level, query-level filtering by firm, and explicit defense-in-depth verification
- **GP entity node scoping** — composite node IDs (`{fund_uuid}_{gp_entity_uuid}`) prevent unintended cross-contamination between subgraphs

Fund-level permission granularity for the GP embedded version is an ongoing design decision.

## Team and Stakeholders

- **One engineer** working on the GP embedded version, with significant support from Claude
- **Two very senior designers** driving the look and feel
- **The original entity map team** remains small and lean, with a close working relationship to the GP Entity team
- **Executive sponsorship** is strong — the CEO, the board, and all executives are excited about this work

## Business Case

### Competitive Position

Nothing else in the market does what the Entity Map does, certainly not with Carta's depth of accounting data. Some entity mapping tools exist, but none are endowed with the financial data that Carta uniquely possesses. This is a **data moat** — Carta has cap table, fund admin, and valuation data in one place. The Entity Map is the visualization layer that makes that moat visible and useful.

Traditional fund administrators (SS&C, Citco, Apex) have deep accounting data but no cap table integration and no modern visualization layer. Cap table tools (Pulley, AngelList) have ownership data but no fund economics. No competitor has the unified dataset required to draw the full graph. The Entity Map is a product that **only Carta can build**.

### Strategic Value

- **Navigation** — rapid access not just to entities but to Carta products and services: valuations, document stores, financial records, cap tables, and more; a GP can click from their carry summary into the fund, into a portfolio company, into the cap table or its latest 409A, without ever leaving the visual context
- **Comprehension** — a CFO can see the entire firm structure at a glance instead of mentally assembling it from dozens of spreadsheet tabs; an LP can see their exposure across funds and underlying assets in a way no quarterly report provides
- **Decision-making** — concentration risk, co-investment overlap, related-party exposure, and capital flow paths become immediately apparent when rendered as a graph rather than described in footnotes
- **Product adoption** — the map serves as a hub that directs users into deeper Carta products; every node is a doorway into the relevant detail view, increasing engagement across the platform
- **Brand and marketing** — a reflection of engineering quality, creativity, and craftsmanship; the kind of product that gets shown in board meetings and partner offsites, generating organic visibility for Carta
- **Platform lock-in** — the more data on the platform, the richer the map; the richer the map, the more indispensable the platform; this is a flywheel that rewards Carta's scale

### Development Philosophy

The project is in the 0-to-1 phase, optimizing for speed before care. Requirements are shifting. The upside is very high. But the codebase has been developed quickly with changing requirements, so the approach going forward must balance speed with **caution, care, and compassion** for the existing code.

## Rollout

1. Feature flag (current)
2. Internal dogfooding
3. Select customers
4. General availability

## Success Criteria

In six months, success looks like:

- **Word of mouth fire in the private equity community**
- GPs excited to visit Carta to see their carry numbers update
- A polished, professional, whimsical GP Dashboard experience that visualizes General Partner exposure, value, risk, and involvement
- Users who **trust and admire** the Carta product because of what the Entity Map shows them

## Future Vision

The GP embedded version is the first of many. Planned future embeddings include:

- **LP views for fund-of-funds** (the LPPA team is exploring this with their own backend)
- **Accountant views** visualizing their operational scope
- **Other persona-specific subgraphs** as the product matures

Each will be a distinct subgraph with its own permissions, entry point, and graphing configuration — all powered by the shared entity map backend.

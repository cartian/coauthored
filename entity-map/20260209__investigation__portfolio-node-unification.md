---
date: 2026-02-09
description: Analysis of the portfolio vs individual_portfolio node types in the entity map — why they're separate, whether they should be unified, and the trade-offs of each approach.
repository: fund-admin
tags: [entity-map, architecture, portfolio, individual-portfolio, crm-entity, design-decision, refactoring]
---

# Portfolio Node Unification Analysis

## Purpose

This document records the current design of two distinct "portfolio" concepts in the entity map — `portfolio` and `individual_portfolio` — and analyzes whether they should remain separate or be unified into a single concept. This is a forward-looking analysis, not a decision. The goal is to preserve context for a future refactoring conversation.

## The Two Portfolio Nodes Today

### `portfolio` — The Fund's Investment Portfolio

A `portfolio` node represents **a fund's collection of investments**. It sits in the middle of the fund-centric hierarchy:

```
Fund → Portfolio → Asset₁, Asset₂, Asset₃ ...
```

**Built by:** `PortfolioNodeBuilder` (`fund_admin/entity_map/node_builders/portfolio_node_builder.py`)

```python
Node(
    id=f"{fund.uuid}_portfolio",            # e.g. "4b6a4f7b-..._portfolio"
    type="portfolio",
    name=f"{fund.name} Portfolio",           # e.g. "Krakatoa Ventures Fund IV Portfolio"
    metadata={
        "fund_carta_id": fund.carta_id,
        "fund_uuid": str(fund.uuid),
        "fund_currency": fund.currency,
    },
    metrics=<aggregated from child asset nodes>,
    children=[asset_node_1, asset_node_2, ...],
)
```

Key behaviors:

- **Node ID** is derived from the fund: `{fund_uuid}_portfolio`
- **Metrics are aggregated upward** from child asset nodes via `sum(node.metrics for node in asset_nodes)`
- **Has children** — each child is an `asset` node representing one issuer/company
- **Name is fund-derived** — "{Fund Name} Portfolio"
- **Appears in** fund entity maps, firm entity maps, and journal impact views

### `individual_portfolio` — The Investor's Holdings

An `individual_portfolio` node represents **a single investor's view of their holdings**. It serves as the **root** of CRM entity (investor) views:

```
Individual Portfolio → GP Entity → Fund → Portfolio → Assets
```

**Built by:** `IndividualPortfolioNodeBuilder` (`fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py`)

```python
Node(
    id=str(crm_entity_uuid),                # e.g. "a2f23ebe-3675-45f7-867e-d3ad5f0effaf"
    type="individual_portfolio",
    name=partner.name,                       # e.g. "John Daley"
    metadata={
        "partner_uuid": str(partner.uuid),
        "partner_type": partner.partner_type,
        "fund_id": partner.fund_id,
        "fund_uuid": str(gp_entity_fund_uuid),
    },
    metrics=<fetched directly for this partner>,
    nav_metrics=<fetched directly>,
    children=[],                             # no children
)
```

Key behaviors:

- **Node ID** is the CRM entity UUID — identifies the investor, not a fund
- **Metrics are fetched directly** from `PartnerMetricsWithNAVComponentsMetricsHandler` for the specific partner
- **Has no children** — it is a leaf node at the top of the graph (a root with no sub-nodes)
- **Name is investor-derived** — the partner's display name
- **Appears only in** CRM entity views (`/entity-atlas/crm-entity/{uuid}/`)
- **Fund partners are excluded** from its graph entirely

## Why They Were Made Separate

### 1. Different Perspectives on the Same Data

The fundamental reason: these nodes answer different questions.

- `portfolio` answers: **"What does this fund hold?"** It's the fund's view of its investments, structured as a container of assets.
- `individual_portfolio` answers: **"What does this investor own?"** It's the investor's view of their position, structured as a root identity node.

These are genuinely different graph traversal starting points. A fund has one portfolio containing many assets. An investor has one position in (potentially) many funds. The topology is different.

### 2. Metrics Flow in Opposite Directions

This is the most technically consequential difference:

- `portfolio` metrics **aggregate upward** from children. The portfolio's total is the sum of all its asset nodes' metrics. The data flows: issuers → assets → portfolio.
- `individual_portfolio` metrics **are fetched directly** and do not aggregate from children. The data flows: `PartnerMetricsWithNAVComponentsMetricsHandler` → individual_portfolio.

The direct-fetch approach for `individual_portfolio` was not an arbitrary choice. It was forced by a concrete problem: **managing members and GPs are excluded from `fund_partners` children** by the `PartnerMetadataFetcher`. This means the standard aggregation path (fund_partners → partner nodes → extract metrics) doesn't work for these partner types. Their metrics have to be fetched through a separate handler.

### 3. Clean Architectural Separation

The `individual_portfolio` node is built by `CrmEntityGraphBuilder`, which composes (not extends) the shared `GraphBuilder`. This keeps CRM-entity-specific logic isolated:

```
EntityMapService
  ├── get_firm_tree()           → uses GraphBuilder directly
  ├── get_fund_tree()           → uses GraphBuilder directly
  └── get_crm_entity_tree()     → uses CrmEntityGraphBuilder
                                    └── composes GraphBuilder internally
```

The `GraphBuilder` has no knowledge of `individual_portfolio`. It never creates one. The CRM builder wraps it and adds the root node on top. This was a deliberate decision to avoid polluting the shared builder with persona-specific logic.

### 4. Different Identity Models

- `portfolio` is identified by **fund** — `{fund_uuid}_portfolio`. There is exactly one per fund.
- `individual_portfolio` is identified by **CRM entity** — the investor's UUID. There is exactly one per investor-in-a-view.

These are fundamentally different identity axes. A fund has one portfolio; an investor has one individual_portfolio per view. The same fund's portfolio might appear in many different graphs, but an individual_portfolio is always the root of exactly one graph.

## Why We Might Unify Them

### 1. They Are Both "A Collection of Investments Belonging to an Entity"

Strip away the implementation details and both nodes represent the same abstract concept: **an entity's portfolio of financial positions**. A fund's portfolio is its collection of assets. An investor's portfolio is their collection of fund positions. The difference is one of scope and perspective, not of kind.

If the entity map is meant to be a general-purpose financial graph, having two separate node types for "portfolio" creates conceptual fragmentation. A single `portfolio` type parameterized by owner (fund vs. investor) could be cleaner.

### 2. Future Personas Will Blur the Line

The background document outlines future embeddings for LPs, founders, accountants, and board members. Each new persona is likely to need their own "root portfolio" concept:

- An LP's portfolio (their positions across multiple funds)
- A founder's portfolio (their equity across cap table events)
- An accountant's scope (the entities they administer)

If each persona gets its own node type (`lp_portfolio`, `founder_portfolio`, `accountant_scope`), the type system will proliferate. A unified `portfolio` type with a `perspective` or `owner_type` field could scale better.

### 3. Simplifies the Frontend Type System

The frontend currently consumes a `NodeTypeEnum` that includes both `portfolio` and `individual_portfolio`. The rendering logic needs to handle both types, even though they are visually similar (both are "portfolio-like" nodes at their respective levels). A unified type could simplify conditional rendering.

### 4. Reduces Domain Model Surface Area

The `NodeType` literal, the `human_readable_node_type` dict, the serializers, the API schema types, and the frontend type enum all carry both types. Unifying them reduces the number of concepts consumers need to understand.

## Why We Might Keep Them Separate

### 1. The Metrics Problem Is Real and Structural

The fact that `individual_portfolio` can't use the same aggregation pattern as `portfolio` is not a cosmetic difference — it reflects a genuine asymmetry in how the data is sourced.

- `portfolio` metrics come from issuer-level data, aggregated through asset nodes.
- `individual_portfolio` metrics come from partner-level data, fetched through a dedicated handler.

Unifying the node type means the `portfolio` concept would need two completely different metrics pipelines depending on context. This is the kind of hidden complexity that creates subtle bugs: "Why does my portfolio node sometimes have children and sometimes not? Why do the metrics sometimes come from aggregation and sometimes from a direct fetch?"

### 2. Identity Semantics Are Genuinely Different

A `portfolio` is identified by its fund. An `individual_portfolio` is identified by its CRM entity. Unifying the type means the `id` field carries different semantics depending on context (`{fund_uuid}_portfolio` vs. `{crm_entity_uuid}`). This makes the ID format unpredictable and harder to reason about.

Node IDs are used for edge construction, graph traversal, and API responses. Inconsistent ID semantics within a single type can cause subtle breakages.

### 3. Graph Topology Is Different

`portfolio` is always a **middle node** with children (assets) and a parent (fund). `individual_portfolio` is always a **root node** with no children and one or more edges to downstream nodes.

Unifying them means the `portfolio` type can be either a root or a middle node, either with or without children, depending on which view you're in. This breaks the implicit invariant that graph topology correlates with node type.

### 4. Separation Protects the Shared Code Path

The `GraphBuilder` is used by multiple views (firm, fund, journal impact). It is well-tested and stable. It produces `portfolio` nodes reliably. The `individual_portfolio` logic lives in `CrmEntityGraphBuilder`, which is newer and still evolving (partner metrics, NAV components, multi-fund support are all recent additions).

Keeping them separate means changes to investor-specific logic can't accidentally break fund views. The composition pattern (`CrmEntityGraphBuilder` wraps `GraphBuilder`) provides a clean blast radius. If we unified the node type, the GraphBuilder itself would need to become aware of investor context, which increases coupling and risk.

### 5. "Premature Abstraction" Risk

We currently have exactly two portfolio-like concepts. The urge to unify is partly driven by the hypothesis that more will follow (LP portfolio, founder portfolio, etc.). But that hypothesis is unvalidated. If those future personas end up having sufficiently different requirements, a premature unification could become a constraint rather than a simplification.

The principle of least power suggests waiting until we have three or more concrete instances before abstracting.

## Possible Unification Approaches

If we do decide to unify, here are three possible approaches, ordered by increasing ambition:

### Option A: Rename Without Restructuring

Change `individual_portfolio` to `portfolio` and use a metadata field (e.g., `portfolio_type: "fund" | "investor"`) to distinguish them. The graph builders remain separate. No metrics changes.

**Pros:** Minimal code change. Frontend gets one type to render.
**Cons:** The underlying architectural split remains. You've papered over the difference with a metadata field.

### Option B: Unified Type with Polymorphic Builders

Define a single `portfolio` node type. Create a `PortfolioNodeBuilder` interface with two implementations: `FundPortfolioNodeBuilder` (current `PortfolioNodeBuilder`) and `InvestorPortfolioNodeBuilder` (current `IndividualPortfolioNodeBuilder`). Graph builders select the appropriate implementation.

**Pros:** Clean polymorphism. Type system is unified. Each builder handles its own metrics pipeline.
**Cons:** Requires reworking the node builder interfaces. The `portfolio` type becomes context-dependent, which can confuse consumers who expect a type to have consistent behavior.

### Option C: Full Graph Abstraction

Rethink the entity map as a generic graph where **every entity has a portfolio** and the graph topology is fully parameterized. Funds, investors, founders, and accountants all produce subgraphs through a common interface. Node types become more generic (e.g., `entity`, `portfolio`, `asset`).

**Pros:** Maximum flexibility. Scales to all future personas.
**Cons:** Massive refactor. Risk of over-engineering. The current architecture works well and is under active development.

## Recommendation

**Keep them separate for now.** The current separation is well-motivated by real technical constraints (metrics aggregation, identity semantics, graph topology). The composition pattern is clean and limits blast radius. Unification can be revisited when:

1. A third portfolio-like node type is needed (e.g., LP portfolio for fund-of-funds).
2. The metrics pipeline is refactored to support a common interface for both fund-level and partner-level fetching.
3. The feature stabilizes enough that refactoring risk is acceptable.

If a third portfolio type does emerge, **Option B** (unified type with polymorphic builders) is the most likely right answer — it preserves the clean separation of metrics pipelines while giving consumers a single type to work with.

## Code References

| Concept | File | Key Lines |
|---------|------|-----------|
| `NodeType` literal | `fund_admin/entity_map/domain.py` | 8-16 |
| `Node` dataclass | `fund_admin/entity_map/domain.py` | 319-348 |
| `PortfolioNodeBuilder` | `fund_admin/entity_map/node_builders/portfolio_node_builder.py` | 61-95 |
| `IndividualPortfolioNodeBuilder` | `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py` | 7-39 |
| `GraphBuilder` (shared) | `fund_admin/entity_map/graph_builder.py` | 34-304 |
| `CrmEntityGraphBuilder` | `fund_admin/entity_map/crm_entity_graph_builder.py` | 26-153 |
| Portfolio node creation in graph | `fund_admin/entity_map/graph_builder.py` | 186-197 |
| Individual portfolio root node creation | `fund_admin/entity_map/crm_entity_graph_builder.py` | 94-103 |
| fund_partners exclusion for CRM views | `fund_admin/entity_map/graph_builder.py` | 83-90 |

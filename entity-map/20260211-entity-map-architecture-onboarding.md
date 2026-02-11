---
date: 2026-02-11
description: Onboarding guide to the Entity Map feature architecture — data flow from API views through graph assembly for fund, firm, CRM entity, and journal impact views
repository: fund-admin
tags: [entity-map, architecture, onboarding, graph-builder, node-fetcher]
---

# Entity Map Architecture Guide

This document traces the full data flow of the Entity Map feature, from API endpoints down to graph assembly. It covers the four view modes (fund, firm, CRM entity, journal impact), the relationship graph, the node fetching pipeline, and key architectural patterns.

## What the Entity Map Does

The entity map visualizes the investment structure of a fund administration firm. It renders a directed graph where nodes represent funds, GP entities, partners, portfolios, and assets, and edges represent investment relationships between them. The frontend receives a `Graph` object (nodes + edges) and renders it visually.

There are four entry points, each showing a different slice of the same underlying data:

| View | Question it answers | Root of graph |
|------|-------------------|---------------|
| **Fund** | "What does this fund's investment structure look like?" | A specific fund and its related funds |
| **Firm** | "What does our entire firm's structure look like?" | All funds in the firm |
| **CRM Entity** | "What does this investor's portfolio look like?" | An `individual_portfolio` root node for the investor |
| **Journal Impact** | "How did this journal entry affect the entity map?" | Same as fund view, but enriched with before/after metrics |

## The Pipeline

Every entity map request flows through the same five-stage pipeline:

```
View → EntityMapService → InvestedInRelationshipGraph → GraphBuilder → NodeFetcherService
                                                              ↓
                                                         Graph (nodes + edges)
```

### Stage 1: API Views

URL patterns are defined in `fund_admin/entity_map/urls.py`.

| Endpoint | View Class | File |
|----------|-----------|------|
| `GET /funds/<fund_uuid>/entity-map/v2` | `EntityMapFundViewV2` | `views/entity_map_fund_view.py` |
| `GET /firms/<firm_uuid>/entity-map/` | `EntityMapFirmView` | `views/entity_map_firm_view.py` |
| `GET /firms/<firm_uuid>/entity-map/crm-entity/<crm_entity_uuid>/` | `EntityMapCrmEntityView` | `views/entity_map_crm_entity_view.py` |
| `GET /funds/<fund_uuid>/entity-map/v2/journal/<journal_gluuid>` | `EntityMapFundJournalImpactView` | `views/entity_map_fund_view.py` |

All views accept a `lightweight` query param. When `true`, the graph returns structure only (no financial metrics), enabling a fast initial page load.

The CRM entity view includes IDOR protection — it validates the CRM entity has Partner records in the specified firm before proceeding.

### Stage 2: EntityMapService

**File:** `fund_admin/entity_map/entity_map_service.py`

The service layer orchestrates the flow. Each view mode maps to a method:

```
get_fund_and_related_funds_tree()  →  builds relationship graph filtered to fund subgraph
get_firm_tree()                    →  builds full firm relationship graph (unfiltered)
get_crm_entity_tree()              →  builds relationship graph from investor perspective
get_journal_impact()               →  builds fund graph, then enriches with journal delta
```

The service creates an `InvestedInRelationshipGraph` (the "what's connected to what" layer), then hands it to a `GraphBuilder` (the "turn that into renderable nodes and edges" layer).

For CRM entity views, it uses `GraphBuilder.create_for_crm_entity()` instead of the default builder — this swaps the node fetcher configuration to exclude aggregated partner nodes and add an investor root node.

### Stage 3: InvestedInRelationshipGraph

**File:** `fund_admin/entity_map/invested_in_relationship_graph.py`

This is the relationship layer. It answers: "which funds invest in which other funds?" It does NOT contain rendered nodes — it's a lightweight graph of fund IDs and their investment relationships.

**Data structure:**

```python
@dataclass
class InvestedInRelationshipGraph:
    investing_fund_id_to_invested_fund_ids: dict[int, list[int]]   # fund A invests in [B, C]
    invested_fund_id_to_investing_fund_ids: dict[int, list[int]]   # fund B receives from [A]
    investment_pair_to_partner_uuid: dict[tuple[int, int], UUID]   # (A, B) → partner UUID
    fund_ids_to_fund: dict[int, FundDomain]                        # all funds in graph
```

The builder (`InvestedInRelationshipGraphBuilder`) has three build methods:

#### `build_for_firm(firm_id)`

Fetches all funds in the firm and all Partner records. Identifies Partners whose `entity_id` matches another fund's UUID — these represent intra-firm investments (e.g., a GP entity fund investing in a main fund). Builds bidirectional mappings of these relationships.

#### `filtered_to_fund_subgraph(fund_id)`

Takes a full firm graph and filters it to only the funds reachable from `fund_id` via BFS traversal. Follows both outgoing (investing) and incoming (receiving investment) edges. Optionally includes funds in the same `fund_family_id`.

#### `build_for_crm_entity(firm_id, crm_entity_uuid)`

Builds the graph from an investor's perspective:

1. Find all Partner records where `entity_id = crm_entity_uuid`
2. For Partners in GP Entity funds, traverse GP Entity → Main Fund (because GP members have Partner records in GP Entities, not directly in the main funds they care about)
3. Build firm graph, filter to subgraphs of all relevant funds, merge them

### Stage 4: GraphBuilder

**File:** `fund_admin/entity_map/graph_builder.py`

The GraphBuilder converts an `InvestedInRelationshipGraph` into a renderable `Graph` with typed nodes and edges. The `build_graph()` method does this in four phases:

#### Phase 1: Collect node identifiers

For each non-GP-entity fund in the relationship graph, create identifiers for:
- `fund` — the fund itself
- `fund_partners` — aggregated view of all partners (excluded in CRM entity views)
- `portfolio` — the fund's portfolio of assets
- `gp_entity` — the GP entity managing the fund (if any)
- `individual_portfolio` — root node for the investor (CRM entity views only)

#### Phase 2: Fetch node data

Pass all identifiers to `NodeFetcherService.fetch_nodes()`, which dispatches to type-specific fetchers and returns populated `Node` objects keyed by ID.

#### Phase 3: Assemble graph

Add nodes and create structural edges:

```
individual_portfolio ──→ gp_entity ──→ fund ←── fund_partners
                                        │            │
                                        ↓        (children)
                                    portfolio    partner nodes
                                        │
                                    (children)
                                    asset nodes
```

- `fund_partners → fund` — partners invest in fund
- `gp_entity → fund` — GP entity manages fund
- `fund → portfolio` — fund owns portfolio
- `individual_portfolio → gp_entity` or `fund` — investor has stake (CRM entity views)

#### Phase 4: Connect fund trees

Create edges between funds that have investment relationships. Edge weight = NAV of the Partner record representing the investment. This connects the separate fund sub-trees into a single connected graph.

### Stage 5: NodeFetcherService

**File:** `fund_admin/entity_map/services/node_fetcher_service.py`

The NodeFetcherService groups identifiers by `node_type` and dispatches to the registered fetcher for that type:

```
NodeFetcherService.fetch_nodes(identifiers)
  ├── "fund"                 → FundNodeFetcher
  ├── "fund_partners"        → FundPartnersNodeFetcher
  ├── "portfolio"            → PortfolioNodeFetcher
  ├── "gp_entity"            → GPEntityNodeFetcher
  └── "individual_portfolio" → IndividualPortfolioNodeFetcher  (CRM entity views only)
```

Each fetcher implements `INodeTypeFetcher.fetch(request) → NodeFetchResponse` and follows the same pattern: parse node IDs → fetch entities → fetch metrics → build nodes via a node builder.

#### Node ID conventions

| Node type | ID format | Example |
|-----------|-----------|---------|
| `fund` | `{fund_uuid}` | `550e8400-...` |
| `fund_partners` | `{fund_uuid}_all_partners` | `550e8400-..._all_partners` |
| `portfolio` | `{fund_uuid}_portfolio` | `550e8400-..._portfolio` |
| `gp_entity` | `{fund_uuid}_{gp_entity_uuid}` | `550e8400-..._660e8400-...` |
| `individual_portfolio` | `{crm_entity_uuid}` | `770e8400-...` |

#### Individual fetcher details

**FundNodeFetcher** — Fetches fund entities, partner metadata (capital accounts), and balance sheets. Each fund gets a `Node` with `metrics`, `nav_metrics`, and `balance_sheet`.

**FundPartnersNodeFetcher** — Fetches all partners for a fund, excluding intra-firm investment partners (those are represented as fund→fund edges instead). Returns a `fund_partners` node whose `children` are individual `partner` nodes.

**PortfolioNodeFetcher** — Fetches portfolio assets (issuers) with metrics. Returns a `portfolio` node whose `children` are individual `asset` nodes.

**GPEntityNodeFetcher** — Fetches GP entity fund data with partner children and optional balance sheet. Uses compound node ID (`fund_uuid_gp_entity_uuid`) because a GP entity can manage multiple funds.

**IndividualPortfolioNodeFetcher** — Fetches investor root node for CRM entity views. Looks up Partner records by `crm_entity_uuid`, resolves the fund, fetches partner metrics. Edge creation from this root to the graph happens later in GraphBuilder (after all other nodes are assembled).

## Builder Configurations

The `GraphBuilder` has factory methods that configure different node fetcher pipelines:

### Default (`GraphBuilder()`)

Full metrics: partner metadata, balance sheets, issuer metrics, GP entity with partner children.

### Lightweight (`GraphBuilder.create_lightweight()`)

Structure only: all metric fetchers replaced with no-op implementations. Used for `?lightweight=true` requests to enable fast initial page load.

| Component | Full | Lightweight |
|-----------|------|-------------|
| Partner metadata | `PartnerMetadataFetcher` | `NoopPartnerMetadataFetcher` |
| Balance sheets | `FundBalanceSheetHandler` | `NoopBalanceSheetHandler` |
| Issuer metrics | `IssuerMetricsHandler` | `NoopIssuerMetricsHandler` |
| GP entity builder | `GPEntityWithPartnerChildrenNodeBuilder` | `GPEntityNodeBuilder` |

### CRM Entity (`GraphBuilder.create_for_crm_entity()`)

Removes `fund_partners` fetcher (no aggregated LP node) and adds `IndividualPortfolioNodeFetcher` for the investor root node. Uses `PartnerMetadataFetcher` with `exclude_gp_and_managing_member=False` to include GP/managing member data in metrics.

## Domain Types

**File:** `fund_admin/entity_map/domain.py`

### Graph

```python
@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
```

### Node

```python
@dataclass
class Node:
    id: NodeIdType
    type: NodeType          # "fund" | "portfolio" | "asset" | "partner" | "gp_entity" | "fund_partners" | "individual_portfolio"
    name: str
    metadata: dict[str, Any]
    metrics: MetricsOverTime | None = None
    nav_metrics: NAVMetrics | None = None
    balance_sheet: SummarizedBalanceSheet | None = None
    children: list[Node] = field(default_factory=list)
```

### Edge

```python
@dataclass
class Edge:
    from_node_id: NodeIdType
    to_node_id: NodeIdType
    weight: Decimal | None = None    # For fund→fund edges: Partner NAV
```

### MetricsOverTime

Point-in-time financial metrics with start/end/change snapshots. Contains `start_metrics`, `end_metrics`, and `change_metrics` dicts mapping metric names to `Decimal` values.

### NAVMetrics

NAV with component breakdown: `ending_nav` total plus `nav_components` dict (contributions, income, etc.).

### SummarizedBalanceSheet

Three-section balance sheet: assets, liabilities, investors' capital. Each section has line items with amounts.

## Key File Index

| File | Purpose |
|------|---------|
| `entity_map/urls.py` | URL routing |
| `entity_map/views/` | API view classes |
| `entity_map/entity_map_service.py` | Service orchestration |
| `entity_map/invested_in_relationship_graph.py` | Fund relationship graph + builder |
| `entity_map/graph_builder.py` | Graph assembly (identifiers → nodes → edges) |
| `entity_map/services/node_fetcher_service.py` | Node fetching pipeline + all fetcher classes |
| `entity_map/node_builders/` | Individual node builder classes |
| `entity_map/domain.py` | Domain types (Graph, Node, Edge, Metrics, etc.) |
| `entity_map/journal_impact/` | Journal impact enrichment |

## Architectural Patterns

**Separation of concerns:** Relationship discovery (which entities are related) is decoupled from node rendering (what data each entity carries). The `InvestedInRelationshipGraph` knows about fund topology; the `GraphBuilder` + `NodeFetcherService` know about node types and metrics.

**Pluggable fetchers:** Node fetchers are registered by type in `NodeFetcherService`. The builder factories (`create_lightweight`, `create_for_crm_entity`) swap fetcher implementations via constructor injection rather than conditional logic.

**Batch fetching:** All nodes are fetched in parallel by type (one call per node type, not one per node). This keeps the number of database round-trips proportional to node types (~5), not node count (could be hundreds).

**Lightweight/full split:** The initial page load uses lightweight mode for fast structure rendering. The frontend can then fetch full metrics for visible nodes on demand.

**Intra-firm investment filtering:** When a fund invests in another fund, the Partner record representing that investment is excluded from the `fund_partners` node (it would be confusing to show "Fund B" as a partner alongside real LPs). Instead, it's represented as a fund→fund edge with the Partner's NAV as the edge weight.

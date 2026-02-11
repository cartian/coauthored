---
date: 2026-02-10
description: Curated walkthrough of the two primary entity map code paths — Firm Tree (core) and CRM Entity (new) — from inbound API request through graph building to JSON response.
repository: fund-admin
tags: [entity-map, architecture, code-walkthrough, crm-entity, graph-builder]
---

# Entity Map Code Path Walkthrough

Two primary code paths serve the entity map feature. Both share the same `GraphBuilder.build_graph()` method and the same `NodeFetcherService` dispatch loop — the behavioral difference is entirely determined by **how NodeFetcherService is configured** and whether a `crm_entity_uuid` is passed.

---

## Core Case: Firm Tree

**Route:** `GET /entity-map/firms/{firm_uuid}/`

**The short version:** View &rarr; EntityMapService &rarr; GraphBuilder (default config) &rarr; NodeFetcherService (all 4 fetchers) &rarr; Graph &rarr; auto-serialized JSON.

### Step 1 — API request enters the View

**`entity_map/views/entity_map_firm_view.py:57-80`** &mdash; `EntityMapFirmView.get()`

This is refreshingly thin. The `@dc_exposed` decorator at line 64 deserializes query params (`end_date`, `lightweight`) into `EntityMapFirmViewQueryParams` and auto-serializes the `-> Graph` return type into JSON. The view does exactly two things:

1. **Line 73-74**: Creates the service — `EntityMapService.factory(lightweight=...)`. If `lightweight=True`, this swaps in Noop handlers for metrics/balance sheets.
2. **Line 77-79**: Calls `entity_map_service.get_firm_tree(firm_id, end_date)` and returns the `Graph`.

### Step 2 — EntityMapService builds the relationship graph

**`entity_map/entity_map_service.py:121-144`** &mdash; `EntityMapService.get_firm_tree()`

Two operations:

1. **Lines 134-137**: Builds the full firm `InvestedInRelationshipGraph` — this is the pre-computed map of "which funds invest in which other funds" and the partner UUIDs representing those relationships. No filtering here; it's the whole firm.
2. **Lines 140-144**: Passes it to `self._graph_builder.build_graph(firm_uuid, invested_in_relationship_graph, end_date)`. Note: **no `crm_entity_uuid`** parameter — this is the key difference from the CRM path.

### Step 3 — GraphBuilder determines structure and collects identifiers

**`entity_map/graph_builder.py:106-164`** (first half of `build_graph`)

The GraphBuilder is constructed with default `NodeFetcherService()` — all 4 fetchers registered (fund, fund_partners, gp_entity, portfolio).

1. **Lines 124-134**: Extracts funds from the relationship graph, filters out GP entity funds (they appear as children, not top-level nodes).
2. **Lines 141-148**: Queries `ManagingEntityLinksService` to find which funds have GP entities attached (the main_fund &rarr; GP entity mapping).
3. **Lines 150-155**: `_collect_node_identifiers()` builds the list of `NodeIdentifier(node_type, node_id)` tuples. For each fund: one `fund` identifier, one `fund_partners` identifier (`{uuid}_all_partners`), one `portfolio` identifier (`{uuid}_portfolio`). Plus one `gp_entity` identifier per fund-to-GP-entity link.

### Step 4 — NodeFetcherService fetches all node data

**`entity_map/services/node_fetcher_service.py:589-628`** &mdash; `NodeFetcherService.fetch_nodes()`

1. **Line 607**: Groups identifiers by type &rarr; `{"fund": [...], "fund_partners": [...], "gp_entity": [...], "portfolio": [...]}`.
2. **Lines 612-626**: For each type, looks up the registered fetcher and calls `fetcher.fetch(sub_request)`. Each fetcher returns a `NodeFetchResponse(nodes_by_id={...})`.

The four fetchers in play:

| Fetcher | Lines | What it does |
|---------|-------|--------------|
| `FundNodeFetcher` | `132-189` | Loads fund domain objects, fetches partner metrics (to aggregate into the fund node), gets balance sheet |
| `FundPartnersNodeFetcher` | `260-337` | Loads partners for each fund, builds child partner nodes with NAV metrics, returns an aggregate `fund_partners` node with children |
| `GPEntityNodeFetcher` | `192-257` | Loads GP entity funds, fetches their partner metadata, builds nodes with balance sheets |
| `PortfolioNodeFetcher` | `340-401` | Loads issuer metrics per fund, builds portfolio nodes with child asset nodes |

### Step 5 — GraphBuilder assembles nodes and edges

**`entity_map/graph_builder.py:166-246`** (second half of `build_graph`)

With all node data back from `NodeFetcherService`, the builder now assembles the `Graph`:

1. **Lines 178-181**: Add fund nodes.
2. **Lines 185-197**: Add `fund_partners` nodes — but only if they have children (or lightweight mode). Creates edges `fund_partners → fund`.
3. **Lines 200-206**: Add GP entity nodes. Creates edges `gp_entity → fund`.
4. **Lines 209-219**: Add portfolio nodes. Creates edges `fund → portfolio`.
5. **Lines 237-244**: `_connect_fund_trees_by_invested_in_relationship()` — adds edges between fund trees based on invested-in relationships, with NAV-based edge weights pulled from the fund_partners children.

Lines 172-175 and 221-235 are skipped — `crm_entity_uuid` is `None`.

### Step 6 — Serialization

Back in the view, the `@dc_exposed` decorator intercepts the `Graph` return value and feeds it through `rest_framework_dataclasses.DataclassSerializer`, which recursively serializes the dataclass tree (Graph &rarr; Nodes &rarr; children, metrics, nav_metrics, balance_sheet; Edges). No manual serializer code.

---

## CRM Entity Case (New)

**Route:** `GET /entity-map/crm-entity/{crm_entity_uuid}/`

**The short version:** View (with IDOR validation) &rarr; EntityMapService &rarr; GraphBuilder (CRM config: no fund_partners fetcher, has individual_portfolio fetcher) &rarr; NodeFetcherService &rarr; Graph &rarr; auto-serialized JSON.

### Step 1 — API request enters the View

**`entity_map/views/entity_map_crm_entity_view.py:37-160`** &mdash; `EntityMapCrmEntityView.get()`

More involved than the firm view because of security concerns:

1. **Lines 148-154**: Firm resolution — if the URL doesn't include a firm identifier, derives it via `_get_firm_uuid_from_crm_entity()` (line 56-84), which traverses CRM Entity &rarr; Partner &rarr; Fund &rarr; Firm.
2. **Lines 156-160**: Delegates to `_get_crm_entity_tree()`.

**`entity_map/views/entity_map_crm_entity_view.py:120-136`** &mdash; `_get_crm_entity_tree()`

1. **Line 127**: `_validate_crm_entity_in_firm()` — the IDOR guard. Verifies the CRM entity actually has partners in the claimed firm by checking the CRM Entity &rarr; Partner &rarr; Fund &rarr; Firm chain (defense-in-depth at lines 112-118).
2. **Lines 129-136**: Creates `EntityMapService.factory(lightweight=...)` and calls `get_crm_entity_tree(firm_id, crm_entity_uuid, end_date)`.

### Step 2 — EntityMapService builds the relationship graph AND creates a CRM-specific GraphBuilder

**`entity_map/entity_map_service.py:146-176`** &mdash; `EntityMapService.get_crm_entity_tree()`

**This is where the two paths diverge at the service level:**

1. **Lines 165-168**: Builds an `InvestedInRelationshipGraph` using `build_for_crm_entity()` instead of `build_for_firm()`. This filters to only funds the CRM entity is invested in.
2. **Line 170**: `GraphBuilder.create_for_crm_entity()` — **not** the default builder.
3. **Lines 171-176**: Calls `build_graph()` with the extra `crm_entity_uuid` parameter.

### Step 3 — The CRM-configured GraphBuilder

**`entity_map/graph_builder.py:84-104`** &mdash; `GraphBuilder.create_for_crm_entity()`

This factory configures a `NodeFetcherService` differently:

```python
crm_node_fetcher = NodeFetcherService(
    exclude_node_types=frozenset({"fund_partners"}),   # no aggregate LP node
    additional_fetchers={
        "individual_portfolio": IndividualPortfolioNodeFetcher(...)  # investor root
    },
)
```

So the fetcher registry for this path is: `fund`, `gp_entity`, `portfolio`, `individual_portfolio`. No `fund_partners`.

### Step 4 — GraphBuilder collects identifiers (with the root node)

**`entity_map/graph_builder.py:248-289`** &mdash; `_collect_node_identifiers(..., crm_entity_uuid=<UUID>)`

**Lines 258-264** — this is the fork point. Because `crm_entity_uuid` is not `None`, it prepends:

```python
NodeIdentifier(node_type="individual_portfolio", node_id=str(crm_entity_uuid))
```

Then the same fund/fund_partners/portfolio/gp_entity identifiers as the core path. The `fund_partners` identifiers are still generated, but they'll be silently dropped by NodeFetcherService because no fetcher is registered for that type.

### Step 5 — NodeFetcherService fetches node data (different fetcher set)

**`entity_map/services/node_fetcher_service.py:589-628`**

Same dispatch loop as the core path, but the registry is different:

| Type | Fetcher | What happens |
|------|---------|--------------|
| `individual_portfolio` | `IndividualPortfolioNodeFetcher` | **New** — fetches investor data |
| `fund` | `FundNodeFetcher` | Same as core |
| `fund_partners` | *(none registered)* | **Skipped** — line 614: `if fetcher is None: continue` |
| `gp_entity` | `GPEntityNodeFetcher` | Same as core |
| `portfolio` | `PortfolioNodeFetcher` | Same as core |

### Step 5a — IndividualPortfolioNodeFetcher (the new fetcher)

**`entity_map/services/node_fetcher_service.py:404-479`**

This is the only fetcher that's unique to the CRM path:

1. **Lines 442-445**: Looks up the partner record for the CRM entity UUID (via `PartnerService`).
2. **Lines 451-453**: Resolves the partner's fund (via `FundService`).
3. **Lines 455-460**: Fetches partner metadata and metrics for that fund — using `PartnerMetadataFetcher(exclude_gp_and_managing_member=False)` because the investor may be a GP/managing member.
4. **Lines 470-477**: Builds the node via `IndividualPortfolioNodeBuilder`, which embeds `fund_uuid` in the node's metadata (this is used later for edge targeting).

### Step 6 — GraphBuilder assembles (with root node and edge targeting)

**`entity_map/graph_builder.py:166-246`** (same method as core, but `crm_entity_uuid` is not `None`)

1. **Lines 172-175**: Adds the `individual_portfolio` root node from `nodes_by_id`.
2. **Lines 178-181**: Fund nodes (same as core).
3. **Lines 185-197**: `fund_partners` loop runs but finds nothing in `nodes_by_id` — the fetcher was excluded, so no nodes were produced. Zero iterations do work here.
4. **Lines 200-206**: GP entity nodes (same as core).
5. **Lines 209-219**: Portfolio nodes (same as core).
6. **Lines 221-235**: **The root edge** — `_find_root_target()` searches the assembled nodes for where to connect the investor. It reads `fund_uuid` from the root node's metadata and:
   - First pass (lines 304-309): looks for a `gp_entity` node whose `fund_uuid` matches — meaning the investor's fund IS a GP entity fund, so connect to the GP entity node.
   - Second pass (lines 311-313): falls back to a `fund` node with a matching ID — meaning the investor is a direct LP in a regular fund.

### Step 7 — Serialization

Same as core — `@dc_exposed` auto-serializes the `Graph` dataclass.

---

## Domain Objects

All defined in **`entity_map/domain.py`**.

### Graph (line 420-450)

```python
@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    nodes_by_id: dict[NodeIdType, Node]  # cached_property
```

### Node (line 318-348)

```python
@dataclass
class Node:
    id: NodeIdType                              # str
    type: NodeType                              # "fund" | "portfolio" | "asset" | "partner" | "gp_entity" | "fund_partners" | "individual_portfolio"
    name: str
    metadata: dict[str, Any]                    # type-specific metadata
    metrics: MetricsOverTime | None             # financial metrics over time
    nav_metrics: NAVMetrics | None              # Net Asset Value components
    balance_sheet: SummarizedBalanceSheet | None
    children: list[Node]                        # child nodes (must not be circular)
```

### Edge (line 410-414)

```python
@dataclass
class Edge:
    from_node_id: NodeIdType
    to_node_id: NodeIdType
    weight: Decimal | None    # e.g. NAV for fund-to-fund invested-in relationships
```

---

## Summary: What makes the two paths different

The entire behavioral difference is determined by **how NodeFetcherService is configured** and whether `crm_entity_uuid` is passed to `build_graph()`.

| Aspect | Firm Tree (Core) | CRM Entity (New) |
|--------|-----------------|------------------|
| **View** | `EntityMapFirmView` | `EntityMapCrmEntityView` (+ IDOR validation) |
| **Service method** | `get_firm_tree()` | `get_crm_entity_tree()` |
| **Relationship graph** | `build_for_firm()` — full firm | `build_for_crm_entity()` — filtered to investor |
| **GraphBuilder factory** | Default `GraphBuilder()` | `GraphBuilder.create_for_crm_entity()` |
| **NodeFetcherService config** | All 4 default fetchers | Excludes `fund_partners`, adds `individual_portfolio` |
| **Root node** | None — multiple fund roots | `individual_portfolio` investor node |
| **fund_partners nodes** | Present (aggregated LP view) | Absent (investor is shown as root instead) |
| **`build_graph()` method** | Same code | Same code (crm_entity_uuid triggers root node + edge) |
| **Serialization** | `@dc_exposed` &rarr; Graph dataclass | Identical |

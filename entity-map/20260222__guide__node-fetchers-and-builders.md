---
date: 2026-02-22
description: Explanation of how node fetchers and node builders work in the entity map pipeline
repository: fund-admin
tags: [entity-map, architecture, fetchers, builders, explainer]
---

# Node Fetchers and Node Builders

The entity map pipeline has a two-phase process for turning empty shells into fully populated graph nodes. **Fetchers** are responsible for getting data from the database. **Builders** are responsible for assembling that data into `Node` objects. Fetchers call builders, never the other way around.

## Node Fetchers

A node fetcher is a class that implements `INodeTypeFetcher` — a single method: `fetch(request: NodeFetchRequest) -> NodeFetchResponse`. Each fetcher is specialized for one node type and knows how to get the right data for that type from the database.

### The interface

```python
class INodeTypeFetcher(metaclass=ABCMeta):
    @abstractmethod
    def fetch(self, request: NodeFetchRequest) -> NodeFetchResponse: ...
```

`NodeFetchRequest` carries:
- `firm_uuid` — scope guard, prevents cross-firm data leakage
- `node_identifiers` — list of `NodeIdentifier(node_type, node_id)` shells to fill
- `end_date` — optional date for metrics calculation
- `invested_in_relationship_graph` — the pre-built fund-to-fund relationship graph

`NodeFetchResponse` returns:
- `nodes_by_id` — a dict mapping node ID to the fully populated `Node`
- `edges` — any edges the fetcher needs to create (some fetchers produce edges as a side effect, e.g. `IndividualPortfolioNodeFetcher` doesn't, but `GPEntityNodeBuilder.build_nodes_and_edges` does)

### The registry

`NodeFetcherService` holds a registry mapping `NodeType` → `INodeTypeFetcher`. When `fetch_nodes()` is called, it groups the identifiers by type and dispatches each group to the right fetcher:

```python
for node_type, identifiers in identifiers_by_type.items():
    fetcher = self._fetchers.get(node_type)
    if fetcher is None:
        continue
    sub_request = NodeFetchRequest(
        firm_uuid=request.firm_uuid,
        node_identifiers=identifiers,
        end_date=request.end_date,
        invested_in_relationship_graph=invested_in_relationship_graph,
    )
    response = fetcher.fetch(sub_request)
    nodes_by_id.update(response.nodes_by_id)
```

The default registry:

| Node type | Fetcher | What it does |
|-----------|---------|-------------|
| `fund` | `FundNodeFetcher` | Loads fund domains, fetches partner metadata via `PartnerMetadataFetcher`, gets balance sheet from GL |
| `gp_entity` | `GPEntityNodeFetcher` | Loads GP entity fund domains, fetches partner metadata for the GP entity |
| `fund_partners` | `FundPartnersNodeFetcher` | Loads fund domains, fetches partner metadata, builds partner child nodes |
| `portfolio` | `PortfolioNodeFetcher` | Loads fund domains, fetches issuer/asset metrics via `IssuerMetricsHandler` |
| `individual_portfolio` | `IndividualPortfolioNodeFetcher` | (CRM entity view only) Looks up all partner records, aggregates metrics across funds |

The registry is configurable — callers pass `fetchers={node_type: fetcher}` to add/replace, or `{node_type: None}` to remove. The CRM entity view uses this to swap out the default `fund_partners` fetcher (removes it) and add the `individual_portfolio` fetcher:

```python
# From GraphBuilder.create_for_crm_entity()
crm_node_fetcher = NodeFetcherService(
    fetchers={
        "fund_partners": None,              # remove — CRM view has no LP bucket
        "individual_portfolio": IndividualPortfolioNodeFetcher(...),  # add
    },
)
```

### What a fetcher actually does

Taking `FundNodeFetcher` as an example — the pattern is always the same:

1. **Parse identifiers** — extract the entity IDs from node ID strings (e.g. `NodeIdParser.parse_fund_id(node_id)` extracts a fund UUID)
2. **Batch-fetch domain objects** — load the fund/entity records from the database in one query (`FundService.get_by_firm_id_and_fund_uuids()`)
3. **Batch-fetch metrics** — call a metrics handler or metadata fetcher to get financial data for all entities at once (`PartnerMetadataFetcher.get_partner_metadata_for_funds()`)
4. **Build nodes** — for each identifier, call a node builder with the domain object and metrics
5. **Return** — `NodeFetchResponse(nodes_by_id=...)`

The key efficiency pattern: fetchers batch their database queries per type (one query for all fund nodes, one metrics call for all funds), rather than N+1 queries per node.

### `IndividualPortfolioNodeFetcher` — the special case

This fetcher is more complex because the `individual_portfolio` root node aggregates data across multiple funds. For each CRM entity:

1. Look up all `Partner` records via `PartnerService`
2. For each partner's fund, check if it's in `invested_in_relationship_graph.fund_ids_to_fund`:
   - **In graph** → include for both edge creation and metric aggregation
   - **Not in graph, GP entity** → resolve via `FundService`, include for edges and metrics
   - **Not in graph, not GP entity** → include UUID for edges only (unpermitted fund)
3. Batch-fetch partner metadata across all included funds
4. Aggregate metrics using `sum()` with `MetricsOverTime.__add__()` and `NAVMetrics.__add__()`
5. Build the root node via `IndividualPortfolioNodeBuilder`

The `fund_uuids` list (all partner funds) goes into node metadata for edge creation by `GraphBuilder._find_root_targets()`. The `all_funds` list (graph-scoped + GP entity funds) drives metric aggregation.

---

## Node Builders

A node builder is a plain class that takes domain objects and metrics and returns `Node` dataclass instances. Builders have no database access — they're pure data transformation. This is the separation of concerns: fetchers own I/O, builders own assembly.

### What a builder does

A builder takes:
- A domain object (e.g. `FundDomain`, `PartnerMetadata`, `IssuerMetadata`)
- Financial metrics (`MetricsOverTime`, `NAVMetrics`, `SummarizedBalanceSheet`)
- Any contextual metadata (fund UUIDs, currency, etc.)

And returns a `Node`:

```python
@dataclass
class Node:
    id: str               # unique identifier (usually a UUID or composite)
    type: NodeType         # "fund", "gp_entity", "partner", etc.
    name: str              # display name
    metadata: dict         # arbitrary key-value pairs for the frontend
    metrics: MetricsOverTime | None
    nav_metrics: NAVMetrics | None
    balance_sheet: SummarizedBalanceSheet | None
    children: list[Node]   # nested nodes (partners inside fund_partners, etc.)
```

### The builders

| Builder | Builds | Key behavior |
|---------|--------|-------------|
| `FundNodeBuilder` | `fund` nodes | Sums partner class metrics into fund-level aggregates. Attaches balance sheet. |
| `GPEntityNodeBuilder` | `gp_entity` nodes | Sums partner metrics and NAV. Attaches balance sheet. Has `build_nodes_and_edges()` for batch creation with edges to parent funds. |
| `GPEntityWithPartnerChildrenNodeBuilder` | `gp_entity` nodes with `children` | Subclass of `GPEntityNodeBuilder`. Builds partner nodes and attaches them as `children` on the GP entity node (not as separate graph nodes). |
| `FundPartnersNodeBuilder` | `fund_partners` nodes | Creates a container node with individual `partner` nodes as `children`. Aggregates metrics across all partners. |
| `IndividualPartnerNodeBuilder` | `partner` nodes | Creates one node per partner with their individual metrics and nav_metrics. |
| `PortfolioNodeBuilder` | `portfolio` nodes | Creates a container node with `asset` child nodes. Delegates to `IndividualAssetNodeBuilder` for children. Aggregates asset metrics. |
| `IndividualPortfolioNodeBuilder` | `individual_portfolio` nodes | Creates the CRM entity root node with aggregated cross-fund metrics and a `fund_uuids` metadata list for edge creation. |

### The aggregation pattern

Several builders aggregate metrics from children using the `sum()` built-in with a `start` value:

```python
metrics = sum(
    (pm.metrics for pm in partner_metadata_list),
    start=DEFAULT_METRICS,   # MetricsOverTime with all zeros
)
nav_metrics = sum(
    (pm.nav_metrics for pm in partner_metadata_list if pm.nav_metrics),
    start=NAVMetrics.empty(),
)
```

This works because `MetricsOverTime.__add__()` and `NAVMetrics.__add__()` are implemented to union keys and sum values. The `start` value provides the identity element.

### The `children` pattern

Some nodes nest other nodes as `children` rather than placing them as separate graph nodes with edges. This is a display decision — the frontend renders children inside the parent's card (e.g. partner rows inside a fund_partners or GP entity node tile).

`GPEntityWithPartnerChildrenNodeBuilder` demonstrates this:

```python
def build_node(self, gp_entity, node_id, end_date, partner_metadata_list=None):
    node_without_children = super().build_node(...)
    children = self._partner_node_builder.build_nodes(...)
    return replace(node_without_children, children=children)
```

The `replace()` call (from `dataclasses`) creates a new node with the children attached. The partners don't appear as separate graph nodes — they're embedded in the GP entity node.

### Node ID conventions

Node IDs encode enough information to identify the entity and its context:

| Node type | ID format | Example |
|-----------|-----------|---------|
| `fund` | `{fund_uuid}` | `a1b2c3d4-...` |
| `gp_entity` | `{fund_uuid}_{gp_entity_uuid}` | `a1b2..._e5f6...` |
| `fund_partners` | `{fund_uuid}_all_partners` | `a1b2..._all_partners` |
| `portfolio` | `{fund_uuid}_portfolio` | `a1b2..._portfolio` |
| `asset` | `{fund_uuid}_asset_{issuer_id}` | `a1b2..._asset_42` |
| `partner` | `{partner_uuid}` | `f7g8h9i0-...` |
| `individual_portfolio` | `{crm_entity_uuid}` | `j1k2l3m4-...` |

`NodeIdParser` handles parsing these back into their components.

---

## How it all fits together

```
GraphBuilder.build_graph()
    │
    ├── 1. Reads fund_ids_to_fund from InvestedInRelationshipGraph
    ├── 2. Creates NodeIdentifier shells for each node type
    ├── 3. Calls NodeFetcherService.fetch_nodes(NodeFetchRequest)
    │       │
    │       ├── Groups identifiers by type
    │       ├── FundNodeFetcher.fetch()        → FundNodeBuilder.build_node()
    │       ├── GPEntityNodeFetcher.fetch()     → GPEntityNodeBuilder.build_node()
    │       ├── FundPartnersNodeFetcher.fetch() → FundPartnersNodeBuilder.build_nodes()
    │       ├── PortfolioNodeFetcher.fetch()    → PortfolioNodeBuilder.build_node()
    │       └── IndividualPortfolioNodeFetcher.fetch() → IndividualPortfolioNodeBuilder.build_node()
    │
    ├── 4. Merges all NodeFetchResponses into nodes_by_id
    ├── 5. Creates edges (fund↔gp_entity, fund↔portfolio, fund↔fund_partners, root↔targets)
    └── 6. Returns Graph(nodes, edges)
```

### Key files

| File | What |
|------|------|
| `entity_map/services/node_fetcher_service.py` | All fetchers + `NodeFetcherService` registry |
| `entity_map/services/domain.py` | `NodeFetchRequest`, `NodeFetchResponse` |
| `entity_map/node_builders/fund_node_builder.py` | `FundNodeBuilder` |
| `entity_map/node_builders/gp_entity_node_builder.py` | `GPEntityNodeBuilder` and subclasses |
| `entity_map/node_builders/partner_node_builder.py` | `FundPartnersNodeBuilder`, `IndividualPartnerNodeBuilder` |
| `entity_map/node_builders/portfolio_node_builder.py` | `PortfolioNodeBuilder`, `IndividualAssetNodeBuilder` |
| `entity_map/node_builders/individual_portfolio_node_builder.py` | `IndividualPortfolioNodeBuilder` |
| `entity_map/graph_builder.py` | Orchestrates the whole pipeline, calls `NodeFetcherService` |

---
date: 2026-02-10
description: Status document for the embedded entity map feature, including multi-firm readiness assessment
repository: fund-admin
tags: [entity-map, crm-entity, status, mvp, multi-firm]
---

# Embedded Entity Map: Project Status

## Executive Summary

The embedded entity map is a graph-based visualization of investment relationships within a GP's fund structure. It provides three main views:

1. **Firm view** — entire firm's entity hierarchy (funds, GP entities, portfolios, partners)
2. **Fund view** — single fund and its related entities
3. **CRM entity (investor) view** — an individual investor's portfolio across funds within a firm

As of the latest commit (`b4e31639f59`), the CRM entity view includes a new `individual_portfolio` root node representing the investor, with their partner-level financial metrics (commitment, called capital, distributions, NAV, etc.). The CRM code path reuses `GraphBuilder` entirely — behavioral differences are achieved by configuring `NodeFetcherService` with a different fetcher registry.

## Architecture

### Module Structure

```
fund_admin/entity_map/
├── domain.py                    # Core types: Node, Edge, Graph, NodeType, metrics
├── entity_map_service.py        # Service layer orchestrating graph construction
├── graph_builder.py             # Graph builder for all view types (configurable per codepath)
├── invested_in_relationship_graph.py  # Fund-to-fund investment relationships
├── partner_metadata_fetcher.py  # Fetches partner metrics (configurable GP/managing member filter)
├── node_builders/               # IndividualPortfolioNodeBuilder, GPEntityNodeBuilder, etc.
├── services/
│   ├── node_fetcher_service.py  # NodeFetcherService + per-type fetchers (strategy pattern)
│   └── domain.py                # NodeFetchRequest, NodeFetchResponse, NodeIdentifier
├── metrics/                     # Balance sheet, issuer, partner, NAV metric handlers
├── journal_impact/              # Journal entry impact visualization
├── financial_reporting/         # Financial reporting layer overlay
├── kyc/                         # KYC layer overlay
└── views/                       # Django REST views (firm, fund, CRM entity, etc.)
```

### Graph Construction Pipeline

Both the core (firm) path and the CRM entity path use the same `GraphBuilder.build_graph()` method. The behavioral difference is driven by how `NodeFetcherService` is configured.

**Core path (firm tree):**
```
EntityMapFirmView.get()
  └─ EntityMapService.get_firm_tree(firm_id, end_date)
       ├─ InvestedInRelationshipGraphBuilder.build_for_firm(firm_id)  → full firm graph
       └─ GraphBuilder().build_graph(firm_uuid, relationship_graph, end_date)
            ├─ _collect_node_identifiers()  → fund, fund_partners, gp_entity, portfolio
            ├─ NodeFetcherService.fetch_nodes()  → all 4 default fetchers
            └─ assemble nodes + edges
```

**CRM entity path:**
```
EntityMapCrmEntityView.get()
  └─ EntityMapService.get_crm_entity_tree(firm_id, crm_entity_uuid, end_date)
       ├─ InvestedInRelationshipGraphBuilder.build_for_crm_entity(firm_id, crm_entity_uuid)
       │     ├─ Find all partners for CRM entity
       │     ├─ Filter funds to the specified firm
       │     ├─ Traverse GP Entity → Main Fund relationships
       │     └─ Build merged subgraphs from connected funds
       │
       └─ GraphBuilder.create_for_crm_entity().build_graph(..., crm_entity_uuid)
            ├─ _collect_node_identifiers()  → individual_portfolio + fund, fund_partners, gp_entity, portfolio
            ├─ NodeFetcherService.fetch_nodes()
            │     ├─ IndividualPortfolioNodeFetcher  → investor root node with metrics
            │     ├─ FundNodeFetcher, GPEntityNodeFetcher, PortfolioNodeFetcher  → same as core
            │     └─ fund_partners identifiers silently skipped (no fetcher registered)
            └─ assemble nodes + edges + _find_root_target() → connect root to GP entity or fund
```

The key configuration in `GraphBuilder.create_for_crm_entity()`:
```python
NodeFetcherService(
    exclude_node_types=frozenset({"fund_partners"}),
    additional_fetchers={"individual_portfolio": IndividualPortfolioNodeFetcher(...)},
)
```

### Node Types

| Type | Description | When Used |
|------|-------------|-----------|
| `fund` | A fund entity | All views |
| `gp_entity` | GP entity managing a fund | All views |
| `portfolio` | Investment portfolio (assets) | All views |
| `fund_partners` | Aggregated LP node with children | Firm/Fund views only |
| `partner` | Individual partner (child of fund_partners) | Firm/Fund views only |
| `individual_portfolio` | Root node for investor view | CRM entity view only |

## What's Been Built (Merged to Master)

### Core Entity Map (FACC-228 through FACC-362)
- Graph builder with fund, partner, GP entity, and portfolio nodes
- Balance sheet metrics, NAV metrics, partner metrics
- Fund family/feeder-master traversal
- Intra-firm investment edge detection and visualization
- Journal impact visualization (before/after metrics on transaction)
- Lightweight mode for fast structural queries

### Firm-Level Features (FACC-310 through FACC-416)
- Full firm tree view with all entities
- Financial reporting layer overlay (report status by fund)
- KYC layer overlay
- Read-only database routing for performance
- GP entity from other firms excluded (security fix, FACC-416)
- Init API for feature configuration

### CRM Entity Views (PR #49859, merged)
- CRM entity-rooted graph views
- URL routes: firm-scoped and firmless (derives firm from CRM entity)
- IDOR validation (CRM entity must belong to specified firm)
- Defense-in-depth firm membership verification
- Fine-grained permission enforcement (HasAllViewPermissions | IsStaff)

### Frontend Integration
- `FARSComponent` wrapper passes `firmUuid` and `crmEntityId` props to the federated entity map module
- Entity map itself is a separate microfrontend (`entityMap` scope)

## Current PR: GPE-263 (In Review)

**Branch:** `gpe-263.cartian.crm_entity_map_response_follow_up`
**PR:** [#50628](https://github.com/carta/fund-admin/pull/50628)
**Latest commit:** `b4e31639f59`

### Changes (after refactoring per review feedback)

The original PR introduced a `CrmEntityGraphBuilder` that composed `GraphBuilder` with investor-specific logic. Reviewer feedback (galonsky) identified that this created a parallel composition layer with tight coupling, wasteful queries (fund_partners fetched then discarded), and DIP violations. The refactored approach:

1. **Deleted `CrmEntityGraphBuilder`** (~200 lines removed) — no separate builder class
2. **New `IndividualPortfolioNodeFetcher`** in `node_fetcher_service.py` — consolidates all CRM entity data fetching (partner lookup, fund resolution, metrics) into the existing `INodeTypeFetcher` strategy pattern
3. **`NodeFetcherService` configuration** — new `exclude_node_types` and `additional_fetchers` parameters allow per-codepath fetcher registry customization without modifying the dispatch loop
4. **`GraphBuilder.create_for_crm_entity()`** — factory that configures `NodeFetcherService` with no `fund_partners` fetcher + an `individual_portfolio` fetcher
5. **Minimal `GraphBuilder` additions** — `crm_entity_uuid` parameter, root node identifier collection, and `_find_root_target()` for edge assembly (~30 lines of graph-assembly logic)
6. **Simplified `EntityMapService.get_crm_entity_tree()`** — from ~40 lines to ~15 lines

**Net delta:** +210 / -280 = **-70 lines**

### Design Decisions

- **Why edge targeting stays in GraphBuilder:** The root edge (individual_portfolio → GP entity or fund) depends on which GP entity nodes exist in the final graph. This is a graph-assembly concern, not a data-fetching concern. An earlier attempt to put this in the fetcher using `ManagingEntityLinksService` failed because that service maps main_fund → GP entity (one direction), and can't reverse-lookup from a GP entity fund back to the main fund.
- **Why `exclude_node_types` over Noop fetchers:** Removing the fetcher from the registry entirely means zero queries execute — not even Noop overhead. The `fund_partners` identifiers generated by `_collect_node_identifiers()` are silently skipped at dispatch time.
- **Why `additional_fetchers` dict over named parameters:** Avoids modifying `NodeFetcherService.__init__()` signature each time a new node type is introduced. More DI-compliant.

### Known Limitation (Documented in PR)
The node card in the graph UI currently shows balance sheet fields ($0) instead of partner metrics. The metrics **are correctly returned by the API** and display in the click-in modal. This is a **frontend mapping issue** for the new `individual_portfolio` node type.

### Test Coverage
- **Backend integration tests:** 117 passing (includes 11 CRM entity tests covering: basic graph, individual_portfolio node, end_date filtering, LP investors, multi-fund investors, feeder-master structures, cross-firm exclusion, accurate fund metrics, related fund traversal via GP entity)
- **Unit tests:** 207 passing (IndividualPortfolioNodeBuilder, GraphBuilder, NodeFetcherService, etc.)
- **Validation:** ruff format clean, ruff check clean, 1 non-blocking ty diagnostic (known `dict.pop` false positive)

## Multi-Firm Readiness Assessment

### How Firm Scoping Works Today

Every entry point into the entity map is **scoped to a single firm**:

1. **`EntityMapService.get_crm_entity_tree(firm_id, ...)`** — single firm_id parameter
2. **`InvestedInRelationshipGraphBuilder.build_for_crm_entity(firm_id, ...)`** — fetches all CRM entity partners, then filters: `funds_in_firm = {fid: fund for fid, fund in funds.items() if fund.firm_id == firm_id}`
3. **`IndividualPortfolioNodeBuilder.build_node(partner, ...)`** — uses a single partner record (from one fund in one firm) for the root node

### Behavior for Multi-Firm Investors

When a CRM entity is invested in funds across multiple firms:

| Scenario | Behavior | Correct? |
|----------|----------|----------|
| Firm-scoped URL (`/firm/<firm_uuid>/entity-map/crm-entity/<crm_uuid>/`) | Shows only that firm's investments | Yes |
| Firmless URL (`/entity-map/crm-entity/<crm_uuid>/`) | Derives firm from first partner's fund (arbitrary) | Partially — shows correct data for whichever firm is resolved, but doesn't show all firms |
| Aggregated cross-firm view | Not implemented | N/A |

### What Multi-Firm Investors Would See

For a GP invested in **Firm A** (3 funds) and **Firm B** (2 funds):

- **Via firm-scoped URL for Firm A:** Graph shows `individual_portfolio → GP Entity A → Fund 1, Fund 2, Fund 3` with correct metrics. This is complete and accurate for Firm A.
- **Via firm-scoped URL for Firm B:** Graph shows `individual_portfolio → GP Entity B → Fund 4, Fund 5` with correct metrics. This is complete and accurate for Firm B.
- **Via firmless URL:** One of the above, depending on which partner record is returned first. **The data shown is correct, but the user has no way to switch to the other firm.**

### Explicit Test Evidence

The codebase already tests for this scenario:

- `test_get_crm_entity_tree_excludes_other_firm_funds` — creates a CRM entity in two firms, verifies only the queried firm's fund appears
- `test_build_for_crm_entity_filters_to_single_firm` — comment says "CRM entity has partners in multiple firms, but **V1 filters to single firm**"

This is a **known, tested, intentional V1 limitation**.

### Risks for Multi-Firm Release

| Risk | Severity | Affected Users |
|------|----------|----------------|
| **Firmless URL picks arbitrary firm** | Medium | Multi-firm GPs using firmless URL |
| **No cross-firm aggregation** | Low (feature gap, not a bug) | Multi-firm GPs wanting total portfolio view |
| **Metrics only for one firm's partner** | Low (correct per-firm, just incomplete) | Multi-firm GPs |

### Recommendation

**The current implementation is safe and correct for single-firm GPs and can be released as an MVP.**

For multi-firm GPs (<20% of customers), the behavior is:
- **Not broken** — they see accurate data for whichever firm context they're in
- **Incomplete** — they see one firm at a time, not an aggregated view
- **The main risk** is the firmless URL endpoint, which could show an arbitrary firm's data

**Mitigation options for multi-firm before release:**
1. Ensure the CRM entity view is always accessed via the firm-scoped URL (so users explicitly choose which firm context they're in)
2. Or disable the firmless URL route for now

**Multi-firm portfolio aggregation can be safely deferred** to a post-release iteration.

## Learnings from Code Review

The initial implementation created a `CrmEntityGraphBuilder` that wrapped `GraphBuilder` — a "safe via duplication" approach. Review feedback identified three problems with this pattern:

1. **DIP violation:** `CrmEntityGraphBuilder` reached into `GraphBuilder` internals and depended on its output structure rather than configuring behavior through the existing abstractions.
2. **Wasteful queries:** The original `GraphBuilder` still fetched `fund_partners` data (expensive partner + metrics queries), which `CrmEntityGraphBuilder` then discarded.
3. **Scattered data fetching:** Partner lookup and metrics fetching for the investor lived in `EntityMapService` and `CrmEntityGraphBuilder` instead of in `NodeFetcherService` where all other node data fetching is consolidated.

The fix was to recognize that `NodeFetcherService` already implements a **strategy pattern** (fetcher registry keyed by node type). Adding a new view type = adding/removing fetchers from the registry, not creating a new builder class. This "configure, don't fork" approach keeps the graph-building pipeline uniform while allowing arbitrary per-codepath behavior via DI.

## Open Items / Tech Debt

1. **Frontend node card mapping** — `individual_portfolio` shows $0 in node card (metrics work in modal)
2. **Permission relaxation** — TODO to move from `HasAllViewPermissions` to `IsFirmMember` once fine-grained permission filtering is added
3. **GPE-215: GP entity query duplication** — `ManagingEntityLinksService` is queried in `GraphBuilder.build_graph()` for every codepath; the CRM entity path could potentially reuse data from the relationship graph
4. **Multi-firm aggregation** — future work to show cross-firm portfolio view
5. **Firmless URL firm derivation** — `_get_firm_uuid_from_crm_entity` comment says "All partners should be in the same firm" which is incorrect for multi-firm investors

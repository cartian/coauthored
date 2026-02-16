---
date: 2026-02-10
description: Research on moving partner_metrics_handler from EntityMapService into the GraphBuilder/NodeFetcherService layer per galonsky's PR review feedback
repository: fund-admin
tags: [entity-map, refactor, architecture, pr-review]
---

# Moving `partner_metrics_handler` from EntityMapService to the Builder Layer

## Context

PR #50628 added `partner_metrics_handler: IPartnerMetricsHandler | None = None` to
`EntityMapService.__init__()` (line 42). @galonsky flagged two review comments:

1. **On `crm_entity_graph_builder.py`**: "This feels a bit fragile... would it be possible
   to configure GraphBuilder/NodeFetcherService with this behavior instead? Take a look at
   how `GraphBuilder.create_lightweight` works. I think you could do something similar where
   you can inject dependencies that tell it to: not create fund_partners nodes, create
   individual partner nodes."

2. **On `entity_map_service.py:42`**: "I think this should happen inside NodeFetcherService."

## Architecture Overview

```
EntityMapService                        (orchestrator - picks which builder to use)
  |
  +-- GraphBuilder                      (determines graph structure: which nodes + edges)
  |     |
  |     +-- NodeFetcherService          (fetches actual node data by type)
  |           |
  |           +-- FundNodeFetcher       (uses PartnerMetadataFetcher)
  |           +-- GPEntityNodeFetcher   (uses PartnerMetadataFetcher)
  |           +-- FundPartnersNodeFetcher (uses PartnerMetadataFetcher)
  |           +-- PortfolioNodeFetcher  (uses IssuerMetricsHandler)
  |
  +-- CrmEntityGraphBuilder             (wraps GraphBuilder for CRM entity views)
        |
        +-- GraphBuilder                (with excluded_node_types={"fund_partners"})
        +-- IndividualPortfolioNodeBuilder
```

### The Dependency Injection Pattern (`create_lightweight`)

`GraphBuilder.create_lightweight()` configures `NodeFetcherService` with noop handlers:

```python
@staticmethod
def create_lightweight() -> "GraphBuilder":
    lightweight_node_fetcher = NodeFetcherService(
        issuer_metrics_handler=NoopIssuerMetricsHandler(),
        balance_sheet_handler=NoopBalanceSheetHandler(),
        partner_metadata_fetcher=NoopPartnerMetadataFetcher(),
        gp_entity_node_builder=GPEntityNodeBuilder(
            balance_sheet_handler=NoopBalanceSheetHandler(),
        ),
    )
    return GraphBuilder(node_fetcher_service=lightweight_node_fetcher, is_lightweight=True)
```

This is the pattern galonsky wants us to follow: **configure behavior via dependency injection
at the NodeFetcherService level**, not by adding special-case logic in EntityMapService.

## The Problem

### Why `partner_metrics_handler` Ended Up in EntityMapService

The `individual_portfolio` node needs metrics for the investor's partner record.
`PartnerMetadataFetcher` (line 61 of `partner_metadata_fetcher.py`) calls:

```python
all_partners = self._partner_service.list_domain_objects(
    fund_ids=fund_ids, exclude_gp_and_managing_member=True  # <-- HARDCODED
)
```

This filters out GPs and managing members, which is correct for `fund_partners` node
aggregation (those partners aren't "limited partners"). But CRM entity views need
metrics for ALL partner types, including GPs and managing members.

So `EntityMapService._fetch_partner_metadata_for_crm_entity()` was created to bypass
`PartnerMetadataFetcher` entirely, calling `IPartnerMetricsHandler` directly with a
single partner. This works but puts the dependency in the wrong layer.

### Why This Is Fragile

- `EntityMapService` is an orchestrator. It should pick which builder to use and pass
  high-level context, not know about partner type filtering rules.
- The `partner_metrics_handler` dependency is duplicated: both in `EntityMapService`
  and inside `NodeFetcherService.PartnerMetadataFetcher`.
- Making `EntityMapService` aware of partner metadata internals creates coupling
  that makes the code harder to change.

## Recommended Approach

### Make `PartnerMetadataFetcher` Configurable + Inject into `CrmEntityGraphBuilder`

**Key insight**: The fund/gp_entity nodes should continue using the standard fetcher
(exclude GPs). Only the `individual_portfolio` node needs a non-excluding fetcher.
So we can't just swap the NodeFetcherService's fetcher globally.

#### Changes:

1. **`PartnerMetadataFetcher`**: Add `exclude_gp_and_managing_member` constructor param
   ```python
   class PartnerMetadataFetcher(IPartnerMetadataFetcher):
       def __init__(self, ..., exclude_gp_and_managing_member: bool = True):
           self._exclude_gp_and_managing_member = exclude_gp_and_managing_member
   ```

2. **`CrmEntityGraphBuilder`**: Accept a `partner_metadata_fetcher` dependency
   ```python
   class CrmEntityGraphBuilder:
       def __init__(self, ..., partner_metadata_fetcher: IPartnerMetadataFetcher | None = None):
           self._partner_metadata_fetcher = (
               partner_metadata_fetcher
               or PartnerMetadataFetcher(exclude_gp_and_managing_member=False)
           )
   ```

3. **`CrmEntityGraphBuilder.build_graph()`**: Fetch partner metadata internally instead
   of receiving it as a parameter
   - Accept `partner` + `partner_fund` + `end_date` instead of `partner_metadata`
   - Call `self._partner_metadata_fetcher.get_partner_metadata_for_funds()` to get metrics

4. **`EntityMapService`**:
   - Remove `partner_metrics_handler` from `__init__()` (line 42)
   - Remove `_fetch_partner_metadata_for_crm_entity()` method
   - Simplify `get_crm_entity_tree()` to pass partner + fund to builder

#### Why This Approach

- Follows the `create_lightweight` pattern: behavior is configured via dependency injection
- The builder layer owns the "how to fetch data" logic, not the orchestrator
- No change to fund/gp_entity node fetching behavior
- `EntityMapService` stays a thin orchestrator
- Minimal surface area change; easy to review

### Alternative: Add `individual_portfolio` Node Type to NodeFetcherService

A deeper refactoring could register `individual_portfolio` as a node type in
`NodeFetcherService` with its own `IndividualPortfolioNodeFetcher`. This would
make it fully consistent with how other nodes are fetched, but:

- Requires extending `NodeFetchRequest` with CRM-specific context
- The fetcher would duplicate partner/fund lookups already done in `EntityMapService`
- Higher complexity for the same behavioral outcome
- Could be done as a follow-up if the architecture evolves that way

## Files to Modify

| File | Change |
|------|--------|
| `fund_admin/entity_map/partner_metadata_fetcher.py` | Add `exclude_gp_and_managing_member` param |
| `fund_admin/entity_map/crm_entity_graph_builder.py` | Accept `partner_metadata_fetcher`, fetch metadata in `build_graph()` |
| `fund_admin/entity_map/entity_map_service.py` | Remove `partner_metrics_handler`, simplify `get_crm_entity_tree()` |
| `tests/backend/fund_admin/entity_map/test_entity_map_service.py` | Update CRM entity tree tests |
| `tests/backend/fund_admin/entity_map/test_crm_entity_graph_builder.py` | Update builder tests |

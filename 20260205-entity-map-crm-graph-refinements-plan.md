---
date: 2026-02-05
description: Implementation plan for refining CRM entity graph code before PR, addressing test quality, service complexity, and extensibility
repository: fund-admin
tags: [entity-map, crm-entity, code-review, implementation-plan, refactoring]
---

# Entity Map CRM Graph Refinements

## Overview

This plan addresses refinements identified during code review of the `gpe-263.cartian.crm_entity_map_response_follow_up` branch. The changes introduce `CrmEntityGraphBuilder` and `IndividualPortfolioNodeBuilder` to support CRM entity (investor) portfolio views in the Entity Map.

**Branch:** `gpe-263.cartian.crm_entity_map_response_follow_up`
**Files Changed:**
- `fund_admin/entity_map/crm_entity_graph_builder.py` (new)
- `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py` (new)
- `fund_admin/entity_map/entity_map_service.py` (modified)
- `fund_admin/entity_map/domain.py` (modified)
- `tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py` (new)
- `tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py` (new)
- `tests/backend/fund_admin/entity_map/test_entity_map_service.py` (modified)

---

## Task 1: Add `autospec=True` to Unit Test Mocks

**Estimated Effort:** 5 minutes
**Files:** `tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py`

### Problem

The unit tests for `CrmEntityGraphBuilder` use `spec=GraphBuilder` when creating mocks:

```python
mock_graph_builder = mocker.MagicMock(spec=GraphBuilder)
```

While `spec=` validates that only attributes present on `GraphBuilder` are accessed, it does **not** validate method call signatures. This means a test could pass even if the production code calls `build_graph()` with incorrect arguments.

### Why This Matters

The fund-admin `CLAUDE.md` explicitly requires `autospec=True` for mocks:

> When mocks are required, use `autospec` to ensure the component is accurately mocked

Using `autospec=True` creates a mock that:
1. Only allows access to attributes/methods that exist on the real class
2. Validates that method calls match the real method's signature
3. Fails fast if the interface changes (e.g., if `GraphBuilder.build_graph()` adds a required parameter)

### Implementation

In `test_crm_entity_graph_builder.py`, update all mock creations:

```python
# Before
mock_graph_builder = mocker.MagicMock(spec=GraphBuilder)

# After
mock_graph_builder = mocker.MagicMock(autospec=GraphBuilder)
```

This change affects approximately 6 test methods in the file.

### Verification

```bash
poetry run pytest tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py -v
```

---

## Task 2: Extract Partner Metadata Fetching Logic

**Estimated Effort:** 15 minutes
**Files:** `fund_admin/entity_map/entity_map_service.py`

### Problem

The `get_crm_entity_tree()` method in `EntityMapService` is ~70 lines and handles 6 distinct responsibilities:

1. Fetch partner records for the CRM entity
2. Get the partner's fund
3. Fetch partner metrics (bypassing the normal fetcher to include managing members)
4. Build the invested-in relationship graph
5. Construct the `CrmEntityGraphBuilder`
6. Call `build_graph()` and return

This violates the Single Responsibility Principle and makes the method harder to understand, test, and modify.

### Why This Matters

The partner metadata fetching logic (step 3) is particularly complex:

```python
# Fetch partner metrics directly. Managing members and GPs are excluded
# from fund_partners children by PartnerMetadataFetcher, so we use the
# metrics handler directly to include all partner types.
partner_metrics_handler = PartnerMetricsWithNAVComponentsMetricsHandler()
partner_metadata_by_fund = (
    partner_metrics_handler.get_partner_metadata_for_funds(
        funds=[partner_fund],
        all_partners=[partner],
        end_date=end_date,
    )
)
partner_metadata = partner_metadata_by_fund.get(partner.fund_id, {}).get(
    str(partner.uuid)
)
```

This logic:
- Has an important comment explaining *why* we bypass the normal fetcher
- Performs nested dictionary lookups that could fail silently
- Is specific to the CRM entity use case (managing members need their metrics)

Extracting this into a named method makes the intent clearer and the main method easier to follow.

### Implementation

Add a private method to `EntityMapService`:

```python
def _fetch_partner_metadata_for_crm_entity(
    self,
    partner: PartnerDomain,
    partner_fund: FundDomain,
    end_date: date | None,
) -> PartnerMetadata | None:
    """Fetch partner metrics directly for CRM entity views.

    The standard PartnerMetadataFetcher excludes managing members and GPs
    from fund_partners children (they're not "limited" partners). However,
    for CRM entity views we need the investor's own metrics regardless of
    partner type. This method bypasses that exclusion.

    :param partner: The partner record for the CRM entity.
    :param partner_fund: The fund the partner is invested in.
    :param end_date: Optional end date for metrics calculation.
    :returns: PartnerMetadata with metrics, or None if not found.
    """
    partner_metrics_handler = PartnerMetricsWithNAVComponentsMetricsHandler()
    partner_metadata_by_fund = partner_metrics_handler.get_partner_metadata_for_funds(
        funds=[partner_fund],
        all_partners=[partner],
        end_date=end_date,
    )
    return partner_metadata_by_fund.get(partner.fund_id, {}).get(str(partner.uuid))
```

Then update `get_crm_entity_tree()` to use it:

```python
partner_metadata = self._fetch_partner_metadata_for_crm_entity(
    partner=partner,
    partner_fund=partner_fund,
    end_date=end_date,
)
```

### Verification

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -v
```

---

## Task 3: Make Node Type Exclusion Configurable

**Estimated Effort:** 10 minutes
**Files:** `fund_admin/entity_map/crm_entity_graph_builder.py`

### Problem

The `CrmEntityGraphBuilder._remove_fund_partners()` method hardcodes which node types to exclude:

```python
@staticmethod
def _remove_fund_partners(graph: Graph) -> Graph:
    """Remove fund_partners nodes and their edges from the graph."""
    fund_partners_ids = {n.id for n in graph.nodes if n.type == "fund_partners"}
    return Graph(
        nodes=[n for n in graph.nodes if n.type != "fund_partners"],
        edges=[
            e
            for e in graph.edges
            if e.from_node_id not in fund_partners_ids
            and e.to_node_id not in fund_partners_ids
        ],
    )
```

This works for the current use case, but future views may need different exclusion rules.

### Why This Matters

The Entity Map is evolving to support multiple perspectives:
- **Fund view:** Shows all nodes including fund_partners
- **CRM entity view:** Excludes fund_partners (LP aggregation isn't relevant for an individual investor)
- **Future summary view:** Might exclude partner nodes entirely
- **Future compliance view:** Might exclude portfolio company nodes

Hardcoding `"fund_partners"` makes each new view require copy-paste-modify of the filtering logic.

### Implementation

1. Add a class constant for excluded node types:

```python
class CrmEntityGraphBuilder:
    """Builds graphs for CRM entity (investor) portfolio views."""

    # Node types to exclude from CRM entity views
    # fund_partners (LP aggregation) is not relevant when viewing a single investor
    _EXCLUDED_NODE_TYPES: frozenset[str] = frozenset({"fund_partners"})
```

2. Generalize the removal method:

```python
@staticmethod
def _remove_nodes_by_type(graph: Graph, types_to_remove: frozenset[str]) -> Graph:
    """Remove nodes of specified types and their associated edges.

    :param graph: The graph to filter.
    :param types_to_remove: Set of node types to exclude.
    :returns: New graph with specified node types removed.
    """
    excluded_ids = {n.id for n in graph.nodes if n.type in types_to_remove}
    return Graph(
        nodes=[n for n in graph.nodes if n.type not in types_to_remove],
        edges=[
            e
            for e in graph.edges
            if e.from_node_id not in excluded_ids
            and e.to_node_id not in excluded_ids
        ],
    )
```

3. Update the call site in `build_graph()`:

```python
# 2. Remove nodes not relevant for CRM entity views
base_graph = self._remove_nodes_by_type(base_graph, self._EXCLUDED_NODE_TYPES)
```

### Future Extension

This pattern allows easy customization:

```python
class SummaryGraphBuilder(CrmEntityGraphBuilder):
    _EXCLUDED_NODE_TYPES = frozenset({"fund_partners", "partner", "asset"})
```

Or via constructor injection if needed.

### Verification

```bash
poetry run pytest tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py -v
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -v
```

---

## Execution Order

These tasks are independent and can be done in any order. Suggested sequence for minimal context-switching:

1. **Task 1** (test mocks) - Quick win, ensures tests are robust before other changes
2. **Task 3** (node exclusion) - Small production code change
3. **Task 2** (extract method) - Larger refactor, benefits from tests being solid

---

## Post-Implementation Validation

After all tasks, run the full validation suite:

```bash
# Format
poetry run ruff format fund_admin/entity_map/crm_entity_graph_builder.py fund_admin/entity_map/entity_map_service.py

# Lint
poetry run ruff check --fix fund_admin/entity_map/crm_entity_graph_builder.py fund_admin/entity_map/entity_map_service.py

# Type check (run on all changed files in single command)
poetry run python -m mypy fund_admin/entity_map/crm_entity_graph_builder.py fund_admin/entity_map/entity_map_service.py

# Tests
poetry run pytest tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -v
```

---

## Summary

| Task | Effort | Impact |
|------|--------|--------|
| 1. `autospec=True` in mocks | 5 min | Test robustness |
| 2. Extract metadata fetching | 15 min | Readability, SRP |
| 3. Configurable node exclusion | 10 min | Extensibility |
| **Total** | **~30 min** | |

These refinements preserve the existing architecture while improving code quality for the PR review.

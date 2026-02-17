---
date: 2026-02-11
description: Follow-up plan addressing galonsky's review feedback on PR #50628 — refining the NodeFetcherService fetcher registry and GraphBuilder identifier collection
repository: fund-admin
tags: [entity-map, refactor, review-feedback, GPE-263]
---

# Entity Map: Fetcher Registry Refinement

Follow-up to [PR #50628](https://github.com/carta/fund-admin/pull/50628) — addressing remaining items from galonsky's architectural feedback.

## Context

PR #50628 added `individual_portfolio` root nodes to CRM entity graphs. Across 5 review threads, galonsky pushed toward a cleaner separation: NodeFetcherService should fully own what gets fetched, and GraphBuilder should not carry CRM-specific branching.

**What #50628 already addressed:**
- Eliminated `CrmEntityGraphBuilder` — consolidated into `GraphBuilder.create_for_crm_entity()`
- Moved partner metrics fetching into `IndividualPortfolioNodeFetcher` inside NodeFetcherService
- Collapsed `exclude_node_types` + `additional_fetchers` into a single `fetchers` override param

**Post-approval suggestion from galonsky (non-blocking):**
> "I'd prefer if the dependencies were more explicit at the initializer level, so just taking the fetchers dict as is, like it was before. We can leave the init fully injectable for testing, but maybe have different factory methods for the defaults?"

```python
@classmethod
def default(cls) -> NodeFetcherService:
    # create with existing fetchers dict defaults

@classmethod
def for_crm_entity(cls) -> NodeFetcherService:
    # create with crm entity dependencies
```

This replaces item #2 below — instead of lazy defaults, move the default construction into factory classmethods on NodeFetcherService itself. The `__init__` would accept the fetchers dict as-is (no merge/override logic), and each classmethod builds the right set explicitly.

**What remains:**

## 1. `_collect_node_identifiers` always emits `fund_partners` identifiers

**File:** `fund_admin/entity_map/graph_builder.py:271-274`

```python
# This runs for ALL views, including CRM entity views
fund_partners_node_id = f"{fund.uuid}_all_partners"
node_identifiers.append(
    NodeIdentifier(node_type="fund_partners", node_id=fund_partners_node_id)
)
```

The fund_partners fetcher is removed from the registry for CRM views, so `fetch_nodes` skips them (no expensive queries). But the identifiers are still created — unclear intent for someone reading the code.

**Fix:** Skip `fund_partners` identifiers when the fetcher registry doesn't include them. Two options:

- **Option A** — Pass the fetcher registry (or just its keys) to `_collect_node_identifiers` and only emit identifiers for registered types:
  ```python
  def _collect_node_identifiers(self, ...) -> list[NodeIdentifier]:
      registered_types = self._node_fetcher_service.registered_types
      ...
      if "fund_partners" in registered_types:
          node_identifiers.append(...)
  ```

- **Option B** — Make `_collect_node_identifiers` type-agnostic by having each fetcher declare which identifiers it needs from the fund list. This is a larger refactor that makes the fetcher registry truly self-describing.

**Recommendation:** Option A — minimal change, makes the intent explicit.

## 2. Move default fetcher construction into factory classmethods

**File:** `fund_admin/entity_map/services/node_fetcher_service.py`

**Galonsky's suggestion:** Instead of merge/override semantics in `__init__`, make the initializer accept the fetchers dict as-is and add factory classmethods that build the right set explicitly:

```python
class NodeFetcherService:
    def __init__(self, fetchers: dict[NodeType, INodeTypeFetcher], ...):
        self._fetchers = fetchers  # no merge logic

    @classmethod
    def default(cls) -> "NodeFetcherService":
        return cls(fetchers={
            "fund": FundNodeFetcher(...),
            "gp_entity": GPEntityNodeFetcher(...),
            "fund_partners": FundPartnersNodeFetcher(...),
            "portfolio": PortfolioNodeFetcher(...),
        })

    @classmethod
    def for_crm_entity(cls) -> "NodeFetcherService":
        return cls(fetchers={
            "fund": FundNodeFetcher(...),
            "gp_entity": GPEntityNodeFetcher(...),
            "portfolio": PortfolioNodeFetcher(...),
            "individual_portfolio": IndividualPortfolioNodeFetcher(...),
        })
```

This makes each configuration fully explicit — no `None` sentinel, no merge logic. The `__init__` stays fully injectable for tests.

**Impact:** `GraphBuilder.create_for_crm_entity()` would call `NodeFetcherService.for_crm_entity()` instead of passing override dicts. The factory logic moves one level down from GraphBuilder into NodeFetcherService.

**Recommendation:** Medium priority. Cleaner than the current merge/override pattern, and galonsky prefers it. Good candidate for the follow-up PR alongside item #1.

## 3. GraphBuilder still has CRM-specific branching in `build_graph`

**File:** `fund_admin/entity_map/graph_builder.py:172-175, 222-235`

`build_graph` has `if crm_entity_uuid:` checks for:
- Adding the individual_portfolio root node
- Connecting the root to the graph via `_find_root_target`

This means GraphBuilder "knows about" CRM entity views. Galonsky's vision was: "just an instance of GraphBuilder configured with the components you need."

**Fix:** Move root node connection logic into the fetcher or a post-processing hook:

- **Option A** — Have `IndividualPortfolioNodeFetcher.fetch()` return edges in its `NodeFetchResponse`. Currently it only returns nodes (edges depend on graph structure). This would require the fetcher to know about other nodes, breaking the current isolation.

- **Option B** — Add a `post_processors` hook on GraphBuilder that runs after all nodes are assembled. CRM entity views register a post-processor that connects the root node. This generalizes the pattern.

- **Option C** — Keep it as-is. The `if crm_entity_uuid:` checks are small and self-contained. The branching is proportional to the feature complexity.

**Recommendation:** Option C for now — the branching is minimal and well-documented. Revisit if more view-specific logic accumulates in GraphBuilder.

## Suggested PR scope

A single follow-up PR covering items **#1** and **#2**:

1. Add factory classmethods (`default()`, `for_crm_entity()`) to `NodeFetcherService`
2. Simplify `__init__` to accept fetchers as-is (no merge/override logic)
3. Skip `fund_partners` identifiers in `_collect_node_identifiers` when not in the registry
4. Update `GraphBuilder` factory methods to use the new `NodeFetcherService` classmethods

Item #3 (CRM-specific branching in `build_graph`) is a low-priority refinement that doesn't affect correctness or performance.

## Files to change

| File | Change |
|------|--------|
| `services/node_fetcher_service.py` | Add `default()` and `for_crm_entity()` classmethods; simplify `__init__`; expose `registered_types` property |
| `graph_builder.py` | Use `NodeFetcherService.default()` / `.for_crm_entity()`; conditionally emit `fund_partners` identifiers |
| `tests/backend/.../test_node_fetcher_service.py` | Test factory classmethods and registered_types property |
| `tests/backend/.../test_entity_map_service.py` | Verify CRM entity views don't emit fund_partners identifiers |

## Related

- [20260210__investigation__nodefetcherservice-partner-metrics.md](20260210__investigation__nodefetcherservice-partner-metrics.md) — Investigation of partner metrics fetching issues that led to this refinement plan
- [20260210__walkthrough__code-paths.md](20260210__walkthrough__code-paths.md) — Code path analysis providing architectural context for fetcher registry patterns

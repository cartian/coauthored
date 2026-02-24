# Entity Map Fund-Level Permissions Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Filter the CRM entity (GP portfolio) entity map graph to only show funds the requesting GP has `view_investments` ∩ `view_partners` ∩ `view_fund_performance` permissions on.

**Architecture:** The view queries `PermissionService` for the intersection of three permissions (`view_investments`, `view_partners`, `view_fund_performance`), passes the set to `EntityMapService`, which filters the relationship graph before passing it to `GraphBuilder`. GraphBuilder and NodeFetcherService never see unpermitted funds. `IndividualPortfolioNodeFetcher` consults the filtered graph's `fund_ids_to_fund` for scope — no separate `permitted_fund_uuids` threading through `NodeFetchRequest` or `GraphBuilder`.

**Key design change (from galonsky PR review):** The graph is the single source of truth for "what's visible." The fetcher doesn't get a separate permission set — it just asks the graph which funds exist. This eliminates the double-filtering smell and keeps the fetcher "dumb."

**Tech Stack:** Django 4.2, Python 3.11, DRF, pytest with real DB fixtures

**Dependency:** This branch should be rebased on master after PRs #50962 (multi-fund root edges) and #51129 (aggregated root metrics) merge. Those PRs change `IndividualPortfolioNodeFetcher` from single-partner to multi-partner and `_find_root_target` to `_find_root_targets`. The plan below is written against master as-is but Task 3 (fetcher filtering) will need minor adaptation after rebase.

**Working directory:** `/Users/ian.wessen/Projects/fund-admin/.worktrees/gpe-276-fund-permissions/`

---

## Task 1: `InvestedInRelationshipGraph.filtered_to_permitted_funds()`

Add the method that filters a relationship graph to only include permitted funds. This is a pure operation on the dataclass — no DB, no permissions awareness.

**Files:**
- Modify: `fund_admin/entity_map/invested_in_relationship_graph.py` (after `filtered_to_fund_subgraph`, ~line 261)
- Test: `tests/backend/fund_admin/entity_map/test_invested_in_relationship_graph.py` (new file or add to existing)

**Step 1: Find or create the integration test file**

Check if `tests/backend/fund_admin/entity_map/test_invested_in_relationship_graph.py` exists. If not, check where existing builder tests live (likely `test_investment_relationships_service.py`). Use the existing file if there's one for `InvestedInRelationshipGraph` directly; otherwise add tests to the builder test file in Task 2.

For now, we'll write the method first since it's a pure dataclass operation and will be exercised by builder integration tests in Task 2.

**Step 2: Implement `filtered_to_permitted_funds`**

Add this method to `InvestedInRelationshipGraph` after `filtered_to_fund_subgraph`:

```python
def filtered_to_permitted_funds(
    self, permitted_fund_uuids: set[UUID]
) -> "InvestedInRelationshipGraph":
    """Return a new graph containing only funds the user has permission to view.

    Removes unpermitted funds from fund_ids_to_fund, prunes edges involving
    those funds from adjacency dicts, and removes their partner pairs. BFS
    traversal in filtered_to_fund_subgraph() then naturally stops at
    permission boundaries.

    :param permitted_fund_uuids: Set of fund UUIDs the user can view.
    :returns: A new graph with only permitted funds and their edges.
    """
    filtered_funds = {
        fund_id: fund
        for fund_id, fund in self.fund_ids_to_fund.items()
        if fund.uuid in permitted_fund_uuids
    }
    permitted_fund_ids = set(filtered_funds.keys())

    filtered_investing = {
        fund_id: [fid for fid in invested_ids if fid in permitted_fund_ids]
        for fund_id, invested_ids in self.investing_fund_id_to_invested_fund_ids.items()
        if fund_id in permitted_fund_ids
    }
    filtered_invested = {
        fund_id: [fid for fid in investing_ids if fid in permitted_fund_ids]
        for fund_id, investing_ids in self.invested_fund_id_to_investing_fund_ids.items()
        if fund_id in permitted_fund_ids
    }

    filtered_pairs = {
        (a, b): partner_uuid
        for (a, b), partner_uuid in self.investment_pair_to_partner_uuid.items()
        if a in permitted_fund_ids and b in permitted_fund_ids
    }

    return InvestedInRelationshipGraph(
        investing_fund_id_to_invested_fund_ids=filtered_investing,
        invested_fund_id_to_investing_fund_ids=filtered_invested,
        investment_pair_to_partner_uuid=filtered_pairs,
        fund_ids_to_fund=filtered_funds,
    )
```

**Step 3: Run ruff format and lint**

```bash
poetry run ruff format fund_admin/entity_map/invested_in_relationship_graph.py
poetry run ruff check --fix fund_admin/entity_map/invested_in_relationship_graph.py
```

**Step 4: Commit**

```bash
git add fund_admin/entity_map/invested_in_relationship_graph.py
git commit -m "feat(entity-map): add filtered_to_permitted_funds to relationship graph"
```

---

## Task 2: Wire `permitted_fund_uuids` Through Builder and Service

Thread the permitted fund set from `build_for_crm_entity()` through `EntityMapService.get_crm_entity_tree()`.

**Files:**
- Modify: `fund_admin/entity_map/invested_in_relationship_graph.py:343` (`build_for_crm_entity` signature)
- Modify: `fund_admin/entity_map/entity_map_service.py:146` (`get_crm_entity_tree` signature)
- Test: `tests/backend/fund_admin/entity_map/test_entity_map_service.py` (add permission filtering tests)

**Step 1: Write the failing integration test**

Add to `tests/backend/fund_admin/entity_map/test_entity_map_service.py`. Use existing test fixtures from that file as a template. The test should:

- Create a firm with 2 funds (Fund A and Fund B)
- Create a CRM entity with Partner records in both funds
- Call `get_crm_entity_tree()` with `permitted_fund_uuids={fund_a.uuid}` (only Fund A)
- Assert the graph only contains Fund A's node, not Fund B's

Use `FirmFactory`, `FundFactory`, `PartnerFactory`, `CRMEntityFactory` following the patterns in the existing `test_get_crm_entity_tree_*` tests.

Also add a test for `permitted_fund_uuids=None` (staff path) that returns the full graph — this should match existing behavior.

**Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::<new_test_name> -v
```

Expected: FAIL because `get_crm_entity_tree` doesn't accept `permitted_fund_uuids` yet.

**Step 3: Add `permitted_fund_uuids` param to `get_crm_entity_tree()`**

In `entity_map_service.py`, modify `get_crm_entity_tree`:

```python
def get_crm_entity_tree(
    self,
    firm_id: UUID,
    crm_entity_uuid: UUID,
    end_date: date | None = None,
    permitted_fund_uuids: set[UUID] | None = None,
) -> Graph:
```

Filter the graph after building, before passing to GraphBuilder:

```python
    invested_in_relationship_graph = InvestedInRelationshipGraphBuilder(
        fund_service=FundService(),
        partner_service=PartnerService(),
    ).build_for_crm_entity(firm_id=firm_id, crm_entity_uuid=crm_entity_uuid)

    if permitted_fund_uuids is not None:
        invested_in_relationship_graph = (
            invested_in_relationship_graph.filtered_to_permitted_funds(
                permitted_fund_uuids
            )
        )
```

Note: filtering happens at the service layer, not inside `build_for_crm_entity`. The builder stays permission-unaware. The service orchestrates: build → filter → render.

**Step 5: Run test to verify it passes**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -v
```

Expected: All tests pass (existing + new).

**Step 6: Run ruff format, lint, and type check**

```bash
poetry run ruff format fund_admin/entity_map/invested_in_relationship_graph.py fund_admin/entity_map/entity_map_service.py
poetry run ruff check --fix fund_admin/entity_map/invested_in_relationship_graph.py fund_admin/entity_map/entity_map_service.py
```

**Step 7: Commit**

```bash
git add fund_admin/entity_map/invested_in_relationship_graph.py fund_admin/entity_map/entity_map_service.py tests/backend/fund_admin/entity_map/test_entity_map_service.py
git commit -m "feat(entity-map): wire permitted_fund_uuids through service and builder"
```

---

## Task 3: Scope `IndividualPortfolioNodeFetcher` to Graph's Fund Set

The root node fetcher independently queries all partners for the CRM entity and resolves their funds. After graph filtering (Task 2), the fetcher should consult the filtered graph for scope instead of independently building its own fund universe.

Per galonsky's review: "the fetcher should consult the graph to see which funds to limit the search to." The graph is the single source of truth for visibility.

**Files:**
- Modify: `fund_admin/entity_map/services/node_fetcher_service.py:431` (`IndividualPortfolioNodeFetcher.fetch`)
- Test: covered by Task 2's service-level tests (root node metrics should reflect only permitted funds)

**No changes to:** `domain.py` (no `permitted_fund_uuids` on `NodeFetchRequest`)

**Note:** `graph_builder.py` gets a one-liner to pass `invested_in_relationship_graph` through to `NodeFetchRequest` in `build_graph()`. This field already existed on the dataclass but wasn't being populated.

**Step 1: Scope `IndividualPortfolioNodeFetcher.fetch()` to graph's fund set**

In `node_fetcher_service.py`, replace the independent fund resolution with graph-scoped filtering. Graph funds get both edges and metrics; non-graph funds (GP entity funds) get edge-only UUID resolution:

```python
    partners = self._partner_service.list_domain_objects(
        crm_entity_ids=[crm_entity_uuid],
        firm_ids=[request.firm_uuid],
    )
    if not partners:
        continue

    # Use the relationship graph as the source of truth for which funds
    # are in scope. The graph is already filtered to permitted funds
    # before reaching the fetcher.
    fund_ids_to_fund = (
        request.invested_in_relationship_graph.fund_ids_to_fund
        if request.invested_in_relationship_graph
        else {}
    )

    seen_fund_ids: set[int] = set()
    fund_uuids: list[str] = []
    all_funds: list[FundDomain] = []
    partner_uuid_by_fund_id: dict[int, str] = {}
    for p in partners:
        if p.fund_id in seen_fund_ids:
            continue
        seen_fund_ids.add(p.fund_id)

        fund = fund_ids_to_fund.get(p.fund_id)
        if fund and fund.uuid:
            # Fund is in the graph — include for both edges and metrics
            fund_uuids.append(str(fund.uuid))
            all_funds.append(fund)
            partner_uuid_by_fund_id[fund.id] = str(p.uuid)
        else:
            # Fund not in the graph (e.g. GP entity fund). Resolve
            # UUID for edge creation but skip metric aggregation.
            resolved = self._fund_service.get_by_fund_id(fund_id=p.fund_id)
            if resolved and resolved.uuid:
                fund_uuids.append(str(resolved.uuid))
```

Key design point: GP entity funds aren't in the relationship graph (excluded by `build_for_firm`). Their UUIDs are still needed for root → GP entity node edges, but they're excluded from `all_funds` so their partner metrics aren't aggregated into the root node.

**Step 2: Write a test asserting root metrics only reflect permitted funds**

Add to the service test file. Create a CRM entity invested in Fund A (commitment 100k) and Fund B (commitment 200k). Pass `permitted_fund_uuids={fund_a.uuid}` to `get_crm_entity_tree`. Assert the individual_portfolio root node's metrics show commitment = 100k, not 300k.

**Step 3: Run tests**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree -v
```

**Step 4: Format, lint**

```bash
poetry run ruff format fund_admin/entity_map/services/node_fetcher_service.py
poetry run ruff check --fix fund_admin/entity_map/services/node_fetcher_service.py
```

**Step 5: Commit**

```bash
git add fund_admin/entity_map/services/node_fetcher_service.py tests/backend/fund_admin/entity_map/test_entity_map_service.py
git commit -m "refactor(entity-map): scope fetcher to graph's fund set instead of separate permission param"
```

---

## Task 4: Update View — Relax Permission Gate and Query Permitted Funds

Replace `HasAllViewPermissions` with `IsFirmMember` and query `PermissionService` for the user's permitted fund UUIDs.

**Files:**
- Modify: `fund_admin/entity_map/views/entity_map_crm_entity_view.py`
- Test: `tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py` (new or existing)

**Step 1: Write view-level integration tests**

Create tests using `permissioned_client_factory` and `permissioned_user_factory` fixtures:

**Test 1: GP with partial fund access sees filtered graph**
- Create firm, Fund A, Fund B
- Create CRM entity with partners in both
- Create user with `view_investments` on Fund A only (via `permissioned_user_factory` or `permissions_mock`)
- Make user a firm member
- GET the CRM entity endpoint
- Assert 200, graph contains Fund A node, no Fund B node

**Test 2: Staff sees full graph**
- Same setup, user is staff
- Assert 200, graph contains both Fund A and Fund B

**Test 3: Firm member with no fund permissions sees empty graph**
- User is firm member but has `view_investments` on no funds
- Assert 200, graph has no fund nodes (empty or just root node)

**Test 4: IDOR prevention unchanged**
- CRM entity from different firm
- Assert 403

Use the URL pattern from `entity_map/urls.py` for the CRM entity endpoint. The firmless URL is: `/entity-atlas/crm-entity/<crm_entity_uuid>/`

**Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py -v
```

**Step 3: Implement view changes**

In `entity_map_crm_entity_view.py`:

1. Change imports — remove `HasAllViewPermissions`, add `IsFirmMember`:

```python
from fund_admin.permissions.gp_permissions.permission_classes import (
    IsFirmMember,
)
from fund_admin.permissions.constants import StandardFundPermissionEnum as StandardFundPermission
from fund_admin.permissions.services.permission_service import PermissionService
```

2. Update permission_classes:

```python
    permission_classes = [IsFirmMember | IsStaff]
```

3. Remove the TODO comment on line 46-47.

4. Add the permission query method (intersects all three required permissions):

```python
    _REQUIRED_FUND_PERMISSIONS = [
        StandardFundPermission.VIEW_INVESTMENTS,
        StandardFundPermission.VIEW_PARTNERS,
        StandardFundPermission.VIEW_FUND_PERFORMANCE,
    ]

    def _get_permitted_fund_uuids(
        self, request: Request, firm_uuid: UUID
    ) -> set[UUID] | None:
        """Get fund UUIDs where the user has all required view permissions.

        A fund is visible only if the user has view_investments,
        view_partners, AND view_fund_performance on it.

        :param request: The DRF request (contains user).
        :param firm_uuid: The firm to check permissions in.
        :returns: Set of permitted fund UUIDs, or None for staff (no filtering).
        """
        if request.user.is_staff:
            return None

        permission_service = PermissionService()
        fund_uuid_sets = [
            set(
                permission_service.get_funds_user_has_gp_permission_for(
                    firm_uuid=firm_uuid,
                    user=request.user,
                    permission_level=perm,
                ).values_list("uuid", flat=True)
            )
            for perm in self._REQUIRED_FUND_PERMISSIONS
        ]
        return set.intersection(*fund_uuid_sets) if fund_uuid_sets else set()
```

5. Update `_get_crm_entity_tree` to accept and pass the request:

```python
    def _get_crm_entity_tree(
        self,
        request: Request,
        firm_uuid: UUID,
        crm_entity_uuid: UUID,
        query_params: EntityMapCrmEntityViewQueryParams,
    ) -> Graph:
        """Internal method for getting the CRM entity tree - can be tested directly."""
        self._validate_crm_entity_in_firm(crm_entity_uuid, firm_uuid)

        permitted_fund_uuids = self._get_permitted_fund_uuids(request, firm_uuid)

        entity_map_service = EntityMapService.factory(
            lightweight=query_params.lightweight,
        )
        return entity_map_service.get_crm_entity_tree(
            firm_id=firm_uuid,
            crm_entity_uuid=crm_entity_uuid,
            end_date=query_params.end_date,
            permitted_fund_uuids=permitted_fund_uuids,
        )
```

6. Update `get` to pass `request`:

```python
        return self._get_crm_entity_tree(
            request=request,
            firm_uuid=resolved_firm_uuid,
            crm_entity_uuid=crm_entity_uuid,
            query_params=query_params,
        )
```

**Step 4: Run tests**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py -v
```

**Step 5: Run ALL entity map tests to check for regressions**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/ -v
```

**Step 6: Format, lint, type check**

```bash
poetry run ruff format fund_admin/entity_map/views/entity_map_crm_entity_view.py
poetry run ruff check --fix fund_admin/entity_map/views/entity_map_crm_entity_view.py
```

**Step 7: Commit**

```bash
git add fund_admin/entity_map/views/entity_map_crm_entity_view.py tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py
git commit -m "feat(entity-map): relax CRM entity view to IsFirmMember with fund-level filtering"
```

---

## Task 5: Final Validation

**Step 1: Run full entity map test suite**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/ -v
```

**Step 2: Run ruff on all changed files**

```bash
poetry run ruff format fund_admin/entity_map/invested_in_relationship_graph.py fund_admin/entity_map/entity_map_service.py fund_admin/entity_map/graph_builder.py fund_admin/entity_map/services/domain.py fund_admin/entity_map/services/node_fetcher_service.py fund_admin/entity_map/views/entity_map_crm_entity_view.py
poetry run ruff check fund_admin/entity_map/invested_in_relationship_graph.py fund_admin/entity_map/entity_map_service.py fund_admin/entity_map/graph_builder.py fund_admin/entity_map/services/domain.py fund_admin/entity_map/services/node_fetcher_service.py fund_admin/entity_map/views/entity_map_crm_entity_view.py
```

**Step 3: Run flake8 mock specs on test files**

```bash
poetry run flake8 tests/backend/fund_admin/entity_map/test_entity_map_service.py tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py --select=TMS010,TMS011,TMS012,TMS013,TMS020,TMS021,TMS022
```

**Step 4: Verify git status and review diff**

```bash
git status
git log --oneline master..HEAD
```

Expected: 4 commits, all entity_map files, no untracked/unstaged changes.

---

## File Summary

| File | Change |
|------|--------|
| `fund_admin/entity_map/invested_in_relationship_graph.py` | Add `filtered_to_permitted_funds()` method |
| `fund_admin/entity_map/entity_map_service.py` | Add `permitted_fund_uuids` param to `get_crm_entity_tree()`, filter graph before passing to builder |
| `fund_admin/entity_map/services/node_fetcher_service.py` | Scope `IndividualPortfolioNodeFetcher` to graph's fund set for metrics; GP entity funds get edge-only UUID resolution |
| `fund_admin/entity_map/graph_builder.py` | One-liner: pass `invested_in_relationship_graph` through to `NodeFetchRequest` |
| `fund_admin/entity_map/views/entity_map_crm_entity_view.py` | Swap `HasAllViewPermissions` → `IsFirmMember`, add `_get_permitted_fund_uuids()` (3-permission intersection) |
| `tests/backend/fund_admin/entity_map/test_entity_map_service.py` | Add permission filtering integration tests |
| `tests/backend/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py` | Add view-level permission integration tests |

Unchanged: `services/domain.py` — no permission params needed downstream.

Total: 5 implementation files + 2 test files = 7 files (within the 15-file target).

## Related

- [20260213__design__fund-level-permissions.md](20260213__design__fund-level-permissions.md) — Design document establishing fund-level permission filtering architecture
- [20260213__review__fund-permissions-implementation.md](20260213__review__fund-permissions-implementation.md) — Code review notes and feedback on implementation

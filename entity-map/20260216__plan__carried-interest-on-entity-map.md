# Carried Interest on Entity Map Nodes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add carried interest accrued as a metric on entity map nodes, respecting per-fund carry visibility gates.

**Architecture:** Add `PartnerCapitalCarriedInterestAccrued` to the existing `INCLUDED_METRICS` list so it flows through the partner metrics pipeline automatically. After metrics are fetched, check `show_carry_metrics_by_fund_ids()` and strip the carry key from partners in funds where carry is hidden. The metric aggregates to the root node via existing `MetricsOverTime.__add__()`.

**Tech Stack:** Django 4.2, Python 3.11, pytest with real DB fixtures

**Working directory:** `/Users/ian.wessen/Projects/fund-admin/`

**Branch:** Create from current branch or master as appropriate.

---

## Task 1: Add Carried Interest to `METRIC_KEY_TO_NAME`

Register the carry metric so it's included in all partner metrics fetches.

**Files:**
- Modify: `fund_admin/entity_map/constants.py`

**Step 1: Add the metric to `METRIC_KEY_TO_NAME`**

In `fund_admin/entity_map/constants.py`, add the import and the new entry:

```python
import fund_admin.metrics.partner.auditable as partner_metrics
from fund_admin.entity_map.domain import MetricsOverTime

METRIC_KEY_TO_NAME: dict[str, str] = {
    partner_metrics.Commitment.name: "commitment",
    partner_metrics.CalledCapital.name: "called_capital",
    partner_metrics.Distribution.name: "distribution",
    partner_metrics.DPI.name: "dpi",
    partner_metrics.TVPI.name: "tvpi",
    partner_metrics.RVPI.name: "rvpi",
    partner_metrics.UnrealizedGainLoss.name: "unrealized_gain_loss",
    partner_metrics.PartnerCapitalCarriedInterestAccrued.name: "carried_interest_accrued",
}
```

No other changes — `INCLUDED_METRICS = list(METRIC_KEY_TO_NAME.keys())` picks it up automatically, and `DEFAULT_METRICS` uses the values dict, so it also gains a `"carried_interest_accrued": Decimal(0)` entry.

**Step 2: Run ruff format and lint**

```bash
poetry run ruff format fund_admin/entity_map/constants.py
poetry run ruff check --fix fund_admin/entity_map/constants.py
```

**Step 3: Commit**

```bash
git add fund_admin/entity_map/constants.py
git commit -m "feat(entity-map): add carried_interest_accrued to included metrics"
```

---

## Task 2: Write Failing Test for Carry Metric on Entity Map Nodes

Write an integration test that verifies carry appears in node metrics. This should fail initially because the carry gate stripping logic doesn't exist yet — but the metric will actually be present since Task 1 added it to `INCLUDED_METRICS`. So write the test for the *carry gate* behavior: a fund with carry hidden should NOT have the key.

**Files:**
- Test: `tests/backend/fund_admin/entity_map/test_entity_map_service.py`

**Step 1: Write the carry gate test**

Add a new test to the `TestGetCrmEntityTree` class (or create a new class `TestCarriedInterestMetrics` — follow existing patterns in the file). The test should:

1. Create a firm with a fund
2. Create a CRM entity with a partner in the fund, with a commitment transaction
3. Call `get_crm_entity_tree()` — the result should have `carried_interest_accrued` in the root node's `end_metrics`
4. Now mock `show_carry_metrics_by_fund_ids` to return `{fund.id: False}` for that fund
5. Call again — the result should NOT have `carried_interest_accrued` in the root node's `end_metrics`

Use `mocker.patch()` to patch `fund_admin.entity_map.metrics.partner_metrics_handler.show_carry_metrics_by_fund_ids` (this is the import location in the handler, which is where the gate runs).

Note: `show_carry_metrics_by_fund_ids` calls `GPEntityConfigurationService` which hits the DB and checks feature flags. In the test without patching, the default behavior when `GPE_172_PARTNER_DASHBOARD_R1` is disabled is to return `True` for all funds (backward compat). So the metric should be present by default.

```python
def test_get_crm_entity_tree_includes_carried_interest_metric(self, firm, mocker):
    """Carried interest accrued should appear in node metrics when carry is enabled for the fund."""
    gp_entity = FundFactory(entity_type=EntityTypes.GP_ENTITY, firm=firm)
    fund = make_fund_with_gp_entity(firm, gp_entity)

    investor_crm_entity = CRMEntityFactory()
    partner = PartnerFactory(
        fund=fund,
        partner_type=PartnerTypes.LIMITED_PARTNER.value,
        entity=investor_crm_entity,
    )
    CommitmentTransactionFactory(partner=partner, amount_cents=100000)

    entity_map_service = EntityMapService()
    result = entity_map_service.get_crm_entity_tree(
        firm_id=firm.id,
        crm_entity_uuid=investor_crm_entity.id,
    )

    root_node = next(
        (n for n in result.nodes if n.type == "individual_portfolio"), None
    )
    assert root_node is not None
    assert root_node.metrics is not None
    assert "carried_interest_accrued" in root_node.metrics.end_metrics


def test_get_crm_entity_tree_hides_carry_when_fund_gate_is_false(self, firm, mocker):
    """When carry gate returns False for a fund, carried_interest_accrued key should be absent from metrics."""
    gp_entity = FundFactory(entity_type=EntityTypes.GP_ENTITY, firm=firm)
    fund = make_fund_with_gp_entity(firm, gp_entity)

    investor_crm_entity = CRMEntityFactory()
    partner = PartnerFactory(
        fund=fund,
        partner_type=PartnerTypes.LIMITED_PARTNER.value,
        entity=investor_crm_entity,
    )
    CommitmentTransactionFactory(partner=partner, amount_cents=100000)

    # Gate carry off for this fund
    mocker.patch(
        "fund_admin.entity_map.metrics.partner_metrics_handler.show_carry_metrics_by_fund_ids",
        return_value={fund.id: False},
    )

    entity_map_service = EntityMapService()
    result = entity_map_service.get_crm_entity_tree(
        firm_id=firm.id,
        crm_entity_uuid=investor_crm_entity.id,
    )

    root_node = next(
        (n for n in result.nodes if n.type == "individual_portfolio"), None
    )
    assert root_node is not None
    assert root_node.metrics is not None
    assert "carried_interest_accrued" not in root_node.metrics.end_metrics
```

**Step 2: Run tests to verify current state**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_includes_carried_interest_metric -xvs
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_hides_carry_when_fund_gate_is_false -xvs
```

Expected:
- First test: PASS (metric is in `INCLUDED_METRICS` from Task 1, carry gate defaults to enabled)
- Second test: FAIL (carry gate is patched to `False`, but the handler doesn't strip the key yet)

**Step 3: Commit the failing test**

```bash
git add tests/backend/fund_admin/entity_map/test_entity_map_service.py
git commit -m "test(entity-map): add carried interest carry gate integration tests"
```

---

## Task 3: Implement Carry Gate Stripping in Partner Metrics Handler

Add post-processing in `DefaultPartnerMetricsHandler.get_partner_metadata_for_funds()` that checks the carry gate and strips the carry key from partners in hidden-carry funds.

**Files:**
- Modify: `fund_admin/entity_map/metrics/partner_metrics_handler.py`

**Step 1: Add import and constant**

At the top of `partner_metrics_handler.py`, add the import:

```python
from fund_admin.partner_portfolios.feature_flags import show_carry_metrics_by_fund_ids
```

Add a constant after the existing constants (after `METRICS_TO_OMIT_FROM_NAV_COMPONENTS`):

```python
CARRY_METRIC_NAME = METRIC_KEY_TO_NAME.get(
    partner_metrics.PartnerCapitalCarriedInterestAccrued.name, "carried_interest_accrued"
)
```

This will also need the `partner_metrics` import — check if it's already imported (it's in `constants.py` but not necessarily here). Add if needed:

```python
import fund_admin.metrics.partner.auditable as partner_metrics
```

**Step 2: Add carry gate stripping to `get_partner_metadata_for_funds()`**

In `DefaultPartnerMetricsHandler.get_partner_metadata_for_funds()`, after the loop that builds `result` (after line 137), add:

```python
        # Strip carried interest metric from funds where carry is hidden
        self._apply_carry_gate(result, funds)

        return result
```

Add the method to `DefaultPartnerMetricsHandler`:

```python
    def _apply_carry_gate(
        self,
        result: dict[FundIdInteger, dict[PartnerUUIDString, PartnerMetadata]],
        funds: list[FundDomain],
    ) -> None:
        """Remove carried_interest_accrued key from partners in funds where carry is hidden.

        Modifies result in-place. Uses show_carry_metrics_by_fund_ids() to batch-check
        all funds, then strips the carry key from metrics for hidden funds.
        An absent key means "not applicable/permitted" — distinct from 0 (no carry)
        or None (couldn't calculate).
        """
        fund_ids = [fund.id for fund in funds if fund.id in result]
        if not fund_ids:
            return

        carry_visibility = show_carry_metrics_by_fund_ids(fund_ids)

        for fund_id, partners in result.items():
            if carry_visibility.get(fund_id, True):
                continue
            # Strip carry key from all partners in this fund
            for partner_metadata in partners.values():
                metrics = partner_metadata.metrics
                metrics.end_metrics.pop(CARRY_METRIC_NAME, None)
                metrics.start_metrics.pop(CARRY_METRIC_NAME, None)
                metrics.change_metrics.pop(CARRY_METRIC_NAME, None)
```

Note: We mutate the dict in-place rather than creating new `MetricsOverTime` via `filtered_by_keys()` because `filtered_by_keys` would require listing all non-carry keys (brittle). A simple `pop` on the one key we want to remove is more direct.

**Step 3: Run the failing test**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_hides_carry_when_fund_gate_is_false -xvs
```

Expected: PASS

**Step 4: Run all carry-related tests**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_includes_carried_interest_metric tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_hides_carry_when_fund_gate_is_false -xvs
```

Expected: Both PASS.

**Step 5: Run full entity map test suite for regressions**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/ -x --timeout=120
```

Expected: All pass. Existing tests should be unaffected — the carry metric is a new key in `end_metrics` that existing assertions don't check for.

**Step 6: Format, lint, type check**

```bash
poetry run ruff format fund_admin/entity_map/metrics/partner_metrics_handler.py fund_admin/entity_map/constants.py
poetry run ruff check --fix fund_admin/entity_map/metrics/partner_metrics_handler.py fund_admin/entity_map/constants.py
poetry run flake8 tests/backend/fund_admin/entity_map/test_entity_map_service.py --select=TMS010,TMS011,TMS012,TMS013,TMS020,TMS021,TMS022
```

**Step 7: Commit**

```bash
git add fund_admin/entity_map/metrics/partner_metrics_handler.py
git commit -m "feat(entity-map): strip carried_interest_accrued from nodes when carry gate is false"
```

---

## Task 4: Add Multi-Fund Carry Gate Aggregation Test

Verify that when some funds show carry and others don't, the root node only aggregates carry from visible funds.

**Files:**
- Test: `tests/backend/fund_admin/entity_map/test_entity_map_service.py`

**Step 1: Write the partial visibility test**

```python
def test_get_crm_entity_tree_carry_aggregation_with_partial_visibility(self, firm, mocker):
    """Root node carry should only aggregate from funds where carry gate passes."""
    gp_entity = FundFactory(entity_type=EntityTypes.GP_ENTITY, firm=firm)
    fund_a = make_fund_with_gp_entity(firm, gp_entity)
    fund_b = make_fund_with_gp_entity(firm, gp_entity)

    investor_crm_entity = CRMEntityFactory()
    partner_a = PartnerFactory(
        fund=fund_a,
        partner_type=PartnerTypes.LIMITED_PARTNER.value,
        entity=investor_crm_entity,
    )
    partner_b = PartnerFactory(
        fund=fund_b,
        partner_type=PartnerTypes.LIMITED_PARTNER.value,
        entity=investor_crm_entity,
    )
    CommitmentTransactionFactory(partner=partner_a, amount_cents=100000)
    CommitmentTransactionFactory(partner=partner_b, amount_cents=200000)

    # Fund A shows carry, Fund B hides carry
    mocker.patch(
        "fund_admin.entity_map.metrics.partner_metrics_handler.show_carry_metrics_by_fund_ids",
        return_value={fund_a.id: True, fund_b.id: False},
    )

    entity_map_service = EntityMapService()
    result = entity_map_service.get_crm_entity_tree(
        firm_id=firm.id,
        crm_entity_uuid=investor_crm_entity.id,
    )

    root_node = next(
        (n for n in result.nodes if n.type == "individual_portfolio"), None
    )
    assert root_node is not None
    assert root_node.metrics is not None

    # Root should have carry key (Fund A contributes it)
    assert "carried_interest_accrued" in root_node.metrics.end_metrics

    # Check fund-level partner nodes
    fund_nodes = [n for n in result.nodes if n.type == "fund"]
    for fund_node in fund_nodes:
        if fund_node.metrics and fund_node.id == str(fund_b.uuid):
            # Fund B's metrics should NOT have carry
            assert "carried_interest_accrued" not in fund_node.metrics.end_metrics
```

**Step 2: Run the test**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py::TestGetCrmEntityTree::test_get_crm_entity_tree_carry_aggregation_with_partial_visibility -xvs
```

Expected: PASS (the gate stripping from Task 3 handles this).

**Step 3: Commit**

```bash
git add tests/backend/fund_admin/entity_map/test_entity_map_service.py
git commit -m "test(entity-map): verify partial carry visibility in multi-fund aggregation"
```

---

## Task 5: Final Validation

**Step 1: Run full entity map test suite**

```bash
poetry run pytest tests/backend/fund_admin/entity_map/ -v --timeout=120
```

**Step 2: Run ruff on all changed files**

```bash
poetry run ruff format fund_admin/entity_map/constants.py fund_admin/entity_map/metrics/partner_metrics_handler.py
poetry run ruff check fund_admin/entity_map/constants.py fund_admin/entity_map/metrics/partner_metrics_handler.py
```

**Step 3: Run flake8 mock specs on test files**

```bash
poetry run flake8 tests/backend/fund_admin/entity_map/test_entity_map_service.py --select=TMS010,TMS011,TMS012,TMS013,TMS020,TMS021,TMS022
```

**Step 4: Verify git status and review diff**

```bash
git status
git log --oneline master..HEAD
```

Expected: 4 commits, clean working tree.

---

## File Summary

| File | Change |
|------|--------|
| `fund_admin/entity_map/constants.py` | Add `PartnerCapitalCarriedInterestAccrued` to `METRIC_KEY_TO_NAME` |
| `fund_admin/entity_map/metrics/partner_metrics_handler.py` | Add `_apply_carry_gate()` method, import carry gate, add `CARRY_METRIC_NAME` constant |
| `tests/backend/fund_admin/entity_map/test_entity_map_service.py` | 3 new tests: carry present, carry hidden, partial visibility aggregation |

Total: 2 implementation files + 1 test file = 3 files.

## Notes for Future Work

When deal-level carry breakdowns are ready (`CarryAttributionService`), the integration path is:
- Extend `GPEntityNodeFetcher` to call `CarryAttributionService.get_aggregated_attribution()`
- Attach deal-level data to GP Entity node `metadata["carry_attributions"]`
- The aggregate `carried_interest_accrued` from this plan stays as the summary; deal breakdowns layer on top
- Note this in the PR description for discoverability

## Related

- [20260216__design__carried-interest-on-entity-map.md](20260216__design__carried-interest-on-entity-map.md) — Design document establishing the carried interest visibility gates and aggregation approach

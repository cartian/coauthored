# Individual Portfolio Node Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `individual_portfolio` node type to entity map CRM entity views so the investor appears as the root node.

**Architecture:** New `CrmEntityGraphBuilder` composes `GraphBuilder` and adds the individual_portfolio root node. Node data comes from Partner record. Clean separation keeps shared GraphBuilder unchanged.

**Tech Stack:** Python 3.11, Django, pytest, dataclasses

**Design Doc:** `docs/plans/20260205-individual-portfolio-node-design.md`

---

## Task 1: Add Node Type to Domain

**Files:**
- Modify: `fund_admin/entity_map/domain.py:8-15` and `fund_admin/entity_map/domain.py:28-35`

**Step 1: Add individual_portfolio to NodeType**

```python
NodeType = Literal[
    "fund",
    "portfolio",
    "asset",
    "partner",
    "gp_entity",
    "fund_partners",
    "individual_portfolio",
]
```

**Step 2: Add to human_readable_node_type**

```python
human_readable_node_type = {
    "fund": "Fund",
    "portfolio": "Portfolio",
    "asset": "Asset",
    "partner": "Partner",
    "gp_entity": "GP Entity",
    "fund_partners": "Fund Partners",
    "individual_portfolio": "Individual Portfolio",
}
```

**Step 3: Verify no type errors**

Run: `poetry run python -m mypy fund_admin/entity_map/domain.py`
Expected: No errors

**Step 4: Commit**

```bash
git add fund_admin/entity_map/domain.py
git commit -m "feat(entity-map): add individual_portfolio node type to domain"
```

---

## Task 2: Create IndividualPortfolioNodeBuilder

**Files:**
- Create: `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py`
- Create: `tests/unit/fund_admin/entity_map/node_builders/__init__.py`
- Create: `tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py`

**Step 1: Write the failing test**

Create test file:

```python
# tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py
from uuid import UUID, uuid4

import pytest

from fund_admin.capital_account.domain import PartnerDomain
from fund_admin.entity_map.node_builders.individual_portfolio_node_builder import (
    IndividualPortfolioNodeBuilder,
)


@pytest.fixture
def partner_domain() -> PartnerDomain:
    return PartnerDomain(
        id=1,
        uuid=UUID("2eec2da3-c192-4563-9607-6014f829a8ed"),
        name="John Daley",
        fund_id=699,
        partner_type="managing_member",
        entity_id="a2f23ebe-3675-45f7-867e-d3ad5f0effaf",
    )


class TestIndividualPortfolioNodeBuilder:
    def test_build_node_creates_correct_structure(self, partner_domain: PartnerDomain):
        crm_entity_uuid = UUID("a2f23ebe-3675-45f7-867e-d3ad5f0effaf")
        gp_entity_fund_uuid = UUID("4a55f602-375c-4211-a579-09075405de08")
        builder = IndividualPortfolioNodeBuilder()

        node = builder.build_node(
            crm_entity_uuid=crm_entity_uuid,
            partner=partner_domain,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        assert node.id == str(crm_entity_uuid)
        assert node.type == "individual_portfolio"
        assert node.name == "John Daley"
        assert node.metadata["partner_uuid"] == str(partner_domain.uuid)
        assert node.metadata["partner_type"] == "managing_member"
        assert node.metadata["fund_id"] == 699
        assert node.metadata["fund_uuid"] == str(gp_entity_fund_uuid)

    def test_build_node_uses_partner_name(self, partner_domain: PartnerDomain):
        crm_entity_uuid = UUID("a2f23ebe-3675-45f7-867e-d3ad5f0effaf")
        gp_entity_fund_uuid = uuid4()
        partner_domain.name = "Jane Smith"
        builder = IndividualPortfolioNodeBuilder()

        node = builder.build_node(
            crm_entity_uuid=crm_entity_uuid,
            partner=partner_domain,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        assert node.name == "Jane Smith"
```

Also create `tests/unit/fund_admin/entity_map/node_builders/__init__.py` (empty file).

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

**Step 3: Write minimal implementation**

```python
# fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py
from uuid import UUID

from fund_admin.capital_account.domain import PartnerDomain
from fund_admin.entity_map.domain import MetricsOverTime, Node


class IndividualPortfolioNodeBuilder:
    """Builds the root node for CRM entity (investor) portfolio views."""

    def build_node(
        self,
        crm_entity_uuid: UUID,
        partner: PartnerDomain,
        gp_entity_fund_uuid: UUID,
    ) -> Node:
        """
        Build an individual_portfolio node representing the investor.

        Args:
            crm_entity_uuid: The CRM entity UUID (becomes the node ID)
            partner: The Partner record for this investor (provides name, type)
            gp_entity_fund_uuid: The UUID of the GP entity fund they're invested in

        Returns:
            Node with type "individual_portfolio"
        """
        return Node(
            id=str(crm_entity_uuid),
            type="individual_portfolio",
            name=partner.name,
            metadata={
                "partner_uuid": str(partner.uuid),
                "partner_type": partner.partner_type,
                "fund_id": partner.fund_id,
                "fund_uuid": str(gp_entity_fund_uuid),
            },
            metrics=MetricsOverTime.empty(),
        )
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py -v`
Expected: PASS

**Step 5: Run linters**

Run: `poetry run ruff format fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py && poetry run ruff check fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py`

**Step 6: Commit**

```bash
git add fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py tests/unit/fund_admin/entity_map/node_builders/
git commit -m "feat(entity-map): add IndividualPortfolioNodeBuilder"
```

---

## Task 3: Create CrmEntityGraphBuilder

**Files:**
- Create: `fund_admin/entity_map/crm_entity_graph_builder.py`
- Create: `tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py`

**Step 1: Write the failing test**

```python
# tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py
from uuid import UUID, uuid4

import pytest
from pytest_mock import MockerFixture

from fund_admin.capital_account.domain import PartnerDomain
from fund_admin.entity_map.crm_entity_graph_builder import CrmEntityGraphBuilder
from fund_admin.entity_map.domain import Edge, Graph, MetricsOverTime, Node
from fund_admin.entity_map.graph_builder import GraphBuilder
from fund_admin.entity_map.invested_in_relationship_graph import (
    InvestedInRelationshipGraph,
)
from fund_admin.entity_map.node_builders.individual_portfolio_node_builder import (
    IndividualPortfolioNodeBuilder,
)


@pytest.fixture
def firm_uuid() -> UUID:
    return UUID("186fb573-a22d-4c82-8ad3-3186f9095a41")


@pytest.fixture
def crm_entity_uuid() -> UUID:
    return UUID("a2f23ebe-3675-45f7-867e-d3ad5f0effaf")


@pytest.fixture
def main_fund_uuid() -> UUID:
    return UUID("4b6a4f7b-e79d-42d2-9dc9-d35fb0df6a07")


@pytest.fixture
def gp_entity_fund_uuid() -> UUID:
    return UUID("4a55f602-375c-4211-a579-09075405de08")


@pytest.fixture
def partner_domain(gp_entity_fund_uuid: UUID, crm_entity_uuid: UUID) -> PartnerDomain:
    return PartnerDomain(
        id=1,
        uuid=UUID("2eec2da3-c192-4563-9607-6014f829a8ed"),
        name="John Daley",
        fund_id=699,
        partner_type="managing_member",
        entity_id=str(crm_entity_uuid),
    )


@pytest.fixture
def mock_base_graph(main_fund_uuid: UUID, gp_entity_fund_uuid: UUID) -> Graph:
    """A minimal graph returned by the base GraphBuilder."""
    gp_entity_node_id = f"{main_fund_uuid}_{gp_entity_fund_uuid}"
    return Graph(
        nodes=[
            Node(
                id=gp_entity_node_id,
                type="gp_entity",
                name="Krakatoa Fund IV GP, L.P.",
                metadata={},
                metrics=MetricsOverTime.empty(),
            ),
            Node(
                id=str(main_fund_uuid),
                type="fund",
                name="Krakatoa Ventures Fund IV, L.P.",
                metadata={},
                metrics=MetricsOverTime.empty(),
            ),
        ],
        edges=[
            Edge(
                from_node_id=gp_entity_node_id,
                to_node_id=str(main_fund_uuid),
            ),
        ],
    )


class TestCrmEntityGraphBuilder:
    def test_build_graph_adds_individual_portfolio_node(
        self,
        mocker: MockerFixture,
        firm_uuid: UUID,
        crm_entity_uuid: UUID,
        gp_entity_fund_uuid: UUID,
        partner_domain: PartnerDomain,
        mock_base_graph: Graph,
    ):
        mock_graph_builder = mocker.MagicMock(spec=GraphBuilder)
        mock_graph_builder.build_graph.return_value = mock_base_graph

        builder = CrmEntityGraphBuilder(graph_builder=mock_graph_builder)

        result = builder.build_graph(
            firm_uuid=firm_uuid,
            invested_in_relationship_graph=InvestedInRelationshipGraph.empty(),
            crm_entity_uuid=crm_entity_uuid,
            partner=partner_domain,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        # Should have individual_portfolio node
        individual_portfolio_nodes = [
            n for n in result.nodes if n.type == "individual_portfolio"
        ]
        assert len(individual_portfolio_nodes) == 1
        assert individual_portfolio_nodes[0].id == str(crm_entity_uuid)
        assert individual_portfolio_nodes[0].name == "John Daley"

    def test_build_graph_creates_edge_to_gp_entity(
        self,
        mocker: MockerFixture,
        firm_uuid: UUID,
        crm_entity_uuid: UUID,
        main_fund_uuid: UUID,
        gp_entity_fund_uuid: UUID,
        partner_domain: PartnerDomain,
        mock_base_graph: Graph,
    ):
        mock_graph_builder = mocker.MagicMock(spec=GraphBuilder)
        mock_graph_builder.build_graph.return_value = mock_base_graph

        builder = CrmEntityGraphBuilder(graph_builder=mock_graph_builder)

        result = builder.build_graph(
            firm_uuid=firm_uuid,
            invested_in_relationship_graph=InvestedInRelationshipGraph.empty(),
            crm_entity_uuid=crm_entity_uuid,
            partner=partner_domain,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        # Should have edge from individual_portfolio to gp_entity
        gp_entity_node_id = f"{main_fund_uuid}_{gp_entity_fund_uuid}"
        matching_edges = [
            e
            for e in result.edges
            if e.from_node_id == str(crm_entity_uuid)
            and e.to_node_id == gp_entity_node_id
        ]
        assert len(matching_edges) == 1

    def test_build_graph_delegates_to_base_builder(
        self,
        mocker: MockerFixture,
        firm_uuid: UUID,
        crm_entity_uuid: UUID,
        gp_entity_fund_uuid: UUID,
        partner_domain: PartnerDomain,
        mock_base_graph: Graph,
    ):
        mock_graph_builder = mocker.MagicMock(spec=GraphBuilder)
        mock_graph_builder.build_graph.return_value = mock_base_graph
        empty_relationship_graph = InvestedInRelationshipGraph.empty()

        builder = CrmEntityGraphBuilder(graph_builder=mock_graph_builder)

        builder.build_graph(
            firm_uuid=firm_uuid,
            invested_in_relationship_graph=empty_relationship_graph,
            crm_entity_uuid=crm_entity_uuid,
            partner=partner_domain,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        mock_graph_builder.build_graph.assert_called_once_with(
            firm_uuid=firm_uuid,
            invested_in_relationship_graph=empty_relationship_graph,
            end_date=None,
        )
```

**Step 2: Run test to verify it fails**

Run: `poetry run pytest tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py -v`
Expected: FAIL with ImportError

**Step 3: Write minimal implementation**

```python
# fund_admin/entity_map/crm_entity_graph_builder.py
from datetime import date
from uuid import UUID

from fund_admin.capital_account.domain import PartnerDomain
from fund_admin.entity_map.domain import Edge, Graph
from fund_admin.entity_map.graph_builder import GraphBuilder
from fund_admin.entity_map.invested_in_relationship_graph import (
    InvestedInRelationshipGraph,
)
from fund_admin.entity_map.node_builders.gp_entity_node_builder import (
    to_gp_entity_node_id,
)
from fund_admin.entity_map.node_builders.individual_portfolio_node_builder import (
    IndividualPortfolioNodeBuilder,
)


class CrmEntityGraphBuilder:
    """
    Builds graphs for CRM entity (investor) portfolio views.

    This builder composes the base GraphBuilder and adds an individual_portfolio
    root node representing the investor. It keeps CRM entity-specific logic
    isolated from the shared GraphBuilder.
    """

    def __init__(
        self,
        graph_builder: GraphBuilder | None = None,
        individual_portfolio_builder: IndividualPortfolioNodeBuilder | None = None,
    ):
        self._graph_builder = graph_builder or GraphBuilder()
        self._individual_portfolio_builder = (
            individual_portfolio_builder or IndividualPortfolioNodeBuilder()
        )

    @classmethod
    def create_lightweight(cls) -> "CrmEntityGraphBuilder":
        """Create a lightweight builder that skips metrics."""
        return cls(graph_builder=GraphBuilder.create_lightweight())

    def build_graph(
        self,
        firm_uuid: UUID,
        invested_in_relationship_graph: InvestedInRelationshipGraph,
        crm_entity_uuid: UUID,
        partner: PartnerDomain,
        gp_entity_fund_uuid: UUID,
        end_date: date | None = None,
    ) -> Graph:
        """
        Build a graph rooted at an individual portfolio node.

        Args:
            firm_uuid: The firm UUID
            invested_in_relationship_graph: Pre-built relationship graph
            crm_entity_uuid: The CRM entity UUID (becomes root node ID)
            partner: Partner record for the investor (provides name, type)
            gp_entity_fund_uuid: UUID of the GP entity fund they're invested in
            end_date: Optional end date for metrics

        Returns:
            Graph with individual_portfolio as root, connected to GP entity
        """
        # 1. Delegate to base builder for fund graph
        base_graph = self._graph_builder.build_graph(
            firm_uuid=firm_uuid,
            invested_in_relationship_graph=invested_in_relationship_graph,
            end_date=end_date,
        )

        # 2. Build root node for the investor
        root_node = self._individual_portfolio_builder.build_node(
            crm_entity_uuid=crm_entity_uuid,
            partner=partner,
            gp_entity_fund_uuid=gp_entity_fund_uuid,
        )

        # 3. Find the GP entity node to connect to
        # GP entity node ID pattern: {main_fund_uuid}_{gp_entity_fund_uuid}
        gp_entity_node_id = self._find_gp_entity_node_id(
            base_graph, gp_entity_fund_uuid
        )

        # 4. Create edge from individual_portfolio to GP entity
        root_edge = Edge(
            from_node_id=str(crm_entity_uuid),
            to_node_id=gp_entity_node_id,
        )

        return Graph(
            nodes=[root_node] + base_graph.nodes,
            edges=[root_edge] + base_graph.edges,
        )

    def _find_gp_entity_node_id(
        self, graph: Graph, gp_entity_fund_uuid: UUID
    ) -> str:
        """Find the GP entity node ID in the graph."""
        gp_entity_uuid_str = str(gp_entity_fund_uuid)
        for node in graph.nodes:
            if node.type == "gp_entity" and gp_entity_uuid_str in node.id:
                return node.id
        # Fallback: construct the ID if not found (shouldn't happen in practice)
        raise ValueError(
            f"GP entity node not found for fund UUID {gp_entity_fund_uuid}"
        )
```

**Step 4: Run test to verify it passes**

Run: `poetry run pytest tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py -v`
Expected: PASS

**Step 5: Run linters**

Run: `poetry run ruff format fund_admin/entity_map/crm_entity_graph_builder.py && poetry run ruff check fund_admin/entity_map/crm_entity_graph_builder.py`

**Step 6: Commit**

```bash
git add fund_admin/entity_map/crm_entity_graph_builder.py tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py
git commit -m "feat(entity-map): add CrmEntityGraphBuilder"
```

---

## Task 4: Integrate into EntityMapService

**Files:**
- Modify: `fund_admin/entity_map/entity_map_service.py`

**Step 1: Read current implementation**

Review `get_crm_entity_tree()` method to understand current structure.

**Step 2: Update imports and add builder**

Add to imports:
```python
from fund_admin.entity_map.crm_entity_graph_builder import CrmEntityGraphBuilder
```

**Step 3: Modify get_crm_entity_tree to use CrmEntityGraphBuilder**

```python
def get_crm_entity_tree(
    self,
    firm_id: UUID,
    crm_entity_uuid: UUID,
    end_date: date | None = None,
) -> Graph:
    """
    Build a graph rooted at a CRM Entity with full metrics enrichment.
    """
    # Fetch partner info for the CRM entity
    partner_service = PartnerService()
    partners = partner_service.list_domain_objects(
        crm_entity_ids=[crm_entity_uuid],
        firm_ids=[firm_id],
    )

    if not partners:
        return Graph(nodes=[], edges=[])

    partner = partners[0]

    # Get the GP entity fund UUID from the partner's fund
    fund_service = FundService()
    partner_fund = fund_service.get_by_fund_id(fund_id=partner.fund_id)
    if not partner_fund or not partner_fund.uuid:
        return Graph(nodes=[], edges=[])

    gp_entity_fund_uuid = partner_fund.uuid

    # Build the relationship graph
    invested_in_relationship_graph = InvestedInRelationshipGraphBuilder(
        fund_service=fund_service,
        partner_service=partner_service,
    ).build_for_crm_entity(firm_id=firm_id, crm_entity_uuid=crm_entity_uuid)

    # Use CrmEntityGraphBuilder to add individual_portfolio root node
    crm_entity_graph_builder = CrmEntityGraphBuilder(
        graph_builder=self._graph_builder,
    )

    return crm_entity_graph_builder.build_graph(
        firm_uuid=firm_id,
        invested_in_relationship_graph=invested_in_relationship_graph,
        crm_entity_uuid=crm_entity_uuid,
        partner=partner,
        gp_entity_fund_uuid=gp_entity_fund_uuid,
        end_date=end_date,
    )
```

**Step 4: Run existing backend tests**

Run: `poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py -v -k crm_entity`
Expected: Tests should still pass (may need updates for new node)

**Step 5: Run linters**

Run: `poetry run ruff format fund_admin/entity_map/entity_map_service.py && poetry run ruff check fund_admin/entity_map/entity_map_service.py`

**Step 6: Commit**

```bash
git add fund_admin/entity_map/entity_map_service.py
git commit -m "feat(entity-map): integrate CrmEntityGraphBuilder into service"
```

---

## Task 5: Update Backend Integration Tests

**Files:**
- Modify: `tests/backend/fund_admin/entity_map/test_entity_map_service.py`

**Step 1: Update existing CRM entity tests to assert individual_portfolio node exists**

Add assertions to existing tests:

```python
def test_get_crm_entity_tree_includes_individual_portfolio_node(self, ...):
    # ... existing setup ...

    graph = service.get_crm_entity_tree(
        firm_id=firm.uuid,
        crm_entity_uuid=crm_entity.id,
    )

    # Find individual_portfolio node
    individual_portfolio_nodes = [
        n for n in graph.nodes if n.type == "individual_portfolio"
    ]
    assert len(individual_portfolio_nodes) == 1

    root_node = individual_portfolio_nodes[0]
    assert root_node.id == str(crm_entity.id)
    assert root_node.name == partner.name

    # Verify edge to GP entity exists
    root_edges = [e for e in graph.edges if e.from_node_id == str(crm_entity.id)]
    assert len(root_edges) == 1
```

**Step 2: Run tests**

Run: `poetry run pytest tests/backend/fund_admin/entity_map/test_entity_map_service.py -v -k crm_entity`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/backend/fund_admin/entity_map/test_entity_map_service.py
git commit -m "test(entity-map): add assertions for individual_portfolio node"
```

---

## Task 6: Manual Verification

**Step 1: Start local server**

Run: `poetry run python manage.py runserver`

**Step 2: Test with curl**

```bash
curl -s -H "x-carta-user-id: 25" \
  "http://localhost:9000/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/?lightweight=true" \
  | python3 -m json.tool | head -50
```

Expected: Response includes node with `"type": "individual_portfolio"` and `"name": "John Daley"` at root.

**Step 3: Verify edge structure**

Check that there's an edge from the individual_portfolio node to the GP entity node.

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add node type to domain | `domain.py` |
| 2 | Create IndividualPortfolioNodeBuilder | New builder + tests |
| 3 | Create CrmEntityGraphBuilder | New builder + tests |
| 4 | Integrate into EntityMapService | `entity_map_service.py` |
| 5 | Update backend integration tests | Test file |
| 6 | Manual verification | curl commands |

---
date: 2026-02-05
description: Design for adding individual_portfolio node type to entity map CRM entity views
repository: fund-admin
tags: [entity-map, crm-entity, individual-portfolio, partner-dashboard, architecture]
---

# Individual Portfolio Node Design

## Overview

Add a new `individual_portfolio` node type to represent the investor at the root of CRM entity (investor portfolio) views. Currently, the entity map for a CRM entity shows funds and GP entities but not the individual investor themselves.

**Current behavior:**
```
[ GP Entity ] -> [ Main Fund ] -> [ Portfolio ] -> [ Assets ]
```

**Target behavior:**
```
[ John Daley (individual_portfolio) ] -> [ GP Entity ] -> [ Main Fund ] -> [ Portfolio ] -> [ Assets ]
```

## Decisions

| Question | Decision | Rationale |
|----------|----------|-----------|
| Node type name | `individual_portfolio` | Aligns with Partner Dashboard naming; distinct from fund `portfolio` type |
| Edge target | GP Entity node | Mirrors actual investment structure; extend to multi-fund later |
| Data source | Partner record | Data already fetched; has name, partner_type; consistent with other nodes |
| Lightweight mode | Always include node | Root node must always appear; metrics can be empty |
| Architecture | Separate `CrmEntityGraphBuilder` | Clean separation; doesn't pollute shared `GraphBuilder` or service layer |

## Architecture

### Layer Separation

```
┌─────────────────────────────────────────────────────────────────┐
│  EntityMapService.get_crm_entity_tree()                         │
│  - Orchestrates                                                 │
│  - Uses CrmEntityGraphBuilder for CRM entity views              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  CrmEntityGraphBuilder                                          │
│  - Composes GraphBuilder (doesn't modify it)                    │
│  - Adds individual_portfolio node and edge                      │
│  - CRM entity-specific concerns isolated here                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GraphBuilder (unchanged)                                       │
│  - Shared core graph building                                   │
│  - Used by firm view, fund view, journal view                   │
│  - No knowledge of individual_portfolio                         │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principle

The `individual_portfolio` node is **only** exposed via the CRM entity API (`/entity-atlas/crm-entity/{uuid}/`). It never appears in:
- Firm view (`/firm/{uuid}/entity-atlas/`)
- Fund view (`/fund/{uuid}/entity-atlas/v2`)
- Journal impact view

This isolation is achieved by keeping the logic in `CrmEntityGraphBuilder`, which is only used by `get_crm_entity_tree()`.

## Node Structure

```python
Node(
    id="a2f23ebe-3675-45f7-867e-d3ad5f0effaf",  # CRM entity UUID
    type="individual_portfolio",
    name="John Daley",  # From Partner record
    metadata={
        "partner_uuid": "2eec2da3-c192-4563-9607-6014f829a8ed",
        "partner_type": "managing_member",
        "fund_id": 699,
        "fund_uuid": "4a55f602-375c-4211-a579-09075405de08",
    },
    metrics=MetricsOverTime.empty(),  # Or populated if not lightweight
)
```

## Edge Structure

```python
Edge(
    from_node_id="a2f23ebe-...",  # individual_portfolio (CRM entity UUID)
    to_node_id="4b6a4f7b-..._4a55f602-...",  # GP Entity node ID pattern
    weight=None,
)
```

The GP Entity node ID follows the pattern `{main_fund_uuid}_{gp_entity_fund_uuid}`.

## Files to Create

| File | Purpose |
|------|---------|
| `fund_admin/entity_map/crm_entity_graph_builder.py` | Composes GraphBuilder, adds individual_portfolio root node |
| `fund_admin/entity_map/node_builders/individual_portfolio_node_builder.py` | Builds the individual_portfolio node from Partner data |
| `tests/unit/fund_admin/entity_map/test_crm_entity_graph_builder.py` | Unit tests for CRM entity graph builder |
| `tests/unit/fund_admin/entity_map/node_builders/test_individual_portfolio_node_builder.py` | Unit tests for node builder |

## Files to Modify

| File | Change |
|------|--------|
| `fund_admin/entity_map/domain.py` | Add `"individual_portfolio"` to `NodeType` literal and `human_readable_node_type` dict |
| `fund_admin/entity_map/entity_map_service.py` | Use `CrmEntityGraphBuilder` in `get_crm_entity_tree()` |

## Files NOT Modified

- `fund_admin/entity_map/graph_builder.py` - Unchanged, shared core
- `fund_admin/entity_map/invested_in_relationship_graph.py` - Unchanged
- Other entity map views - Unchanged

## Testing Strategy

### Unit Tests

**`test_individual_portfolio_node_builder.py`:**
- Node creation with valid partner data
- Metadata structure correctness
- Name sourced from partner record

**`test_crm_entity_graph_builder.py`:**
- individual_portfolio node added to graph
- Edge connects to GP Entity node
- Lightweight mode still includes the node
- Delegates correctly to GraphBuilder

### Backend Integration Tests

Update `tests/backend/fund_admin/entity_map/test_entity_map_service.py`:
- Assert individual_portfolio node exists in CRM entity tree
- Verify edge from individual_portfolio → gp_entity
- Test with John Daley's CRM entity UUID

### Manual Verification

```bash
# Should return graph with John Daley as root node
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/?lightweight=true"
```

## Future Extensions

### Multi-Fund Support

When a CRM entity has Partner records in multiple funds, the individual_portfolio node will have multiple outbound edges:

```
                    ┌──> [ GP Entity A ] -> [ Main Fund A ]
[ Individual ] ─────┼──> [ GP Entity B ] -> [ Main Fund B ]
                    └──> [ Fund C ] -> [ Portfolio ]
```

Logic stays contained in `CrmEntityGraphBuilder`. The node builder remains unchanged; only edge creation logic expands.

### Multi-Firm Support

Same pattern as multi-fund. The individual_portfolio node can have edges to investments across different firms. This is already partially supported by `build_for_crm_entity()` which handles multi-firm scenarios.

## Test Data Reference

| Entity | UUID |
|--------|------|
| John Daley (CRM Entity) | `a2f23ebe-3675-45f7-867e-d3ad5f0effaf` |
| John Daley (Partner) | `2eec2da3-c192-4563-9607-6014f829a8ed` |
| Krakatoa Fund IV GP (GP Entity fund) | `4a55f602-375c-4211-a579-09075405de08` |
| Krakatoa Ventures Fund IV (Main Fund) | `4b6a4f7b-e79d-42d2-9dc9-d35fb0df6a07` |
| Krakatoa Ventures (Firm) | `186fb573-a22d-4c82-8ad3-3186f9095a41` |

## Related

- [20260205__plan__individual-portfolio-node-implementation.md](20260205__plan__individual-portfolio-node-implementation.md) — Implementation plan for this design
- [20260209__investigation__portfolio-node-unification.md](20260209__investigation__portfolio-node-unification.md) — Follow-up work to unify portfolio node types
- [20260211__plan__multi-fund-root-fix.md](20260211__plan__multi-fund-root-fix.md) — Fix for multi-fund edge selection logic

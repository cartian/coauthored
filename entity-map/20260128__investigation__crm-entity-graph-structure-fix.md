---
date: 2026-01-28
description: Agent prompt and fix documentation for incorrect graph structure in CRM entity views
repository: fund-admin
tags: [bug-fix, entity-map, crm-entity, agent-prompt]
---

# Agent Prompt: Fix CRM Entity-Rooted Graph Structure

## Context

You are working on PR #49859 in the `carta/fund-admin` repository. This PR implements Phase 1 of "CRM Entity-rooted graph views" for the entity-map feature.

**Tech Design Location:** `~/Desktop/tech-design.md`

**Jira:** GPE-215

## Problem Statement

The current implementation returns data correctly but structures the graph incorrectly. The CRM Entity should be the ROOT of the graph, but instead the graph is rooted at the Fund with the CRM Entity appearing as just another partner node buried among hundreds of other partners.

### Current (Incorrect) Graph Structure

```
Fund (Lira Capital Growth Fund I)     ← Graph is rooted here (WRONG)
       │
       └──► fund_partners node (715 total)
                 │
                 ├──► James Brewer    ← CRM Entity buried here as 1 of 715
                 ├──► Kevin Houston
                 ├──► Dr. Jacqueline Johnson DDS
                 └──► ... 712 more partners
```

The API returns:
- 2 nodes: 1 `fund` node + 1 `fund_partners` node
- 1 edge: fund → fund_partners
- 715 children nested inside fund_partners

### Expected (Correct) Graph Structure

Per the tech design, a "CRM Entity-rooted graph view" should have the CRM Entity at the ROOT:

```
CRM Entity (James Brewer)     ← Graph should be rooted HERE
       │
       ├──► GP Entity (if partner record is in a GP Entity)
       │         │
       │         └──► Main Fund (that GP Entity manages)
       │                   │
       │                   ├──► Feeder funds
       │                   └──► Connected entities
       │
       └──► Regular Fund (if directly invested)
                   │
                   └──► Connected entities
```

The graph should answer the question: "What funds am I invested in?" from the GP Member's perspective, showing THEIR investment positions flowing outward.

## Root Cause

The implementation in `invested_in_relationship_graph.py` correctly:
1. Finds Partner records for the CRM Entity
2. Traverses GP Entity → Main Fund relationships via `ManagingEntityLinksService`
3. Builds subgraphs using existing `filtered_to_fund_subgraph()`

However, it then passes the result to the existing `GraphBuilder.build_graph()` which is **fund-centric**. The GraphBuilder was designed for firm-rooted and fund-rooted views, not CRM entity-rooted views. It structures output from the fund's perspective.

## Files to Examine

1. **Graph Builder (builds the final node/edge structure):**
   - `fund_admin/entity_map/graph_builder.py`

2. **Relationship Graph Builder (finds relationships):**
   - `fund_admin/entity_map/invested_in_relationship_graph.py`
   - Focus on `build_for_crm_entity()` method

3. **Service Layer (orchestration):**
   - `fund_admin/entity_map/entity_map_service.py`
   - Focus on `get_crm_entity_tree()` method

4. **Domain Objects:**
   - `fund_admin/entity_map/domain.py`
   - Contains `Graph`, `Node`, `Edge` definitions

5. **View Layer:**
   - `fund_admin/entity_map/views/entity_map_crm_entity_view.py`

6. **Tests:**
   - `tests/unit/fund_admin/entity_map/test_invested_in_relationship_graph.py`
   - `tests/unit/fund_admin/entity_map/views/test_entity_map_crm_entity_view.py`

## Requirements for the Fix

### 1. Graph Structure Requirements

The returned `Graph` object must have:

- **Root node:** A node representing the CRM Entity itself (type: `crm_entity` or similar)
- **Investment edges:** Edges FROM the CRM Entity TO the funds/entities they're invested in
- **Hierarchical flow:** The graph should flow outward from the CRM Entity:
  ```
  CRM Entity → GP Entity → Main Fund → Feeders/Connected
  CRM Entity → Regular Fund → Feeders/Connected
  ```

### 2. Node Requirements

Create a new node type for the CRM Entity root:
```python
{
    "id": "<crm_entity_uuid>",
    "type": "crm_entity",  # New node type
    "name": "<entity_name or 'Portfolio'>",
    "metadata": {
        "crm_entity_uuid": "<uuid>",
    },
    "metrics": {
        # Aggregated metrics across all investments (optional for V1)
    },
    "children": []  # Or include investment positions as children
}
```

### 3. Edge Requirements

Edges should represent the investment relationship:
```python
{
    "source": "<crm_entity_uuid>",
    "target": "<fund_or_gp_entity_uuid>",
    "type": "invested_in"  # Or appropriate relationship type
}
```

### 4. Preserve Existing Functionality

- The existing fund metrics, NAV data, and partner-level details should still be available
- The `lightweight` and `end_date` query parameters should continue to work
- Do not break existing firm-rooted or fund-rooted views

## Implementation Approach

Consider these options:

### Option A: Extend GraphBuilder
Add a new method to `GraphBuilder` specifically for CRM entity-rooted graphs:
```python
def build_crm_entity_graph(
    self,
    crm_entity_uuid: UUID,
    invested_in_relationship_graph: InvestedInRelationshipGraph,
    end_date: date | None = None,
) -> Graph:
    # Build graph with CRM entity as root
    ...
```

### Option B: Post-Process the Graph
Transform the fund-centric graph into a CRM entity-rooted graph after building:
```python
def restructure_for_crm_entity(
    self,
    crm_entity_uuid: UUID,
    fund_centric_graph: Graph,
) -> Graph:
    # Create CRM entity root node
    # Restructure edges to flow from CRM entity
    ...
```

### Option C: New Graph Builder
Create a dedicated `CrmEntityGraphBuilder` class that builds graphs from the CRM entity perspective from the start.

## Acceptance Criteria

1. **Graph root is CRM Entity:** The returned graph has the CRM Entity as its root node, not a fund
2. **Correct edge direction:** Edges flow FROM the CRM Entity TO their investments
3. **Investment visibility:** Shows all funds the CRM Entity is invested in (directly or via GP Entity traversal)
4. **Metrics preserved:** Fund metrics, NAV data, and other financial data remain accurate
5. **Query params work:** `lightweight=true` and `end_date=YYYY-MM-DD` continue to function
6. **Tests pass:** All existing tests pass, new tests cover the restructured graph
7. **No regression:** Existing firm-rooted and fund-rooted views are unaffected

## Test Verification

After implementing, verify with:

```bash
# Full response - should show CRM entity as root
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/eee12355-f79c-4bc8-9076-fae30c6ee4a0/entity-atlas/crm-entity/c502de6c-dfba-4374-ab62-4b3ceebeb155/"

# Verify root node type
# Expected: First node should be type "crm_entity" with id matching the queried UUID
```

The response should look like:
```json
{
  "nodes": [
    {
      "id": "c502de6c-dfba-4374-ab62-4b3ceebeb155",
      "type": "crm_entity",
      "name": "James Brewer",
      ...
    },
    {
      "id": "83ae1973-1027-4fd4-9494-98f45c1a329b",
      "type": "fund",
      "name": "Lira Capital Growth Fund I",
      ...
    }
  ],
  "edges": [
    {
      "source": "c502de6c-dfba-4374-ab62-4b3ceebeb155",
      "target": "83ae1973-1027-4fd4-9494-98f45c1a329b",
      "type": "invested_in"
    }
  ]
}
```

## Additional Context

- The tech design at `~/Desktop/tech-design.md` has the full architecture and rationale
- The driving use case is GP Members answering "What funds am I invested in?"
- V1 scope intentionally defers portfolio company nodes - focus on fund-level visibility
- This is Phase 1 (backend only) - frontend integration comes in Phase 3

## Related

- [20260126__design__crm-entity-graph-views.md](20260126__design__crm-entity-graph-views.md) — Original design for CRM entity graph views that this investigation was validating
- [20260128__test__crm-entity-api-results.md](20260128__test__crm-entity-api-results.md) — Manual testing results that revealed the incorrect graph structure

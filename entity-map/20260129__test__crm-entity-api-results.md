---
date: 2026-01-29
description: Manual API testing results for CRM Entity-Rooted Graph views (Phase 1/2)
repository: fund-admin
tags: [entity-map, crm-entity, api-testing, graph-visualization, gp-entity]
---

# CRM Entity-Rooted Graph API Test Results

| | |
|---|---|
| **PR** | #49859 - feat(entity-map): add CRM entity-rooted graph views (Phase 1) |
| **Date Tested** | January 29, 2026 |
| **Status** | All tests passing |

---

## Executive Summary

This document records manual API testing of the CRM Entity-rooted graph endpoint, which builds an entity map from the perspective of a GP Entity fund.

**Key Findings:**
- All 9 test cases pass
- IDOR protection correctly rejects cross-organization queries
- GP Entity → Main Fund investment relationships render correctly
- Connected funds (e.g., Feeder Funds) appear in the graph as expected

**Bug Fixed During Testing:** GP Entity funds were missing from edge creation due to a `KeyError`. Fixed by adding `include_gp_entity_funds_in_edges` parameter.

---

## Table of Contents

1. [API Reference](#api-reference)
2. [Understanding GP Entity Relationships](#understanding-gp-entity-relationships)
3. [Test Environment](#test-environment)
4. [Test Results](#test-results)
5. [Bug Fix Documentation](#bug-fix-documentation)
6. [Known Limitations](#known-limitations)
7. [Code References](#code-references)

---

## API Reference

### Endpoint

```
GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `lightweight` | boolean | When `true`, returns minimal structure without partner details or metrics |
| `end_date` | date (YYYY-MM-DD) | Calculate metrics as of a specific date |

### Authentication

| Header | Value | Description |
|--------|-------|-------------|
| `x-carta-user-id` | `25` | Fred Administrator (staff user for testing) |

### Example Request

```bash
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/"
```

---

## Understanding GP Entity Relationships

### The Dual Relationship Model

A GP Entity fund has **two distinct relationships** with its Main Fund:

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                     GP ENTITY                           │
                    │               (e.g., Fund IV GP, L.P.)                  │
                    └─────────────────────────┬───────────────────────────────┘
                                              │
                    ┌─────────────────────────┴───────────────────────────────┐
                    │                                                         │
                    ▼                                                         ▼
    ┌───────────────────────────────┐                     ┌───────────────────────────────┐
    │    INVESTMENT RELATIONSHIP    │                     │   MANAGEMENT RELATIONSHIP     │
    │                               │                     │                               │
    │  - Via Partner record         │                     │  - Via ManagingEntityLinks    │
    │  - partner_type:              │                     │  - Represents fiduciary duty  │
    │    general_partner            │                     │  - Used for fund discovery    │
    │  - Creates graph edges        │                     │    in CRM Entity builder      │
    │  - Has NAV (often $0)         │                     │                               │
    └───────────────────────────────┘                     └───────────────────────────────┘
```

### How Investment Relationships Are Determined

The system identifies fund-to-fund investments through **Partner records with an `entity_id` field**:

```
Partner Record Structure:
┌──────────────────────────────────────────────────────────────┐
│  fund_id: 695          (Partner record lives in Main Fund)   │
│  entity_id: <uuid>     (Points back to the investing fund)   │
│  partner_type: general_partner | limited_partner             │
│  name: "Krakatoa Fund IV GP, L.P."                           │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
              Creates edge: entity_id fund ──► fund_id fund
```

### Partner Types Reference

| Type | Description | Typical NAV | Graph Behavior |
|------|-------------|-------------|----------------|
| `general_partner` | GP Entity investing in Main Fund | Small or zero (1-2% of fund) | Creates investment edge |
| `limited_partner` | LP or Fund investing in another fund | Variable | Creates investment edge |
| `member` | Individual partner in GP Entity fund | N/A | Appears as child node |
| `managing_member` | Managing GP in GP Entity fund | N/A | **Filtered from display** |

---

## Test Environment

### Firm Under Test

| Attribute | Value |
|-----------|-------|
| **Name** | Krakatoa Ventures |
| **UUID** | `186fb573-a22d-4c82-8ad3-3186f9095a41` |

### CRM Entities Tested

| CRM Entity | UUID | Type |
|------------|------|------|
| Krakatoa Fund III GP, L.P. | `e96c498b-e329-4e5e-b6b9-eae44e30f70f` | GP Entity |
| Krakatoa Meetly SPV GP, LLC | `0c2d58f8-d857-47df-9c0a-d67684bca75c` | GP Entity (SPV) |
| Krakatoa Fund IV GP, L.P. | `4a55f602-375c-4211-a579-09075405de08` | GP Entity (Primary) |

### Primary Test Case: Fund IV Structure

This is the primary demo case, featuring a GP Entity with multiple investment relationships.

**Funds:**

| Fund | fund_id | carta_id | UUID | Type |
|------|---------|----------|------|------|
| Krakatoa Ventures Fund IV, L.P. | 695 | 498 | `4b6a4f7b-e79d-42d2-9dc9-d35fb0df6a07` | Main Fund |
| Krakatoa Fund IV GP, L.P. | 699 | 502 | `4a55f602-375c-4211-a579-09075405de08` | GP Entity |
| Krakatoa Feeder Fund IV | 1176 | 2117 | `c04456a9-b623-488c-afbc-2265876a6994` | Feeder Fund |

**Investment Relationships:**

| Investor | Investee | Partner Type | NAV |
|----------|----------|--------------|-----|
| GP Entity (699) | Main Fund (695) | `general_partner` | $0.00 |
| Feeder Fund (1176) | Main Fund (695) | `limited_partner` | $2,999,430.16 |

**Visual Representation:**

```
    ┌──────────────────────┐          ┌──────────────────────┐
    │      GP ENTITY       │          │     FEEDER FUND      │
    │   Fund IV GP, L.P.   │          │  Feeder Fund IV      │
    │   (fund_id: 699)     │          │  (fund_id: 1176)     │
    │                      │          │                      │
    │   general_partner    │          │   limited_partner    │
    │   NAV: $0.00         │          │   NAV: $2,999,430    │
    └──────────┬───────────┘          └──────────┬───────────┘
               │                                 │
               │         invests in              │
               └────────────┬────────────────────┘
                            │
                            ▼
               ┌────────────────────────┐
               │       MAIN FUND        │
               │  Krakatoa Ventures     │
               │  Fund IV, L.P.         │
               │  (fund_id: 695)        │
               └────────────┬───────────┘
                            │
                            ▼
                      ┌───────────┐
                      │ PORTFOLIO │
                      │ 10 assets │
                      └───────────┘
```

### Demo User: John Daley

John Daley represents the prototypical GP user for CRM Entity views.

| Attribute | Value |
|-----------|-------|
| **Name** | John Daley |
| **Partner UUID** | `2eec2da3-c192-4563-9607-6014f829a8ed` |
| **CRM Entity UUID** | `a2f23ebe-3675-45f7-867e-d3ad5f0effaf` |
| **CRM Organization** | `1f8d189d-6837-4293-95c7-cc4bdb1287c6` |
| **Fund** | Krakatoa Fund IV GP, L.P. (fund_id: 699) |
| **Partner Type** | `managing_member` |

**Important:** John Daley's CRM entity belongs to an **external organization**, not Krakatoa Ventures. This means:
1. He cannot be queried from Krakatoa's endpoint (IDOR protection)
2. His `managing_member` type causes him to be filtered from partner lists
3. His portfolio view requires calling the API from his organization's context

---

## Test Results

### Summary

| Test | Description | Status | Nodes | Edges |
|------|-------------|--------|-------|-------|
| 1 | Fund III GP - Full | Pass | 64 | 64 |
| 2 | Fund III GP - Lightweight | Pass | 1 | 1 |
| 3 | Fund III GP - Historical | Pass | 64 | 64 |
| 4 | Meetly SPV GP | Pass | 4 | 4 |
| 5 | Fund IV GP - Full (Primary) | Pass | 16 | 16 |
| 6 | Fund IV GP - Lightweight | Pass | 3 | 3 |
| 7 | IDOR - External Entity | Pass | N/A | N/A |
| 8 | IDOR - John Daley | Pass | N/A | N/A |
| 9 | Regression - Firm Map | Pass | 176 | 151 |

---

### Test 1: Fund III GP - Full Response

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/e96c498b-e329-4e5e-b6b9-eae44e30f70f/" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 64 |
| Edges | 64 |
| Node Types | `fund: 1`, `fund_partners: 1`, `portfolio: 1`, `asset: 61` |

**Graph Structure:**
```
    CRM Entity: Krakatoa Fund III GP, L.P.
                        │
                        │ invests in (general_partner)
                        ▼
              ┌─────────────────────┐
              │     MAIN FUND       │
              │ Fund III (id: 694)  │
              └─────────┬───────────┘
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
    ┌───────────┐              ┌───────────┐
    │  PARTNERS │              │ PORTFOLIO │
    │           │              │ 61 assets │
    └───────────┘              └───────────┘
```

---

### Test 2: Fund III GP - Lightweight

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/e96c498b-e329-4e5e-b6b9-eae44e30f70f/?lightweight=true" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 1 |
| Edges | 1 |
| Node Types | `fund: 1` |

**Response Excerpt:**
```json
{
  "nodes": [{
    "id": "e4c0e353-c3ff-489c-af9e-aff8f3ac024a",
    "type": "fund",
    "name": "Krakatoa Ventures Fund III, L.P."
  }],
  "edges": [{
    "from_node_id": "e96c498b-e329-4e5e-b6b9-eae44e30f70f",
    "to_node_id": "e4c0e353-c3ff-489c-af9e-aff8f3ac024a",
    "weight": null
  }]
}
```

---

### Test 3: Fund III GP - Historical Date

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/e96c498b-e329-4e5e-b6b9-eae44e30f70f/?end_date=2024-06-30" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 64 |
| Edges | 64 |
| Metrics Date | 2024-06-30 |

---

### Test 4: Meetly SPV GP

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/0c2d58f8-d857-47df-9c0a-d67684bca75c/" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 4 |
| Edges | 4 |
| Node Types | `fund: 1`, `fund_partners: 1`, `portfolio: 1`, `asset: 1` |

**Note:** This is a smaller SPV structure with a single portfolio asset.

---

### Test 5: Fund IV GP - Full Response (Primary)

This is the **primary test case** demonstrating GP Entity functionality with multiple investor funds.

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/4a55f602-375c-4211-a579-09075405de08/" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 16 |
| Edges | 16 |
| Node Types | `fund: 2`, `fund_partners: 2`, `gp_entity: 1`, `portfolio: 1`, `asset: 10` |

**Investment Edges:**

| From | To | NAV | Meaning |
|------|----|-----|---------|
| GP Entity UUID | Main Fund UUID | $0.00 | GP invests as general_partner |
| Feeder Fund UUID | Main Fund UUID | $2,999,430.16 | Feeder invests as limited_partner |

**Why the Feeder Fund Appears:**

When querying the GP Entity's graph, the API returns the **entire connected investment graph**. The Feeder Fund invests in the same Main Fund, so it appears to show the complete capital flow picture.

**Understanding the NAV Values:**
- **GP Entity: $0.00** — GP commitments are typically 1-2% of fund size. The GP's economic value comes from management fees and carried interest, not capital appreciation.
- **Feeder Fund: $2,999,430.16** — Represents actual LP capital invested in the Main Fund.

---

### Test 6: Fund IV GP - Lightweight

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/4a55f602-375c-4211-a579-09075405de08/?lightweight=true" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 3 |
| Edges | 3 |
| Node Types | `fund: 2`, `gp_entity: 1` |

**Nodes:** Feeder Fund IV, Main Fund IV, GP Entity Fund IV

---

### Test 7: IDOR - External CRM Entity

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/c502de6c-dfba-4374-ab62-4b3ceebeb155/" \
  -H "x-carta-user-id: 25"
```

**Result:**
```json
{
  "detail": "CRM entity does not belong to the specified firm.",
  "error_code": "permission_denied"
}
```

**Verification:** IDOR protection working correctly.

---

### Test 8: IDOR - John Daley's CRM Entity

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/" \
  -H "x-carta-user-id: 25"
```

**Result:**
```json
{
  "detail": "CRM entity does not belong to the specified firm.",
  "error_code": "permission_denied"
}
```

**Analysis:** John Daley's CRM entity belongs to organization `1f8d189d-...`, not Krakatoa Ventures. The IDOR protection correctly rejects this cross-organization query.

---

### Test 9: Regression - Firm Entity Map

Verifies that existing firm-wide entity map functionality remains unaffected.

**Request:**
```bash
curl -s -X GET \
  "http://localhost:9000/firm/186fb573-a22d-4c82-8ad3-3186f9095a41/entity-atlas/" \
  -H "x-carta-user-id: 25"
```

**Result:**
| Metric | Value |
|--------|-------|
| Status | 200 OK |
| Nodes | 176 |
| Edges | 151 |
| Node Types | `fund: 26`, `fund_partners: 13`, `gp_entity: 9`, `portfolio: 9`, `asset: 119` |

**Verification:** Existing functionality unchanged.

---

## Full vs Lightweight Comparison

| Attribute | Full | Lightweight |
|-----------|------|-------------|
| **Query Param** | (none) | `lightweight=true` |
| **Nodes (Fund III)** | 64 | 1 |
| **Edges (Fund III)** | 64 | 1 |
| **Partner Details** | Yes | No |
| **NAV Metrics** | Yes | No |
| **Response Size** | Large | ~2-3 KB |
| **Use Case** | Full portfolio view | Quick summary |

---

## Bug Fix Documentation

### Issue

A `KeyError` occurred when the invested-in relationship graph included GP Entity funds as investors.

**Error Location:** `graph_builder.py:305` in `_connect_fund_trees_by_invested_in_relationship`

### Root Cause

The `fund_id_to_node_id` dictionary excluded GP Entity funds, but the invested-in relationship graph could contain GP Entity funds as investors.

### Fix

Added `include_gp_entity_funds_in_edges` parameter to `build_graph()`:

```python
def build_graph(
    self,
    invested_in_relationship_graph: InvestedInRelationshipGraph,
    end_date: date | None = None,
    include_gp_entity_funds_in_edges: bool = False,  # NEW
) -> Graph:
```

### Files Changed

| File | Change |
|------|--------|
| `fund_admin/entity_map/graph_builder.py` | Added parameter and conditional logic |
| `fund_admin/entity_map/entity_map_service.py` | Pass `True` for CRM Entity views |
| `tests/unit/.../test_entity_map_service.py` | Updated assertions |

---

## Known Limitations

### Managing Member Filtering

Partners with `partner_type=managing_member` (like John Daley) are **filtered from display** in GP Entity partner lists.

**Reason:** The `exclude_gp_and_managing_member=True` flag in `PartnerMetadataFetcher` intentionally excludes these to avoid cluttering the firm-wide entity map with management roles.

**Potential Enhancement:** For CRM Entity views, consider adding `include_managing_members=True` parameter since managing members represent real capital commitments.

**Files:**
- `fund_admin/entity_map/partner_metadata_fetcher.py:57`
- `fund_admin/capital_account/services/partner.py`

---

## Code References

### Investment Relationship Discovery

| File | Line | Purpose |
|------|------|---------|
| `invested_in_relationship_graph.py` | 312-334 | `build_for_firm()` — discovers relationships via Partner `entity_id` |
| `invested_in_relationship_graph.py` | 343-448 | `build_for_crm_entity()` — builds graph rooted at CRM entity |
| `managing_entity_links_service.py` | — | `get_funds_from_managing_entity()` — finds managed funds |

### Graph Building

| File | Line | Purpose |
|------|------|---------|
| `graph_builder.py` | 301-349 | `_connect_fund_trees_by_invested_in_relationship()` — creates edges |
| `entity_map_service.py` | — | Service layer orchestrating graph construction |

### Partner Filtering

| File | Line | Purpose |
|------|------|---------|
| `partner_metadata_fetcher.py` | 56-58 | `exclude_gp_and_managing_member=True` filter |
| `partner.py` | — | `list_domain_objects()` — supports partner type filtering |

---

## Quick Reference

### Test Commands

```bash
# Full response
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/"

# Lightweight
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?lightweight=true"

# Historical date
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?end_date=2024-06-30"
```

### Key UUIDs

| Entity | UUID |
|--------|------|
| Krakatoa Ventures (firm) | `186fb573-a22d-4c82-8ad3-3186f9095a41` |
| Fund IV GP (primary test) | `4a55f602-375c-4211-a579-09075405de08` |
| Fund IV Main | `4b6a4f7b-e79d-42d2-9dc9-d35fb0df6a07` |
| Fund IV Feeder | `c04456a9-b623-488c-afbc-2265876a6994` |
| Fund III GP | `e96c498b-e329-4e5e-b6b9-eae44e30f70f` |
| Meetly SPV GP | `0c2d58f8-d857-47df-9c0a-d67684bca75c` |
| John Daley (CRM Entity) | `a2f23ebe-3675-45f7-867e-d3ad5f0effaf` |

---

## Unit Test Status

All 211 entity_map unit tests passing:

```
tests/unit/fund_admin/entity_map/
├── test_domain.py                    25 passed
├── test_entity_map_firm_view.py       3 passed
├── test_entity_map_journal_view.py    6 passed
├── test_entity_map_service.py         2 passed (updated)
├── test_fund_balance_sheet_handler.py 21 passed
├── test_gp_entity_node_builder.py    17 passed
├── test_hypothetical_allocation.py    2 passed
├── test_invested_in_relationship.py  33 passed
├── test_investment_relationships.py   8 passed
├── test_lightweight_graph_builder.py 11 passed
├── test_partner_node_builder.py       6 passed
├── test_portfolio_node_builder.py     5 passed
├── financial_reporting/              passed
├── journal_impact/                   37 passed
└── views/test_entity_map_crm.py       5 passed
```

---

## Conclusion

The CRM Entity API implementation is working correctly. Key validations:

1. **Graph Construction** — Builds connected graphs from CRM entity perspective
2. **Investment Modeling** — Correctly represents GP (`general_partner`) and LP (`limited_partner`) relationships
3. **NAV Accuracy** — GP shows $0.00, Feeder shows $2.9M (as expected)
4. **Security** — IDOR protection rejects cross-organization queries
5. **Backwards Compatibility** — Firm entity map unchanged
6. **Lightweight Mode** — Returns minimal data for quick summaries
7. **Historical Queries** — `end_date` parameter works correctly

### Key Insight

The GP Entity "invests in" the Main Fund via a Partner record with `partner_type: general_partner`. This is standard fund structure where the GP commits capital (typically 1-2%) alongside LPs. The $0.00 NAV is expected — GP economic value comes from fees and carried interest, not capital appreciation.

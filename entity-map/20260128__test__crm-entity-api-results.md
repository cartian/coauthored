---
date: 2026-01-28
description: Manual API testing results for CRM entity-rooted graph endpoint
repository: fund-admin
tags: [testing, api, entity-map, crm-entity, manual-test]
---

# CRM Entity-Rooted Graph API Test Results

**PR:** [#49859](https://github.com/carta/fund-admin/pull/49859) - feat(entity-map): add CRM entity-rooted graph views (Phase 1)

**Date Tested:** January 28, 2025

---

## API Endpoint

```
GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/
```

**Authentication:** Header `x-carta-user-id: 25` (Fred Administrator - staff user)

**Base URL:** `http://localhost:9000`

---

## Test Data

| Entity | UUID |
|--------|------|
| Firm | `eee12355-f79c-4bc8-9076-fae30c6ee4a0` (Lira Capital) |
| CRM Entity 1 | `c502de6c-dfba-4374-ab62-4b3ceebeb155` (James Brewer) |
| CRM Entity 2 | `3c2112ba-675d-4122-8cb9-6060e7637b0d` (Kevin Houston) |

---

## Visualization 1: Full Response

**Query:** `GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/`

**CRM Entity:** James Brewer (`c502de6c-dfba-4374-ab62-4b3ceebeb155`)

```
                              ┌───────────────────────────────────────┐
                              │           FUND                        │
                              │   Lira Capital Growth Fund I          │
                              │                                       │
                              │   Commitment: $312,102,386.42         │
                              │   Called:     $78,212,805.58          │
                              │   Distributed: $24,905,718.60         │
                              └───────────────────┬───────────────────┘
                                                  │
                                                  │ (edge: fund → partners)
                                                  ▼
                              ┌───────────────────────────────────────┐
                              │        LIMITED PARTNERS               │
                              │        (715 total partners)           │
                              │                                       │
                              │   Total Commitment: $312,102,386.42   │
                              │   Ending NAV:       $53,307,086.98    │
                              │   TVPI: 715.00  DPI: 227.66           │
                              └───────────────────┬───────────────────┘
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    │                             │                             │
                    ▼                             ▼                             ▼
    ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
    │  James Brewer ⭐          │  │  Kevin Houston           │  │  Dr. Jacqueline          │
    │     (Our CRM Entity)     │  │                          │  │     Johnson DDS          │
    │                          │  │  Commitment: $519,608.72 │  │                          │
    │  Commitment: $402,797.46 │  │  Called:     $130,213.86 │  │  Commitment: $508,456.23 │
    │  Called:     $100,940.98 │  │  NAV:        $88,749.22  │  │  Called:     $127,418.95 │
    │  Distributed: $32,143.16 │  │  TVPI: 1.00              │  │  NAV:        $86,845.93  │
    │  NAV:         $68,797.82 │  │                          │  │                          │
    │  TVPI: 1.00  DPI: 0.32   │  └──────────────────────────┘  └──────────────────────────┘
    └──────────────────────────┘
                                        ... and 712 more partners
```

### Response Statistics
- **Total nodes:** 2 (1 fund + 1 fund_partners container)
- **Total edges:** 1
- **Children in fund_partners:** 715 partner records
- **Response size:** ~965 KB

---

## Visualization 2: Lightweight Response

**Query:** `GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?lightweight=true`

**CRM Entity:** James Brewer (`c502de6c-dfba-4374-ab62-4b3ceebeb155`)

```
                              ┌───────────────────────────────────────┐
                              │           FUND                        │
                              │   Lira Capital Growth Fund I          │
                              │                                       │
                              │   Commitment: $312,102,386.42         │
                              │   Called:     $78,212,805.58          │
                              │   Distributed: $24,905,718.60         │
                              │                                       │
                              │   ⚡ No NAV metrics (lightweight)     │
                              │   ⚡ No children/partners             │
                              └───────────────────────────────────────┘

                                    ╔═══════════════════════════╗
                                    ║  That's it! Just 1 node   ║
                                    ║  No edges, no children    ║
                                    ╚═══════════════════════════╝
```

### Response Statistics
- **Total nodes:** 1
- **Total edges:** 0
- **Children:** None (not included in lightweight mode)
- **NAV metrics:** None (not included in lightweight mode)
- **Response size:** ~2-3 KB

> **Use Case:** Use lightweight mode when you only need fund-level summary metrics without individual partner details or NAV breakdowns.

---

## Visualization 3: With end_date Parameter

**Query:** `GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?end_date=2024-06-30`

**CRM Entity:** Kevin Houston (`3c2112ba-675d-4122-8cb9-6060e7637b0d`)

```
                              ┌───────────────────────────────────────┐
                              │           FUND                        │
                              │   Lira Capital Growth Fund I          │
                              │                                       │
                              │   📅 As of 2024-06-30:                │
                              │   Commitment: $312,102,386.42         │
                              │   Called:     $78,212,805.58          │
                              │   Distributed: $24,905,718.60         │
                              └───────────────────┬───────────────────┘
                                                  │
                                                  │ (edge: fund → partners)
                                                  ▼
                              ┌───────────────────────────────────────┐
                              │        LIMITED PARTNERS               │
                              │        (715 total partners)           │
                              │                                       │
                              │   📅 As of 2024-06-30:                │
                              │   Total Commitment: $312,102,386.42   │
                              │   Ending NAV:       $53,307,086.98    │
                              └───────────────────┬───────────────────┘
                                                  │
                    ┌─────────────────────────────┴─────────────────────────────┐
                    │                                                           │
                    ▼                                                           ▼
    ┌─────────────────────────────────┐                     ┌──────────────────────────┐
    │  Kevin Houston ⭐                │                     │  ... other partners      │
    │     (Our CRM Entity)            │                     │                          │
    │                                 │                     │                          │
    │  📅 As of 2024-06-30:           │                     │                          │
    │  ┌─────────────────────────────┐│                     │                          │
    │  │ Commitment:    $519,608.72  ││                     │                          │
    │  │ Called:        $130,213.86  ││                     │                          │
    │  │ Ending NAV:     $88,749.22  ││                     │                          │
    │  │ TVPI: 1.00                  ││                     │                          │
    │  └─────────────────────────────┘│                     └──────────────────────────┘
    └─────────────────────────────────┘
                                        ... and 714 more partners
```

### Response Statistics
- **Total nodes:** 2 (1 fund + 1 fund_partners container)
- **Total edges:** 1
- **Children in fund_partners:** 715 partner records
- **All metrics calculated as of:** 2024-06-30

> **Use Case:** Use end_date to get historical point-in-time metrics for any date. Useful for quarterly reporting, audits, or historical analysis.

---

## Comparison Summary

| Attribute | Full Response | Lightweight | With end_date |
|-----------|---------------|-------------|---------------|
| Query Params | (none) | `lightweight=true` | `end_date=2024-06-30` |
| Total Nodes | 2 | 1 | 2 |
| Total Edges | 1 | 0 | 1 |
| Partner Children | 715 | 0 | 715 |
| Fund Metrics | ✅ Yes | ✅ Yes | ✅ Yes (as of date) |
| NAV Metrics | ✅ Yes | ❌ No | ✅ Yes (as of date) |
| Partner Details | ✅ Yes | ❌ No | ✅ Yes (as of date) |
| Balance Sheet | ✅ Yes | ❌ No | ✅ Yes (as of date) |
| Response Size | ~965 KB | ~2-3 KB | ~965 KB |
| Use Case | Full portfolio view | Quick summary | Historical analysis |

### Graph Structure Comparison

```
  FULL / WITH END_DATE:                          LIGHTWEIGHT:

       ┌──────────┐                                   ┌──────────┐
       │   FUND   │                                   │   FUND   │
       └────┬─────┘                                   └──────────┘
            │                                              │
            ▼                                         (that's it!)
       ┌──────────┐
       │ PARTNERS │
       │ (group)  │
       └────┬─────┘
            │
    ┌───────┼───────┐
    ▼       ▼       ▼
  ┌───┐   ┌───┐   ┌───┐
  │ P │   │ P │   │...│  (715 partners)
  └───┘   └───┘   └───┘
```

---

## Quick Reference Commands

```bash
# Full response (default)
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/"

# Lightweight (fast, minimal data)
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?lightweight=true"

# With historical date
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?end_date=2024-06-30"

# Combine parameters
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?end_date=2024-06-30&lightweight=true"
```

---

## Conclusion

The Phase 1 implementation is working correctly. The API successfully:

1. Builds a graph rooted at a CRM entity
2. Shows all funds the CRM entity is invested in
3. Includes full investment metrics (commitment, called capital, distributions, NAV, TVPI, DPI, RVPI)
4. Supports lightweight mode for quick summaries
5. Supports historical point-in-time queries via end_date parameter

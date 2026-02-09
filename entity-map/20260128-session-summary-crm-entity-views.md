---
date: 2026-01-29
description: Session summary for CRM Entity-rooted views implementation
repository: fund-admin, carta-frontend-platform
tags: [entity-map, crm-entity, permissions, session-summary]
---

# Session Summary: CRM Entity-Rooted Views

## Current State

| Repository | Branch | Status |
|------------|--------|--------|
| fund-admin | `gpe-215.cartian.crm_entity_graph` | PR [#49859](https://github.com/carta/fund-admin/pull/49859) ready for review |
| carta-frontend-platform | `gpe-215.cartian.crm_entity_frontend` | Ready for PR creation |

| Component | Status |
|-----------|--------|
| Backend API | ✅ Complete |
| fund-admin frontend wrapper | ✅ Complete |
| entity-map federated module | ✅ Complete |

---

## What's Been Built

### Backend (Complete - fund-admin)

**Endpoint:**
```
GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/
```

| Parameter | Description |
|-----------|-------------|
| `lightweight=true` | Minimal structure without partner details |
| `end_date=YYYY-MM-DD` | Historical point-in-time metrics |

**Key components:**
- `build_for_crm_entity()` on `InvestedInRelationshipGraphBuilder` — Finds Partner records, traverses GP Entity → Main Fund relationships
- `get_crm_entity_tree()` on `EntityMapService` — Orchestrates graph building with metrics
- `EntityMapCrmEntityView` — API view with `IsFirmMember | IsStaff` permissions
- `empty()` / `merge()` helpers on `InvestedInRelationshipGraph`
- `include_gp_entity_funds_in_edges` param — Fixes edge creation for GP Entity investment relationships

**Security:**
- IDOR validation: CRM entity must belong to firm in URL
- Missing entity → `404`, wrong firm → `PermissionDenied`

### Frontend Wrapper (Complete - fund-admin)

Updated `frontend/src/entity-map/index.tsx` to accept and pass `crmEntityId` prop to the federated module.

### Entity-Map Federated Module (Complete - carta-frontend-platform)

**Files created/modified:**

| File | Change |
|------|--------|
| `Entry.tsx` | Added `crmEntityId` prop |
| `FundAdminContext.tsx` | Added `crmEntityId` to context |
| `constants.ts` | Added `CRM_ENTITY_VIEW_MODE` constant |
| `types.ts` | Extended `ViewMode` type |
| `use-get-crm-entity-map.ts` | New API hook (uses `callApi` direct fetch) |
| `CrmEntityView/CrmEntityView.tsx` | New view component |
| `CrmEntityView/useCrmEntityViewState.ts` | State management hook |
| `EntityMapContainer.tsx` | Routes to CrmEntityView when `crmEntityId` present |
| `LayerDropdown.tsx` | Fixed type narrowing for new ViewMode |

**Architecture:**
- Feature flag gating happens in the **parent** (fund-admin), not entity-map
- When `crmEntityId` is passed, entity-map renders `CrmEntityView`
- When `crmEntityId` is absent, existing `FundView` is rendered
- Uses `callApi` for API call since `fa-api-client` doesn't have the endpoint yet

---

## Key Discovery: Federated Architecture

The entity-map frontend is a **federated module from a separate repository**. In fund-admin, we only have a thin wrapper:

```tsx
// frontend/src/entity-map/index.tsx
<FARSComponent
    scope="entityMap"
    module="App"
    props={{ firmUuid, crmEntityId }}
/>
```

**Implication:** The actual `Entry.tsx`, `EntityMapContainer`, `CrmEntityView`, and API hooks live in carta-frontend-platform. The fund-admin PR only prepares the prop pass-through.

---

## Design Decisions

### Permission Model

| Layer | Responsibility | Implementation |
|-------|---------------|----------------|
| **View (gate)** | "Can you access this endpoint?" | `IsFirmMember \| IsStaff` |
| **Service (filter)** | "What can you see?" | Future: fund-level filtering |

**Why firm-level gating:** Existing fund-level permissions expect `fund_uuid` in URL. Our view has `crm_entity_uuid` instead. V1 doesn't show sensitive financial data, so firm-level is sufficient.

### Feature Flag Strategy

Feature flags are checked in **fund-admin** (the parent), not entity-map. This means:
- Entity-map stays "dumb" - it doesn't make its own feature flag API calls
- The presence of `crmEntityId` prop acts as the feature gate
- Parent only passes `crmEntityId` when the flag is enabled

### GP Entity Edge Handling

GP Entity funds were missing from `fund_id_to_node_id` mapping, causing `KeyError` when creating investment edges. Fixed by adding `include_gp_entity_funds_in_edges=True` for CRM Entity views.

---

## Commits

### fund-admin (gpe-215.cartian.crm_entity_graph)

| Commit | Description |
|--------|-------------|
| `b3b9f9f8ef9` | Phase 1: CRM entity-rooted graph views |
| `39e83b70756` | Phase 2: Firm membership and IDOR validation |
| `df4f58968ed` | Bug fix: GP Entity funds in edge mapping |
| `e7c08674be2` | Phase 3 prep: Frontend crmEntityId prop |
| `fe8d7aa9c85` | API schema regeneration |

### carta-frontend-platform (gpe-215.cartian.crm_entity_frontend)

| Change | Description |
|--------|-------------|
| Entry/Context | Accept and provide `crmEntityId` prop |
| ViewMode | Add `CRM_ENTITY_VIEW_MODE` constant and type |
| API Hook | `useGetCrmEntityMap` with direct `callApi` |
| CrmEntityView | New view component following FundView patterns |
| EntityMapContainer | Route to CrmEntityView when crmEntityId present |

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `20260126-tech-design.md` | Original tech design |
| `20260128-crm-entity-permissions-design.md` | Permission model rationale |
| `20260129-crm-entity-api-test-results.md` | Manual API testing (9 scenarios) |
| PR #49859 comments | Detailed test results with visualizations |

---

## Next Steps

1. **Create PR** for carta-frontend-platform changes
2. **Merge fund-admin PR** (#49859)
3. **Integrate** - Test end-to-end by:
   - Adding feature flag `GPE_215_CRM_ENTITY_MAP` (or similar)
   - Enabling flag for test accounts
   - Navigating to entity-map with `crmEntityId` in URL/props
4. **Future work:**
   - LP-side routing from Partner Dashboard
   - Managing member visibility
   - Update `fa-api-client` to include CRM entity endpoint

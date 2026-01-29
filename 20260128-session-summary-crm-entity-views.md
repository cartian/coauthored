---
date: 2026-01-28
description: Session summary for CRM Entity-rooted views implementation (Phases 1-2)
repository: fund-admin
tags: [entity-map, crm-entity, permissions, tdd, session-summary]
---

# Session Summary: CRM Entity-Rooted Views

## What We Accomplished Today

### Phase 1: Backend Infrastructure (Completed in Previous Session)
- Added `build_for_crm_entity()` to `InvestedInRelationshipGraphBuilder`
- Added `get_crm_entity_tree()` to `EntityMapService`
- Created `EntityMapCrmEntityView` with URL routing
- Wrote unit tests with TDD approach

### Phase 2: Permissions Integration (Completed Today)
- Replaced fund-level permissions (`HasViewInvestmentsPermission & HasViewPartnersPermission & HasViewFundPerformancePermission`) with firm-level (`IsFirmMember | IsStaff`)
- Added IDOR validation to prevent cross-firm data access
- Documented the permission design decision

**Key commits:**
- `36275c80dac` - Phase 1: CRM entity graph views
- `2ff7400c89d` - Phase 2: Firm membership and IDOR validation

---

## Design Decisions Made

### Permission Model Architecture

We chose a two-layer permission approach:

| Layer | Responsibility | Implementation |
|-------|---------------|----------------|
| **View (gate)** | "Can you knock on this door?" | `IsFirmMember \| IsStaff` |
| **Service (filter)** | "What can you see inside?" | Future: fund-level filtering |

**Why this approach:**
1. Existing fund-level permissions expect a `fund_uuid` in the URL - our view has `crm_entity_uuid` instead
2. V1 doesn't show sensitive financial data on nodes, so firm-level gating is sufficient
3. When financial data is added, fund-level filtering can be added in the service layer without changing the view

**IDOR Prevention:**
- Validate that `CRMEntity.organization_id` matches the `firm_uuid` from the URL
- Return `Http404` if CRM entity doesn't exist
- Return `PermissionDenied` if CRM entity belongs to a different firm

Full design rationale: `20260128-crm-entity-permissions-design.md`

---

## Starting Points for Tomorrow (Phase 3)

### What Phase 3 Covers (Frontend)
From the tech design:
1. Update `Entry.tsx` to accept `crmEntityId` prop
2. Create `CrmEntityRootedView` component
3. Update `EntityMapContainer` routing
4. Update Partner Dashboard to pass `crmEntityId`

### Files to Explore
```
frontend/src/entity-map/Entry.tsx
frontend/src/entity-map/EntityMapContainer.tsx
frontend/src/partner-dashboard/  (find where entity map is mounted)
```

### Key Questions to Answer
1. How does the Partner Dashboard currently get `crmEntityId` for the logged-in user?
2. What's the existing pattern for routing between different view types in EntityMapContainer?
3. Are there existing API hooks we can reuse for fetching the CRM entity graph?

### Suggested Approach
1. **Explore first** - Use the codebase-analyzer agent to understand the frontend structure
2. **TDD the API hook** - Write tests for the new API endpoint integration
3. **Component by component** - Build from Entry.tsx down to the view component

---

## Workflow Pattern We're Using

This session followed a deliberate pattern worth continuing:

### 1. Tech Design as North Star
- Reference `~/Desktop/tech-design.md` for requirements and scope
- Each phase maps to a section of the design
- Deviations are discussed and documented (e.g., single-firm vs multi-firm decision)

### 2. Documentation as We Go
- Design decisions get their own markdown files with rationale
- Session summaries capture context for future sessions
- All docs go to `~/Projects/coauthored/` with date prefixes

### 3. TDD Implementation
- **RED**: Write failing test that describes expected behavior
- **GREEN**: Write minimal code to make test pass
- **Refactor**: Clean up, run linters, verify all tests pass
- Commit after each phase is green

### 4. Manual Testing Checkpoints
- After backend work, test endpoints with curl/httpie
- Document test results and edge cases discovered
- Fix issues before moving to frontend

### 5. Progress Recording
- Commit messages reference the phase: `feat(entity-map): ... (Phase N)`
- Session summaries provide continuity between sessions
- Branch name reflects the ticket: `gpe-215.cartian.crm_entity_graph`

---

## Current State

**Branch:** `gpe-215.cartian.crm_entity_graph`

**Backend status:** Complete (Phases 1-2)
- Endpoint: `GET /firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/`
- Permissions: `IsFirmMember | IsStaff`
- IDOR protection: Validates CRM entity belongs to firm

**Frontend status:** Not started (Phase 3)

**Next session goal:** Complete Phase 3 (Frontend) and prepare PR for review

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `~/Desktop/tech-design.md` | Original tech design with all phases |
| `20260128-crm-entity-permissions-design.md` | Permission model decision |
| `20260128-crm-entity-api-test-results.md` | Manual API testing results |
| `20260128-crm-entity-graph-structure-fix.md` | Bug fixes from Phase 1 |

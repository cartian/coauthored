---
date: 2026-02-13
description: Implementation plan to remove firm-admin-only UI from the GP (CRM entity) entity map view
repository: carta-frontend-platform
tags: [entity-map, gp-embedded, frontend, cleanup]
---

# Strip Firm-Admin UI from GP Entity Map View

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove or gate firm-admin-only UI that breaks in the GP portfolio (CRM entity) view where `firmUuid` and `organizationPk` are empty.

**Architecture:** The CRM entity entry (`PortfolioEntry`) sets `firmUuid=""` and `organizationPk=""` in `FundAdminContext` because it only needs `crmEntityId`. Shared footer components and document tables construct URLs using `organizationPk`, producing malformed links (`/investors/firm//portfolio/...`). The fix: each affected component checks `crmEntityId` from context and renders nothing (or an appropriate fallback) when in the CRM view.

**Tech Stack:** React, TypeScript, Jest, React Testing Library, @carta/ink

---

## Decision: Check `crmEntityId` directly, no helper

The context already carries `crmEntityId?: UuidType`. Checking `!!crmEntityId` in 5 components is more explicit than a `useIsCrmEntityView()` abstraction. If this pattern proliferates, extract a helper later.

## Decision: DocumentsTable shows empty state, tab stays visible

Hiding the "Documents" tab entirely would require modifying every node tile (~8 files). Instead, DocumentsTable returns a "not available" empty state when in CRM view. The tab stays visible but isn't misleading. If we add GP-compatible document fetching later, this is the only file that changes.

---

### Task 1: Hide PartnerNodeFooter in CRM view

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/shared/PartnerNodeFooter.tsx`
- Test: `apps/fund-admin/entity-map/src/core/components/nodes/shared/__tests__/PartnerNodeFooter.test.tsx`

**What:** Return null when `crmEntityId` is present. LP rollforward and KYC dashboard are admin views — GPs shouldn't see them.

**Implementation:**
```tsx
// PartnerNodeFooter.tsx — add crmEntityId to destructuring, early return
const { organizationPk, crmEntityId } = useFundAdminContext();

if (crmEntityId) {
    return null;
}
```

**Test additions:**
- Verify renders null when `crmEntityId` is provided via renderWithContexts
- Existing tests unchanged (they don't set crmEntityId)

---

### Task 2: Hide FundNodeFooter in CRM view

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/shared/FundNodeFooter.tsx`
- Test: `apps/fund-admin/entity-map/src/core/components/nodes/shared/__tests__/FundNodeFooter.test.tsx`

**What:** Return null when `crmEntityId` is present. Capital activity, journals, performance, and LP rollforward links are all admin views.

**Implementation:**
```tsx
// FundNodeFooter.tsx — add crmEntityId to destructuring, early return
const { organizationPk, crmEntityId } = useFundAdminContext();

if (crmEntityId) {
    return null;
}
```

**Test additions:**
- Verify renders null when `crmEntityId` is provided
- Existing tests unchanged

---

### Task 3: Hide AssetNodeFooter in CRM view

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/shared/AssetNodeFooter.tsx`
- Test: `apps/fund-admin/entity-map/src/core/components/nodes/shared/__tests__/AssetNodeFooter.test.tsx`

**What:** Return null when `crmEntityId` is present. SOI link is an admin report.

**Implementation:**
```tsx
// AssetNodeFooter.tsx — add crmEntityId to destructuring, early return
const { organizationPk, crmEntityId } = useFundAdminContext();

if (crmEntityId) {
    return null;
}
```

**Test additions:**
- Verify renders null when `crmEntityId` is provided
- Existing tests unchanged

---

### Task 4: Fix ErrorView for CRM context

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/ErrorView.tsx`
- Test: `apps/fund-admin/entity-map/src/core/components/__tests__/ErrorView.test.tsx`

**What:** The "Go to your entities list" link constructs a malformed URL when `organizationPk` is empty. Hide the navigation button when there's no valid destination.

**Implementation:**
```tsx
// ErrorView.tsx — conditionally render the button
const { organizationPk } = useFundAdminContext();

const href = `/investors/firm/${organizationPk}/portfolio/entities`;

return (
    <Ink.EmptyState
        type="page"
        icon="error"
        text="We can't load this page right now"
        data-testid="error-view"
    >
        {organizationPk && (
            <Ink.Button onClick={handleClick} href={href}>
                Go to your entities list
            </Ink.Button>
        )}
    </Ink.EmptyState>
);
```

**Test additions:**
- Verify button is hidden when organizationPk is empty
- Existing tests unchanged (they provide organizationPk)

---

### Task 5: DocumentsTable empty state for CRM view

**Files:**
- Modify: `apps/fund-admin/entity-map/src/core/components/nodes/shared/DocumentsTable/DocumentsTable.tsx`

**What:** The documents API hook requires `firmUuid` (which is empty in CRM view). Currently this silently shows "No documents found" — misleading. Add an early return with a clearer empty state.

**Implementation:**
```tsx
// DocumentsTable.tsx — check crmEntityId before calling the hook
const { organizationPk, crmEntityId } = useFundAdminContext();

if (crmEntityId) {
    return <Ink.EmptyState type="page" icon="notfound" text="Documents are not available in this view" />;
}

// existing hook call and rendering below...
```

**Note:** The early return must come before `useListFirmDocuments` to avoid the hook executing with empty firmUuid. Wait — hooks can't be called conditionally. Move the early return after the hook call but before rendering, or use the hook's `enabled` param. The hook already has `enabled: !!firmUuid`, so it won't fire. The early return should come after the hook call to satisfy React's rules of hooks:

```tsx
const { organizationPk, crmEntityId } = useFundAdminContext();
const { data, isLoading, isError } = useListFirmDocuments({ fundIds: [fundId], partnerUuids });

if (crmEntityId) {
    return <Ink.EmptyState type="page" icon="notfound" text="Documents are not available in this view" />;
}
```

No new test file — DocumentsTable has no existing tests. The behavior is covered by the hook's `enabled` guard.

---

## Test commands

```bash
rush test --only=@carta/entity-map
```

## Files changed summary

| File | Change |
|------|--------|
| `PartnerNodeFooter.tsx` | Return null when crmEntityId present |
| `PartnerNodeFooter.test.tsx` | Add CRM view test |
| `FundNodeFooter.tsx` | Return null when crmEntityId present |
| `FundNodeFooter.test.tsx` | Add CRM view test |
| `AssetNodeFooter.tsx` | Return null when crmEntityId present |
| `AssetNodeFooter.test.tsx` | Add CRM view test |
| `ErrorView.tsx` | Conditionally render back button |
| `ErrorView.test.tsx` | Add empty organizationPk test |
| `DocumentsTable.tsx` | Early return with CRM empty state |

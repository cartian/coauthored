---
date: 2026-02-18
description: Design for generic nav_components rendering on entity map node cards via FundViewContext
repository: carta-frontend-platform
tags: [entity-map, nav-components, carried-interest, fund-view-context]
---

# Generic nav_components Display on Node Cards

## Problem

The entity map node cards hardcode lookups for specific `nav_components` keys (currently only `'Carried interest accrued'`). This makes adding or removing a metric from a node card require bespoke conditional blocks in every node component. The reviewer on PR #19953 flagged this: carried interest shouldn't be special-cased relative to other metrics.

## Context

`nav_components` is a `Record<string, string>` — the NAV waterfall decomposition. All entries sum to `ending_nav`. The backend controls which keys are present per fund configuration. Different views (CRM Entity, Fund Admin, LPPA) may want to surface different subsets of these components on the node card.

The node card already renders fixed metrics (NAV, Commitment, Called Capital) from dedicated typed fields. `nav_components` entries are supplemental — "also show these waterfall line items alongside the headline numbers."

## Design

### Add `displayNavComponents` to `FundViewContext`

```typescript
export type FundViewContextType = {
    endDate: string;
    effectiveDate: string;
    layoutDirection: LayoutDirection;
    setLayoutDirection: (direction: LayoutDirection) => void;
    currency: Ink.CurrencyProps['code'];
    displayNavComponents: string[];  // new
};
```

Each view provider sets its own list as a stable constant:

```typescript
const CRM_DISPLAY_NAV_COMPONENTS = ['Carried interest accrued'];

// In CrmEntityView:
<FundViewContextProvider
    displayNavComponents={CRM_DISPLAY_NAV_COMPONENTS}
    ...
/>
```

### Node components iterate generically

Replace hardcoded carry lookups with:

```tsx
const { displayNavComponents, currency } = useFundViewContext();

// In expanded view, before the fixed metrics (Commitment, NAV):
{displayNavComponents.map(key => {
    const value = nav_components[key];
    return value !== undefined ? (
        <CollapsedMetricView key={key} label={key} value={value} code={currency} />
    ) : null;
})}
```

For Journal nodes (overtime), pair with the change dictionary:

```tsx
{displayNavComponents.map(key => {
    const value = data.nav_metrics.end.nav_components[key];
    const change = data.nav_metrics.change.nav_components[key];
    return value !== undefined ? (
        <CollapsedMetricView key={key} label={key} value={value} change={change} code={currency} />
    ) : null;
})}
```

### Affected components

| Component | Current behavior | New behavior |
|-----------|-----------------|-------------|
| `AsOfDateGPEntityNode` | Hardcoded carry lookup | Iterates `displayNavComponents` |
| `JournalGPEntityNode` | Hardcoded carry + change lookup | Iterates with end/change pairing |
| `IndividualPortfolioNode` | Hardcoded carry lookup | Iterates `displayNavComponents` |
| `AsOfDateGpEntityNodeTile` | Passes carry as prop | Passes `displayNavComponents` values |
| `PartnersTable` | `isGPEntity` guard for carry column | Check key presence in `displayNavComponents` or data |
| `PartnersOverTimeTable` | `isGPEntity` guard for carry column | Same |
| `FundViewContext` | No display config | Adds `displayNavComponents` field |
| `CrmEntityView` | No metric config | Provides `['Carried interest accrued']` |
| `FundView` | No metric config | Provides `['Carried interest accrued']` |
| `LppaFundView` | No metric config | Provides list (TBD — check if LPPA shows carry) |
| Test utilities | No display config | Provide `displayNavComponents` in context |

### What doesn't change

- NAV, Commitment, Called Capital render from dedicated typed fields as before
- The PartnersTable full waterfall breakdown (all `nav_components` entries) stays as-is
- Collapsed node view still shows only NAV
- The backend sends all `nav_components` entries without stripping (see backend follow-up plan)

### Future: backend-driven display hints

Once the backend ships a `display_nav_components` field in the API response (see `20260218__plan__backend-carry-gate-followup.md`), the hardcoded constants per view can be replaced by reading from the API response. The context plumbing stays the same — only the source of the array changes.

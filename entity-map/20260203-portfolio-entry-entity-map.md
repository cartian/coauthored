---
date: 2026-02-03
description: Architecture decision for creating a separate PortfolioEntry point in entity-map for CRM entity views
repository: carta-frontend-platform
tags: [architecture, entity-map, partner-dashboard, module-federation, gpe]
---

# Separate Portfolio Entry Point for Entity Map

## Context

The entity-map application currently has a single `Entry.tsx` that serves firm-rooted views. It uses `InitAPIProvider` to fetch firm metadata from `/firm/${organizationPk}/entity-atlas/init/` before rendering.

When embedding the entity map in Partner Dashboard to show a CRM entity (investor) view, we attempted to reuse this Entry point by passing `crmEntityId` as a prop. This approach caused problems:

1. **API failures** - The firm init endpoint requires `organizationPk` from URL params, which doesn't exist in the Partner Dashboard context
2. **Unnecessary complexity** - The CRM entity view doesn't need firm metadata; it fetches its own data via `useGetCrmEntityMap`
3. **Conditional logic** - Making one Entry point handle both firm and investor contexts added fragile conditional code

## Decision

Create a dedicated `PortfolioEntry.tsx` for CRM entity (investor portfolio) views, exposed via Module Federation as `./PortfolioApp`.

### Architecture

```
Partner Dashboard                    Entity Map App
┌─────────────────────┐             ┌────────────────────────────┐
│ EntityMapSection    │             │                            │
│                     │ FARSComponent│  PortfolioEntry.tsx        │
│  crmEntityId ───────┼─────────────►│  (new file)                │
│                     │ module=      │         │                  │
│                     │ "PortfolioApp"│        ▼                  │
└─────────────────────┘             │  Providers:                 │
                                    │  - QueryClientProvider      │
                                    │  - ErrorBoundary            │
                                    │  - Monitoring               │
                                    │  - FundAdminContext         │
                                    │         │                   │
                                    │         ▼                   │
                                    │  CrmEntityView              │
                                    │  └─ useGetCrmEntityMap      │
                                    └────────────────────────────┘
```

### PortfolioEntry Design

**Props:**
- `crmEntityId: string` - The CRM entity UUID passed from FARSComponent

**Providers (minimal setup):**
- `QueryClientProvider` - React Query for data fetching
- `ErrorBoundary` - Graceful error handling
- `Monitoring` - Analytics/Sentry integration
- `FundAdminContextProvider` - With minimal values:
  - `firmUuid: ''`
  - `organizationPk: ''`
  - `featureFlags: {}`
  - `crmEntityId: <from props>`

**Renders:**
- `CrmEntityView` directly (no MainView routing)

### Module Federation Configuration

```javascript
// rspack.config.ext.js
rspack.plugins.moduleFederationPlugin({
    './App': './core/Entry',           // Existing firm-rooted entry
    './LppaApp': './core/LppaEntry',   // Existing LP entry
    './PortfolioApp': './core/PortfolioEntry',  // New portfolio entry
}),
```

### Partner Dashboard Update

```tsx
// EntityMapSection.tsx
<FARSComponent
    baseUrl={window.AWS_CLOUDFRONT_FEDERATED_BUNDLES_BASE}
    environment={window.CURRENT_ENV as Environment}
    scope="entityMap"
    module="PortfolioApp"  // Changed from "App"
    props={{ crmEntityId }}
/>
```

## Files to Change

| File | Action |
|------|--------|
| `apps/fund-admin/entity-map/src/core/PortfolioEntry.tsx` | Create |
| `apps/fund-admin/entity-map/rspack.config.ext.js` | Add `./PortfolioApp` export |
| `apps/gpe/partner-dashboard/.../EntityMapSection.tsx` | Change module to `"PortfolioApp"` |

## Benefits

1. **Clean separation** - Firm and portfolio views have dedicated entry points
2. **No unnecessary API calls** - Portfolio view skips firm init entirely
3. **Simpler code** - No conditional logic in Entry to handle different contexts
4. **Independent evolution** - Each entry point can evolve without affecting the other
5. **Faster load** - No init endpoint latency for portfolio views

## Alternatives Considered

**Option: Make firm fields optional in FundAdminContext**

Rejected because it would require updating the context type and auditing all consumers to handle undefined values. Passing empty defaults is simpler and the CRM entity view doesn't use these fields anyway.

**Option: Use a CRM-entity-specific init endpoint**

Rejected for now. The `CrmEntityView` already handles its own data fetching via `useGetCrmEntityMap`. Adding an init layer would add latency without benefit. Can be added later if metadata needs arise.

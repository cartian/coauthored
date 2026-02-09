---
date: 2026-02-04
description: Design for a lightweight DevApp debugger for the Entity Map application, enabling developers to inspect backend responses with minimal rendering overhead
repository: carta-frontend-platform
tags: [entity-map, devapp, debugging, react-flow, fund-admin]
---

# Entity Map DevApp Debugger

## Background

The Entity Map application visualizes complex fund structures, showing relationships between funds, assets, GP entities, and fund partners. When developing or debugging backend APIs that produce these structures, it's often difficult to inspect the raw data because the full Carta & Fund Admin environment has substantial rendering and loading overhead.

Today, the team uses a [StackBlitz sandbox](https://stackblitz.com/edit/fmw8n3wu?file=package.json) to test payloads outside the main application. This works, but it's disconnected from the actual codebase—different dependency versions, no access to real types, and no integration with the development workflow.

We want to bring this debugging capability into the app itself as a DevApp that loads only in local development. This gives us the best of both worlds: ultra-slim rendering for quick inspection, but using the same React Flow, elkjs, and type definitions that the production app uses.

## Goals

1. **Quick payload inspection** - Developers can paste JSON or upload files and immediately see how the data renders as a graph
2. **Mock data for testing** - Pre-built mock datasets of varying sizes to test layout behavior without hitting real APIs
3. **Minimal overhead** - Strip away all non-essential features; just render nodes and edges
4. **Integrated tooling** - Lives in the actual codebase, uses real dependencies and types

## Non-Goals (for now)

- Full-featured mock views at `/firm-view` or `/portfolio-view` (future work)
- Collapsible nodes that show full JSON data on click (may add later)
- Custom edge rendering or styling
- Integration with MSW for mock API endpoints (using direct imports instead)

## Architecture

### Entry Point Strategy

Following the pattern established by other apps in the monorepo (partner-dashboard, carried-interest), we'll create a `DevApp.tsx` that loads conditionally based on `NODE_ENV`.

When running locally (`NODE_ENV === 'development'`), the bootstrap process will render `DevApp` instead of the production entry point. This keeps the debugger completely out of production builds.

### File Structure

```
apps/fund-admin/entity-map/src/
├── DevApp.tsx                    # New - routes to debugger
├── core/
│   ├── bootstrap.tsx             # Modified - conditional DevApp loading
│   └── components/
│       └── Debugger/             # New directory
│           ├── index.ts          # Barrel export
│           ├── DebuggerView.tsx  # Main view with controls
│           ├── DebuggerMap.tsx   # Slim React Flow wrapper
│           ├── DebuggerNode.tsx  # Simple node component
│           └── DataInput.tsx     # JSON paste + file upload
└── __mocks__/
    └── debugger-responses.ts     # Size variation mocks
```

### Routing

The DevApp exposes a single route:

- `localhost:4321/debugger` → DebuggerView

Future routes like `/firm-view` and `/portfolio-view` can be added to DevApp.tsx when needed, but we're keeping scope minimal for now.

## Component Design

### DebuggerView

The main container component. It manages state and orchestrates the data flow between user input and the map renderer.

**Layout:**
```
┌─────────────────────────────────────────────────────────┐
│  Entity Map Debugger                                    │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────────────────┐   │
│  │ Mock Data       │  │ Custom Data                 │   │
│  │ ○ Small (5)     │  │ ┌─────────────────────────┐ │   │
│  │ ○ Medium (15)   │  │ │ Paste JSON here...      │ │   │
│  │ ○ Large (50)    │  │ │                         │ │   │
│  │                 │  │ └─────────────────────────┘ │   │
│  │                 │  │ [Upload JSON] [Apply]       │   │
│  └─────────────────┘  └─────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              ┌───────────┐      ┌───────────┐          │
│              │ Fund A    │──────│ Asset X   │          │
│              │ fund      │      │ asset     │          │
│              └───────────┘      └───────────┘          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**State:**
Intentionally simple—just two pieces of state:
- `mapData: { nodes: Node[], edges: Edge[] } | null`
- `error: string | null`

No React Query, no complex state management. This is a debugging tool; simplicity is a feature.

**Data Flow:**
1. User selects a mock preset, pastes JSON, or uploads a file
2. Input is validated for correct shape
3. Valid data is passed to DebuggerMap for rendering
4. Errors are displayed inline if validation fails

### DataInput

Handles the two input methods for custom data:

**Paste JSON:**
A textarea where developers can paste raw API responses. An "Apply" button validates and loads the data.

**File Upload:**
A file input that accepts `.json` files. On selection, the file is read, validated, and loaded automatically.

**Validation Rules:**
1. Must be valid JSON
2. Must have a `nodes` array
3. Must have an `edges` array
4. Each node must have `id`, `type`, and `name` properties

Clear error messages guide developers when validation fails (e.g., "Missing 'nodes' array in JSON").

### DebuggerMap

A stripped-down React Flow wrapper. It takes nodes and edges, runs them through elkjs for layout, and renders the result.

**Key decisions:**
- Reuses the existing `getElkGraphLayout` utility from `core/components/utils/elk-layout.ts`
- Fixed left-to-right layout direction (`'LR'`) for consistency
- Background dots (React Flow default)
- Fit-to-view on load
- Zoom controls, but no pan/drag complexity

**What it doesn't include:**
- Custom edge components
- Panels for legends, controls, or metadata
- View mode switching
- Zoom threshold behaviors

### DebuggerNode

The visual representation of each node. Ultra-minimal: a box with the node's label and a type badge.

```
┌─────────────────────────┐
│  Krakatoa Fund I        │
│  ┌──────┐               │
│  │ fund │               │
│  └──────┘               │
└─────────────────────────┘
```

**Styling:**
All styling comes from `@carta/ink` components (Box, Text, Badge). No custom CSS, no inline styles.

**Type badge colors:**
| Node Type | Badge Color |
|-----------|-------------|
| fund | blue |
| asset | green |
| gp_entity | purple |
| fund_partners | orange |
| portfolio | teal |

These colors help developers quickly identify node types in complex graphs.

## Mock Data

Mock data lives in `src/__mocks__/debugger-responses.ts` and is imported directly into DebuggerView (no MSW endpoint needed for this use case).

### Size Variations

**Small (5 nodes):**
A simple linear structure for basic testing. One fund with an asset, GP entity, and fund partners.

**Medium (15 nodes):**
A multi-fund hierarchy. Three funds, each with their own assets and entities. Some assets are shared between funds to test edge rendering.

**Large (50 nodes):**
A stress test for layout performance. Ten funds with full hierarchies and cross-fund relationships. Useful for checking that elkjs handles complex graphs gracefully.

### Data Shape

All mocks follow the existing API response shape used by the Entity Map:

```typescript
{
  nodes: [
    { id: string, type: string, name: string, metadata?: {...} },
    ...
  ],
  edges: [
    { source: string, target: string, data?: {...} },
    ...
  ]
}
```

This ensures that real API responses can be pasted directly into the debugger without transformation.

## Implementation Changes

### Modified: bootstrap.tsx

The bootstrap file needs a conditional check to load DevApp in development:

```typescript
if (process.env.NODE_ENV === 'development') {
    // Start MSW if needed, then render DevApp
    render(DevApp);
} else {
    render(ProductionApp);
}
```

This follows the exact pattern used by partner-dashboard and carried-interest.

### New: DevApp.tsx

A simple router that maps `/debugger` to DebuggerView:

```typescript
const DevApp = () => (
    <BrowserRouter>
        <Switch>
            <Route path="/debugger">
                <DebuggerView />
            </Route>
            {/* Future: /firm-view, /portfolio-view */}
        </Switch>
    </BrowserRouter>
);
```

## Dependencies

No new dependencies required. The debugger uses:
- `@xyflow/react` (React Flow) - already installed
- `elkjs` - already installed
- `@carta/ink` - already installed

This keeps the implementation lightweight and avoids dependency sprawl.

## Future Considerations

These are explicitly out of scope for the initial implementation, but worth noting for future work:

1. **Collapsible node data** - Click a node to expand and see the full JSON payload. Useful for deep inspection without leaving the debugger.

2. **Additional routes** - `/firm-view` and `/portfolio-view` could provide more realistic mock environments with full UI chrome.

3. **MSW integration** - If we want to test actual API call flows (loading states, error handling), we could add MSW handlers that serve the mock data via HTTP.

4. **Shareable URLs** - Encode the current data in the URL so developers can share specific test cases with each other.

## Summary

The Entity Map DevApp Debugger is a focused tool for one job: quickly visualizing node/edge data without the overhead of the full application. By keeping scope minimal and reusing existing utilities, we get a useful debugging tool with minimal implementation effort.

The design follows established patterns in the monorepo, uses only existing dependencies, and leaves clear extension points for future needs.

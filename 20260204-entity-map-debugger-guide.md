---
date: 2026-02-04
description: Welcome guide and documentation for the Entity Map Debugger development tool
repository: carta-frontend-platform
tags: [entity-map, debugger, developer-tools, react-flow, fund-admin]
---

# Entity Map Debugger

A development tool for visualizing and debugging Entity Map API responses using React Flow.

## Overview

The Entity Map Debugger is a standalone development environment that allows developers to:

- Visualize entity graph data from backend APIs
- Test different data sizes with mock datasets
- Paste custom JSON payloads for debugging
- Call backend endpoints directly and inspect responses
- Export response data for analysis

This tool is **only available in development mode** and does not ship to production.

## Getting Started

### Prerequisites

1. The Entity Map application running in development mode
2. For API Explorer: the backend service running at `localhost:9000`

### Accessing the Debugger

1. Start the development server:
   ```bash
   cd apps/fund-admin/entity-map
   rushx dev
   ```

2. Navigate to `/debugger` in your browser

The debugger loads automatically when `NODE_ENV=development`. In production builds, the standard StandaloneAppViewer loads instead.

## Interface Overview

The debugger has a two-panel layout:

| Panel | Description |
|-------|-------------|
| **Sidebar** (left) | Data input controls with three tabs |
| **Map View** (right) | React Flow visualization of the entity graph |

## Data Input Methods

### 1. Mock Data Tab

Pre-configured test datasets for quick visualization testing.

| Size | Node Count | Use Case |
|------|------------|----------|
| Small | 5 nodes | Quick layout testing |
| Medium | 15 nodes | Typical fund structure |
| Large | 50 nodes | Performance testing |

**How to use:** Click a size option to instantly load and visualize the mock data.

### 2. Custom Tab

Paste arbitrary JSON data for debugging specific scenarios.

**Expected JSON format:**
```json
{
  "nodes": [
    {
      "id": "node-1",
      "type": "fund",
      "name": "Main Fund"
    }
  ],
  "edges": [
    {
      "from_node_id": "node-1",
      "to_node_id": "node-2"
    }
  ]
}
```

**Required node fields:**
- `id` (string) - Unique identifier
- `type` (string) - Node type (fund, asset, gp_entity, fund_partners, partner, portfolio)
- `name` (string) - Display label

**Required edge fields:**
- `from_node_id` (string) - Source node ID
- `to_node_id` (string) - Target node ID

**How to use:**
1. Paste JSON into the text area
2. Click **Apply** to validate and visualize
3. Or click **Upload JSON** to load from a file

### 3. API Explorer Tab

Call backend Entity Atlas endpoints directly from the debugger.

#### Available Endpoints

| Endpoint | Description | Required Params |
|----------|-------------|-----------------|
| **CRM Entity (Firmless)** | CRM entity graph - derives firm from entity | `crm_entity_uuid` |
| **Firm Entity Map** | Full firm entity map | `firm_uuid` |
| **Fund Entity Map (v2)** | Fund entity map version 2 | `fund_uuid` |
| **Fund Journal Impact** | Journal impact on fund map | `fund_uuid`, `journal_gluuid` |
| **Firm Journals** | Journal entries view for firm | `firm_uuid` |

#### Using the API Explorer

1. **Select an endpoint** from the dropdown
2. **Set the User ID Header** (defaults to `25`)
3. **Fill in required parameters** (UUIDs for the selected endpoint)
4. **Enable toggles** if available (e.g., "Lightweight mode" for CRM Entity)
5. Click **Fetch** to make the API call

#### Response Actions

After a successful fetch:

| Action | Description |
|--------|-------------|
| **Load into Map** | Visualize the response in the map view (only for responses with `nodes` and `edges`) |
| **Copy** | Copy JSON response to clipboard |
| **Download** | Save response as a `.json` file |

The response panel shows:
- Status code (green = 200, red = error)
- Response time in milliseconds
- Full request URL
- Pretty-printed JSON response

## Map Visualization

The map uses React Flow with ELK.js for automatic hierarchical layout.

### Node Types and Colors

| Node Type | Badge Color | Description |
|-----------|-------------|-------------|
| Fund | Yellow | Investment fund |
| Asset | White | Fund asset |
| GP Entity | Green | General partner entity |
| Fund Partners | Blue | Partner group |
| Partner | Blue | Individual partner |
| Portfolio | White | Portfolio company |
| Partner Class | Blue | Partner classification |

### Interaction

- **Pan:** Click and drag the background
- **Zoom:** Scroll wheel or pinch gesture
- **Fit View:** The layout automatically fits on data load

## Architecture

```
src/core/
├── bootstrap.tsx           # Conditional loading (DevApp vs StandaloneAppViewer)
├── DevApp.tsx              # Router with /debugger route
└── components/
    └── Debugger/
        ├── index.ts                # Barrel exports
        ├── DebuggerView.tsx        # Main container with sidebar tabs
        ├── DebuggerMap.tsx         # React Flow wrapper with ELK layout
        ├── DebuggerNode.tsx        # Custom node component
        ├── DataInput.tsx           # Custom JSON input tab
        ├── ApiExplorer.tsx         # API Explorer tab
        └── api-explorer-config.ts  # Endpoint configurations
```

Mock data lives in:
```
src/__mocks__/
└── debugger-responses.ts   # Small, medium, large mock datasets
```

## Adding New Endpoints

To add a new endpoint to the API Explorer, edit `api-explorer-config.ts`:

```typescript
{
    id: 'my-new-endpoint',
    name: 'My New Endpoint',
    description: 'Description shown in the UI',
    pathTemplate: '/path/{param1}/subpath/{param2}',
    params: [
        {
            name: 'param1',
            label: 'Parameter 1',
            placeholder: 'Enter value',
            required: true,
        },
        {
            name: 'param2',
            label: 'Parameter 2',
            placeholder: 'Optional value',
            required: false,
        },
    ],
    toggles: [
        {
            name: 'myToggle',
            label: 'Enable feature',
            queryParam: 'feature_enabled',
        },
    ],
}
```

## Troubleshooting

### "Response does not contain nodes and edges arrays"

The API response doesn't match the expected format. Check that the endpoint returns:
```json
{
  "nodes": [...],
  "edges": [...]
}
```

### API calls failing with network errors

Ensure the backend service is running at `localhost:9000`. The debugger makes direct fetch calls without proxying.

### Nodes overlapping or layout issues

The ELK.js layout algorithm spaces nodes automatically. If you see issues:
1. Check for circular references in edges
2. Ensure all `from_node_id` and `to_node_id` values reference valid node IDs

### Mock data not loading

Verify the mock data file exists at `src/__mocks__/debugger-responses.ts` and exports `MOCK_DATA_BY_SIZE`.

## Related Documentation

- [Entity Map Types Organization](./apps/fund-admin/entity-map/CLAUDE.md)
- [React Flow Documentation](https://reactflow.dev/)
- [ELK.js Layout](https://github.com/kieler/elkjs)

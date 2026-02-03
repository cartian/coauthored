---
date: 2026-02-03
description: A comprehensive debugging journey through Carta's microservice architecture, tracing a 404 error from browser to Kubernetes pod, covering Kong ingress, module federation, and cross-service API routing
repository: fund-admin, carta-frontend-platform, carta-web
tags: [kubernetes, kong, networking, debugging, module-federation, microservices, ingress, fund-admin, carta-web]
---

# Debugging Cross-Service 404 Errors: A Journey Through Carta's Microservice Architecture

## Introduction

This document captures a real debugging session that illuminates the intricate networking architecture connecting Carta's frontend and backend services. While the root cause turned out to be a stale client (anti-climactic!), the debugging journey itself reveals valuable insights into how requests flow through our Kubernetes infrastructure, Kong ingress controllers, and module federation system.

Whether you're new to Carta's architecture or a seasoned engineer trying to understand why your API call isn't reaching the right service, this document will help you build a mental model of the entire request path.

## The Problem

We had just finished building a new backend endpoint in `fund-admin`:

```
GET /entity-atlas/crm-entity/<uuid:crm_entity_uuid>/
```

This endpoint returns an investment relationship graph rooted at a specific CRM entity (investor), rather than the traditional firm-rooted view. The backend was working perfectly when tested directly, but when the frontend tried to call it, we got a **404 Not Found**.

The fetch request looked like this:

```javascript
fetch("https://app.ian-is-cool.test.carta.rocks/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/?end_date=2026-02-03", {
  credentials: "include",
  // ... other headers
});
```

The question was: **Why is a valid endpoint returning 404?**

## Architecture Overview

Before diving into debugging, let's understand the architecture involved:

### Services Involved

1. **fund-admin**: Django backend service handling fund administration, entity maps, capital accounts, etc.
2. **carta-web**: The main Django monolith serving the Carta platform
3. **partner-dashboard**: A React frontend app (federated module) for LP/investor views
4. **entity-map**: A React frontend app (federated module) for visualizing entity relationships

### Module Federation

Carta uses Webpack Module Federation to compose frontend applications:

```
fund-admin (host)
    └── entity-map (federated module)

carta-web (host)
    └── partner-dashboard (federated module)
        └── entity-map (federated module) ← Our scenario
```

When `entity-map` is loaded inside `partner-dashboard` (which is hosted by `carta-web`), API calls from `entity-map` go to the **current browser host** (`app.*.carta.rocks`) rather than the `fund-admin` service host.

### Kubernetes Infrastructure

Each developer has their own namespace in the test Kubernetes cluster:

```
Namespace: ian-wessen
Deployments:
  - ian-is-cool-fund-admin-http      (HTTP API service)
  - ian-is-cool-fund-admin-grpc      (gRPC service)
  - ian-is-cool-carta-web            (Main web service)
  - ian-is-cool-fund-admin-postgres  (Database)
  - ... and many more
```

### Kong Ingress Controller

Kong acts as the API gateway, routing external requests to internal services based on:
- **Host header**: Which domain the request is for
- **Path prefix**: Which path pattern the request matches

## The Debugging Journey

### Step 1: Verify the Backend Works

First, we confirmed the Django URL routing was correct:

```python
# In the Kubernetes pod
from django.urls import resolve

url_path = '/entity-atlas/crm-entity/a2f23ebe-3675-45f7-867e-d3ad5f0effaf/'
match = resolve(url_path)
print(f'View name: {match.view_name}')  # crm-entity-atlas:crm-entity-map
print(f'URL kwargs: {match.kwargs}')    # {'crm_entity_uuid': UUID('...')}
```

**Result**: URL resolves correctly. Django knows about this route.

### Step 2: Verify the Data Exists

We checked that the CRM entity has the necessary relationships:

```python
from fund_admin.capital_account.services.partner import PartnerService

crm_entity_uuid = UUID('a2f23ebe-3675-45f7-867e-d3ad5f0effaf')
ps = PartnerService()
partners = ps.list_domain_objects(crm_entity_ids=[crm_entity_uuid])
print(f'Partners found: {len(partners)}')  # 1
```

**Result**: Data exists. The CRM entity has partner records.

### Step 3: Test the View Logic Directly

We called the view's internal method to see if graph building works:

```python
from fund_admin.entity_map.views.entity_map_crm_entity_view import EntityMapCrmEntityView

view = EntityMapCrmEntityView()
result = view._get_crm_entity_tree(
    firm_uuid=firm_uuid,
    crm_entity_uuid=crm_entity_uuid,
    query_params=query_params,
)
print(f'Nodes: {len(result.nodes)}, Edges: {len(result.edges)}')  # 7 nodes, 6 edges
```

**Result**: The view logic works perfectly. We get valid graph data.

### Step 4: Test from Inside the Pod

Now let's see what happens when we make an HTTP request from inside the pod:

```python
import urllib.request

url = 'http://localhost:80/entity-atlas/crm-entity/a2f23ebe.../
response = urllib.request.urlopen(url)
```

**Result**: `HTTP Error: 401 Unauthorized`

Wait, **401 Unauthorized**, not 404! This is a crucial clue. It means:
- Django IS receiving the request
- The URL IS being routed correctly
- We're just not authenticated (expected for an internal test)

### Step 5: The Revelation - Check the Ingress Rules

If Django returns 401 from inside the pod, but the browser gets 404, the 404 must be happening **before** the request reaches Django.

Let's check the Kong ingress configuration:

```bash
kubectl get ingress ian-is-cool-fund-admin-http-1-ingress -n ian-wessen -o yaml
```

```yaml
spec:
  rules:
  - host: app.ian-is-cool.test.carta.rocks
    http:
      paths:
      - path: /api/fund-admin/
        pathType: ImplementationSpecific
        backend:
          service:
            name: ian-is-cool-fund-admin-http
            port:
              number: 80
```

**The smoking gun!**

The ingress for `app.ian-is-cool.test.carta.rocks` only routes paths starting with `/api/fund-admin/` to the fund-admin service. Our request to `/entity-atlas/crm-entity/...` doesn't match this rule, so Kong returns 404.

### Step 6: Compare with the Fund-Admin Host

Let's check what paths are routed for the fund-admin specific host:

```bash
kubectl get ingress ian-is-cool-fund-admin-http-0-ingress -n ian-wessen -o yaml
```

```yaml
spec:
  rules:
  - host: fund-admin.ian-is-cool.test.carta.rocks
    http:
      paths:
      - path: /
        pathType: ImplementationSpecific
        backend:
          service:
            name: ian-is-cool-fund-admin-http
```

The `fund-admin.*.carta.rocks` host routes **all paths** (`/`) to fund-admin. That's why direct fund-admin API calls work!

## Understanding the Request Flow

Here's the complete picture of how requests flow through the system:

### Scenario A: Entity Map loaded in Fund-Admin App (Works)

```
Browser: https://fund-admin.ian-is-cool.test.carta.rocks/firm/{uuid}/entity-atlas/
    │
    ▼
Kong Ingress (host: fund-admin.*.carta.rocks, path: /)
    │
    ▼ Routes ALL paths to fund-admin-http
    │
Django (fund-admin): Receives /firm/{uuid}/entity-atlas/
    │
    ▼ URL routing matches
    │
View: Returns graph data ✓
```

### Scenario B: Entity Map loaded in Partner-Dashboard (Fails)

```
Browser: https://app.ian-is-cool.test.carta.rocks/entity-atlas/crm-entity/{uuid}/
    │
    ▼
Kong Ingress (host: app.*.carta.rocks, path: /api/fund-admin/*)
    │
    ✗ Path /entity-atlas/* does NOT match /api/fund-admin/*
    │
    ▼
Kong returns 404 (request never reaches Django)
```

## The Solution(s)

### Solution 1: Use the Correct Base URL

The frontend needs to know which host to call for fund-admin APIs. The infrastructure provides `window.FUND_ADMIN_HTTP_HOST`:

```javascript
// In the API hook
const baseUrl = window.FUND_ADMIN_HTTP_HOST || '';
const url = `${baseUrl}/entity-atlas/crm-entity/${crmEntityUuid}/`;

// This becomes:
// https://fund-admin.ian-is-cool.test.carta.rocks/entity-atlas/crm-entity/{uuid}/
```

This global is set in the Django templates:

```html
<!-- carta-web/templates/fe-platform/index.html -->
<script>
    window.FUND_ADMIN_HTTP_HOST = "{{ fep_app_shell_dataset.baseFundAdminApiDomain }}"
</script>
```

### Solution 2: Use the Generated API Client

The `@carta/fa-api-client` package (generated from OpenAPI specs) already has the correct base URL configured:

```typescript
import { snakedFaClient } from '@carta/fa-api-client';

// This automatically uses the correct fund-admin host
const response = await snakedFaClient.firm.entityAtlas.firmEntityAtlas({ firm_uuid }).get();
```

For new endpoints, the OpenAPI schema needs to be regenerated to include them in the client.

### The Actual Root Cause

In our case, `window.FUND_ADMIN_HTTP_HOST` was `undefined` in the browser. After investigation, this turned out to be because **the client was stale** and needed to be rebuilt/redeployed. The infrastructure was correct; we just weren't picking up the latest template changes.

## Key Debugging Techniques

### 1. Isolate the Layer

When debugging 404s, work through each layer:

```
Browser → Kong (Ingress) → Service → Django (URL routing) → View
```

Test each layer independently:
- **Django URL routing**: `resolve(url_path)` in Python shell
- **Django view**: Call view methods directly
- **Internal HTTP**: `curl` or Python `urllib` from inside the pod
- **External HTTP**: Browser or external `curl`

### 2. Check Ingress Rules

```bash
# List all ingresses in your namespace
kubectl get ingress -n <namespace>

# Get details of a specific ingress
kubectl get ingress <name> -n <namespace> -o yaml
```

Look for:
- **host**: Which domain triggers this rule
- **path**: Which URL paths are routed
- **backend.service.name**: Where requests are sent

### 3. Access Pod Internals

```bash
# Find your pod
kubectl get pods -n <namespace> | grep <service>

# Execute commands in the pod
kubectl exec -it <pod-name> -n <namespace> -- <command>

# Open a Django shell
kubectl exec -it <pod-name> -n <namespace> -- poetry run python manage.py shell
```

### 4. Check Pod Connectivity

```python
# From inside a pod, check which ports are open
import socket
for port in [80, 8000, 8080]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', port))
    print(f'Port {port}: {"open" if result == 0 else "closed"}')
```

### 5. Distinguish Error Sources

| HTTP Code | Likely Source | Meaning |
|-----------|---------------|---------|
| 404 | Kong | Path doesn't match any ingress rule |
| 404 | Django | URL doesn't match any URL pattern |
| 401 | Django | Authentication required |
| 403 | Django | Permission denied |
| 500 | Django | Application error |

The key insight: **If you get 401/403 from inside the pod but 404 from outside, the 404 is coming from the ingress layer.**

## Architectural Lessons

### 1. Host-Based Routing is Fundamental

In Carta's architecture, different services have different hosts:
- `app.*.carta.rocks` → carta-web (main app)
- `fund-admin.*.carta.rocks` → fund-admin service
- `identity.*.carta.rocks` → identity service

When making cross-service API calls, you must use the correct host.

### 2. Module Federation Complicates Routing

When a federated module (like `entity-map`) is loaded into a host app (like `partner-dashboard`), API calls default to the current page's host. The module must be configured to use the correct backend host.

### 3. Generated API Clients Handle This

The `@carta/fa-api-client` package encapsulates the correct base URL, so you don't need to think about it. When possible, use the generated client rather than raw `fetch`/`callApi`.

### 4. Window Globals Bridge the Gap

For cases where the generated client doesn't have your endpoint, use window globals:
- `window.FUND_ADMIN_HTTP_HOST` - Fund-admin API base URL
- `window.CARTA_WEB_HOST` - Carta-web base URL
- `window.AWS_CLOUDFRONT_FEDERATED_BUNDLES_BASE` - CDN for federated bundles

These are set by Django templates and provide runtime configuration.

## Quick Reference: Test Environment Structure

### Namespace Naming

```
Developer namespace: <username>
Deployment prefix: <branch-name>-

Example:
  Namespace: ian-wessen
  Deployment: ian-is-cool-fund-admin-http
  Host: fund-admin.ian-is-cool.test.carta.rocks
```

### Common Pod Types

| Pod Suffix | Purpose |
|------------|---------|
| `-http` | HTTP API server |
| `-grpc` | gRPC server |
| `-celery-default` | Celery worker |
| `-celery-beat` | Celery scheduler |
| `-postgres` | PostgreSQL database |
| `-redis` | Redis cache |
| `-migrations` | Database migrations (Job) |

### Finding Your Resources

```bash
# Your namespace
kubectl get namespaces | grep <your-name>

# Your pods
kubectl get pods -n <namespace> | grep <branch-name>

# Your ingresses
kubectl get ingress -n <namespace> | grep <branch-name>

# Pod logs
kubectl logs <pod-name> -n <namespace> --tail=100
```

## Conclusion

What started as a simple "my API returns 404" turned into a deep dive through:
- Django URL routing
- Kong ingress configuration
- Kubernetes pod networking
- Module federation and cross-service communication
- Window globals and runtime configuration

The actual fix was simple (rebuild the client), but the debugging journey revealed the intricate dance between all these systems. Understanding this architecture helps you:

1. **Debug faster**: Know where to look based on the error type
2. **Build correctly**: Use the right patterns for cross-service communication
3. **Understand the system**: See how all the pieces fit together

Remember: When your frontend API call fails, the problem might not be in your code at all. It might be in how the request travels from browser to backend through multiple infrastructure layers.

## Appendix: Useful Commands

```bash
# === Kubernetes Basics ===

# Switch context (if you have multiple clusters)
kubectl config use-context <context-name>

# List all resources in namespace
kubectl get all -n <namespace>

# Describe a resource (shows events, conditions)
kubectl describe pod <pod-name> -n <namespace>

# === Debugging Pods ===

# Shell into a pod
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash

# Django shell in fund-admin
kubectl exec -it <pod-name> -n <namespace> -- poetry run python manage.py shell

# View pod logs
kubectl logs <pod-name> -n <namespace> --tail=100 -f

# === Ingress Debugging ===

# List ingresses with hosts
kubectl get ingress -n <namespace> -o wide

# Get ingress YAML
kubectl get ingress <name> -n <namespace> -o yaml

# === Network Testing ===

# Test connectivity from inside a pod
kubectl exec <pod-name> -n <namespace> -- python -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://localhost:80/health/')
    print(f'Status: {r.status}')
except Exception as e:
    print(f'Error: {e}')
"
```

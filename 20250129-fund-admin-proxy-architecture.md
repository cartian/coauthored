---
date: 2025-01-29
description: Deep dive into how carta-web and fund-admin communicate locally via the proxy architecture pattern
repository: fund-admin
tags: [architecture, local-development, proxy, microservices, authentication]
---

# Understanding the Proxy Architecture: localhost:8000 and localhost:9000

## The Story Behind Two Ports

When you open your browser and navigate to `localhost:8000`, you're visiting **carta-web**—the main Carta application. It's the front door, the receptionist, the bouncer who checks your ID. But when certain pages load financial data, calculations, or fund administration features, those requests quietly slip out the back door to `localhost:9000`—**fund-admin**—a completely separate application with its own codebase, database, and personality.

This document explains why this setup exists, how it works mechanically, and what trade-offs it creates.

---

## Part 1: Why Two Services?

### The Hotel Analogy

Imagine a large hotel. The **main lobby** (carta-web) handles check-in, security, concierge services, and directs guests to where they need to go. But the hotel also has a **specialized spa wing** (fund-admin) with its own staff, equipment, and expertise.

When a guest wants a massage, they don't check in again at the spa—the lobby already verified their identity. The spa just needs to know "this person is a registered guest" and can focus on what it does best: spa services.

Similarly:
- **carta-web** handles authentication, the app shell, navigation, and general Carta functionality
- **fund-admin** handles the specialized domain of fund administration—K-1s, capital calls, waterfall calculations, investor statements

### Historical Context

Fund Admin wasn't always separate. In many companies, new features get bolted onto the main monolith until it becomes unwieldy. Carta made an architectural decision to extract fund administration into its own service. This is a common pattern called **domain-driven decomposition**—carving out a bounded context (fund administration) into its own deployable unit.

The benefits:
- **Teams can move independently**: The fund admin team can ship features without coordinating deploys with every other Carta team
- **Different scaling needs**: Fund admin might need more database connections during tax season; it can scale independently
- **Technology flexibility**: Fund admin could theoretically use different technologies (though both happen to use Django)
- **Failure isolation**: If fund-admin has a bug, it doesn't necessarily crash carta-web

---

## Part 2: How Requests Actually Flow

### The Two API Clients

Open `frontend/src/common/apiClient.ts` and you'll find the key to understanding this architecture:

```typescript
// Client for talking to fund-admin (port 9000)
export const fundAdminClient = axios.create({
    baseURL: window.FUND_ADMIN_HTTP_HOST,  // "http://localhost:9000"
    withCredentials: true,
    // ... transforms snake_case ↔ camelCase
});

// Client for talking to carta-web (port 8000)
export const cartaWebClient = axios.create({
    baseURL: window.CARTA_WEB_HOST,        // "http://localhost:8000"
    withCredentials: true,
    xsrfCookieName: 'eshares-csrftoken-2',
    // ... transforms snake_case ↔ camelCase
});
```

When a React component needs data, the developer chooses which client to use based on where that data lives:

```typescript
// Fetching fund data? Use fundAdminClient
const { data: funds } = await fundAdminClient.get('/api/v1/funds/');

// Fetching user profile from main app? Use cartaWebClient
const { data: user } = await cartaWebClient.get('/api/users/me/');
```

### A Concrete Example: Loading a Fund Dashboard

Let's trace what happens when you navigate to a fund dashboard page:

1. **Browser requests** `http://localhost:8000/investors/firm/1/portfolio/`
2. **carta-web** serves the HTML shell and JavaScript bundles
3. **React app boots**, reads `window.FUND_ADMIN_HTTP_HOST` from the page
4. **Component mounts**, calls `fundAdminClient.get('/api/v1/firm/1/funds/')`
5. **Browser sends request** to `http://localhost:9000/api/v1/firm/1/funds/`
6. **fund-admin** processes request, queries its database, returns JSON
7. **React renders** the fund list

Notice: the user's browser URL still shows `localhost:8000`, but API calls go to `localhost:9000`. This is a **client-side routing** pattern—the frontend orchestrates which backend to talk to.

### The Cookie Dance: How Authentication Works

Here's where it gets interesting. When you log in at `localhost:8000`, carta-web sets authentication cookies in your browser. But how does `localhost:9000` know you're authenticated?

**The `withCredentials: true` flag** is crucial:

```typescript
export const fundAdminClient = axios.create({
    baseURL: window.FUND_ADMIN_HTTP_HOST,
    withCredentials: true,  // <-- This sends cookies cross-origin
});
```

This tells the browser: "When making requests to this different origin (port 9000), include my cookies." Without this flag, the browser would strip cookies from cross-origin requests for security reasons.

On the fund-admin side, there's middleware that validates these cookies:

```python
# From .env
KONG_AUTH_CLASS=fund_admin.http.middleware.MockKongUserIdentityMiddleware
```

In production, this would be real authentication middleware (Kong, OAuth, etc.). Locally, it's mocked to trust the cookies from carta-web.

---

## Part 3: The Docker Network—How Services Find Each Other

### The Problem with "localhost"

Here's a subtle issue: when you run services in Docker containers, `localhost` means something different to each container. Container A's `localhost` is Container A, not Container B.

So how does carta-web (running in one container) talk to fund-admin (running in another)?

### Docker Networks: A Shared Neighborhood

Docker networks create a virtual neighborhood where containers can find each other by name. From `docker-compose.yaml`:

```yaml
networks:
    default:
        name: fund-admin_default
        external: true
```

Both carta-web and fund-admin join this network. Now:
- carta-web can reach fund-admin at `http://fund-admin-http:9000` (using the container name)
- fund-admin can reach carta-web at `http://carta-web:8000`

### The Port Mapping Illusion

When you see `ports: - '9000:9000'` in docker-compose, that's creating a tunnel:

```
Your Mac                          Docker Container
localhost:9000  ──────────────►  container-internal:9000
```

So when your browser (running on your Mac, not in Docker) hits `localhost:9000`, Docker forwards that to the fund-admin container's port 9000.

---

## Part 4: Local vs. Production—Two Different Worlds

### Local Development: Direct Access

Locally, your browser talks directly to both services:

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ├────► localhost:8000 (carta-web)
       │
       └────► localhost:9000 (fund-admin)
```

This is simple and fast for development—no proxy layer to debug.

### Production: Reverse Proxy

In production, users only see one domain (e.g., `carta.com`). A reverse proxy (nginx, Kong, or an application-level proxy in carta-web) routes requests:

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│           carta.com (load balancer)      │
└──────┬──────────────────────────┬───────┘
       │                          │
       ▼                          ▼
┌─────────────┐           ┌─────────────┐
│  carta-web  │           │  fund-admin │
│   cluster   │           │   cluster   │
└─────────────┘           └─────────────┘
```

Certain URL patterns (like `/investors/*` or `/api/fund-admin/*`) get proxied to fund-admin. The browser never knows fund-admin exists as a separate service.

### Why the Difference?

| Concern | Local | Production |
|---------|-------|------------|
| **Simplicity** | Direct access is easier to debug | Single domain is cleaner for users |
| **CORS** | Must configure cross-origin headers | Same-origin, no CORS needed |
| **SSL/TLS** | Usually http, no certs | https everywhere |
| **Service discovery** | Hardcoded ports | Dynamic via Kubernetes/service mesh |

---

## Part 5: The Complexity Tax

Every architectural decision has trade-offs. Here's what this separation costs:

### 1. CORS Configuration Everywhere

Cross-Origin Resource Sharing (CORS) is a browser security feature that blocks requests to different origins. Since `localhost:8000` and `localhost:9000` are different origins, both webpack configs include CORS middleware:

```typescript
// webpack.config.ts
devServer.app.use(cors({ credentials: true, origin: true }));
```

And Django needs CORS headers too. If you've ever seen a `CORS policy` error in your console, this is why.

### 2. The 401 Redirect Problem

Look at this comment in `apiClient.ts`:

```typescript
/*
Simply forces a refresh on 401, this will re-render the page.
A lot of pages in fund-admin proxy through carta-web.
Carta-web has `login_required` wrappers to handle redirects on SOME fund-admin endpoints.

If your view is wrapped in django's login_redirect(), you'll get redirected to login with a valid `next_url`
If your view is not wrapped in login_redirect(), you'll be redirected to a generic unauthorized landing page

TODO: fund-admin needs to start managing it's own redirects.
*/
```

This reveals a pain point: when authentication fails, which service should handle the redirect? carta-web knows about login pages, but fund-admin received the request. The current solution is a somewhat hacky "just refresh the page and hope carta-web catches it."

### 3. Two Mental Models

Developers must constantly ask: "Does this endpoint live in carta-web or fund-admin?" The answer determines:
- Which codebase to modify
- Which client to use in frontend code
- Which service to check for logs
- Which database has the data

### 4. Network Dependency

Both services must be running. If you forget to start fund-admin:

```
GET http://localhost:9000/api/v1/funds/ net::ERR_CONNECTION_REFUSED
```

The app partially works (carta-web pages load) but fund admin features fail silently or with confusing errors.

### 5. Environment Variable Juggling

The `.env` file must configure both services:

```bash
FUND_ADMIN_HTTP_HOST=http://localhost:9000
CARTA_WEB_HOST=http://localhost:8000
```

Get these wrong, and requests go to the wrong place (or nowhere).

---

## Part 6: Practical Implications for Development

### Starting Both Services

The readme emphasizes order matters:

> **IMPORTANT** Start `carta-web` dockerized service **_first_**.

Why? Because the Docker network (`fund-admin_default`) is typically created by carta-web's docker-compose. If you start fund-admin first, it can't find the network.

### Debugging API Issues

When something breaks, check:

1. **Which service should handle this request?** Look at the URL and the axios client used.
2. **Is that service running?** `docker compose ps` to verify.
3. **Are cookies being sent?** Check browser dev tools → Network → Request Headers → Cookie.
4. **Is CORS configured?** Look for `Access-Control-Allow-Origin` in response headers.

### Adding New Endpoints

If you're adding a new API endpoint:

1. **Choose the right service**: Fund administration logic → fund-admin. General Carta features → carta-web.
2. **Use the right client**: `fundAdminClient` vs `cartaWebClient` in frontend code.
3. **Consider authentication**: fund-admin endpoints need auth middleware configured.

---

## Part 7: The Bigger Picture

This architecture is an instance of the **Backend for Frontend (BFF)** pattern combined with **service decomposition**. carta-web acts as a BFF that aggregates multiple backend services (fund-admin being one) behind a unified frontend experience.

### Alternative Approaches

Other ways this could have been architected:

| Approach | Pros | Cons |
|----------|------|------|
| **Monolith** | Simple, one codebase | Scaling issues, team coordination overhead |
| **API Gateway** | Clean separation, single entry point | Additional infrastructure to maintain |
| **GraphQL Federation** | Unified query language across services | Complexity, learning curve |
| **Current approach** | Pragmatic, incremental migration | CORS complexity, split mental model |

Carta chose a pragmatic middle ground that allowed gradual extraction of fund-admin without requiring massive infrastructure changes.

---

## Summary

The `localhost:8000` ↔ `localhost:9000` setup is a **local development convenience** that mirrors a production architecture where fund-admin is a separate service behind carta-web's reverse proxy.

**Key takeaways:**
- **carta-web** (8000) = authentication, app shell, main Carta features
- **fund-admin** (9000) = fund administration domain logic
- **Frontend chooses** which backend to call via different axios clients
- **Cookies flow** between services via `withCredentials: true`
- **Docker networks** let containerized services find each other
- **Production hides** this complexity behind a reverse proxy

Understanding this architecture helps you debug issues, add features to the right service, and appreciate the trade-offs inherent in distributed systems—even when they're all running on your laptop.

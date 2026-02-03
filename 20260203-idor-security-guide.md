---
date: 2026-02-03
description: Guide to understanding and preventing IDOR vulnerabilities in fund-admin
repository: fund-admin
tags: [security, idor, authorization, best-practices]
---

# IDOR Vulnerabilities in Fund-Admin: Understanding and Prevention

## What is IDOR?

**Insecure Direct Object Reference (IDOR)** is a type of access control vulnerability that occurs when an application exposes internal object references (database IDs, UUIDs, filenames) and fails to verify that the requesting user is authorized to access those objects.

### Simple Example

```python
# VULNERABLE: No authorization check
@api_view(['GET'])
def get_partner(request, partner_uuid):
    partner = Partner.objects.get(uuid=partner_uuid)
    return Response(PartnerSerializer(partner).data)

# An attacker who knows (or guesses) another firm's partner_uuid
# can access data they shouldn't see
```

### The Attack Pattern

1. User A is authenticated and can access their own data at `/api/partners/uuid-A/`
2. User A guesses or discovers UUID-B belonging to a different firm
3. User A requests `/api/partners/uuid-B/`
4. Without proper authorization, the server returns User B's data

## Why IDOR is Prevalent in Fund-Admin

### 1. Multi-Tenant Architecture

Fund-admin serves multiple firms, each with their own:
- Funds
- Partners (investors)
- Financial data
- Documents

All this data lives in shared database tables, distinguished only by foreign keys. A single missing authorization check exposes one firm's data to another.

### 2. Complex Relationship Hierarchies

Data ownership flows through multiple levels:

```
Firm
  └── Fund
        └── Partner
              └── Transactions
              └── Documents
              └── Capital Activity
```

Validating access requires traversing these relationships. It's easy to check "does this user belong to a firm?" but harder to verify "does this partner belong to a fund in a firm this user can access?"

### 3. UUID Proliferation

The codebase uses UUIDs extensively in URLs:
- `/firm/{firm_uuid}/fund/{fund_uuid}/partner/{partner_uuid}/`

UUIDs are better than sequential IDs (harder to guess), but they're not authorization. Once an attacker obtains a UUID (through logs, error messages, or enumeration), they can attempt access.

### 4. Multiple Entry Points

The same data can be accessed through:
- REST APIs
- gRPC services
- Celery tasks
- Internal service calls

Each entry point needs its own authorization checks, creating many opportunities for oversight.

### 5. Rapid Feature Development

New endpoints are added frequently. Without systematic security review, IDOR vulnerabilities slip through when developers focus on functionality over authorization.

## How We Prevented IDOR in the Entity Map Feature

### Layer 1: Permission Classes

```python
class EntityMapCrmEntityView(APIView, FirmMixin):
    permission_classes = [HasAllViewPermissions | IsStaff]
```

This ensures only users with appropriate firm-level permissions can access the endpoint. But it doesn't verify the requested CRM entity belongs to their firm.

### Layer 2: Query-Level Filtering

```python
partners = self._partner_service.list_domain_objects(
    crm_entity_ids=[crm_entity_uuid],
    firm_ids=[firm_uuid],  # Filter at query level
)
if not partners:
    raise PermissionDenied("CRM entity does not belong to the specified firm.")
```

The query filters by both `crm_entity_id` AND `firm_id`. If the CRM entity doesn't have partners in that firm, access is denied.

### Layer 3: Defense-in-Depth Verification

```python
# Don't trust the query filter alone - verify explicitly
partner_fund_ids = [p.fund_id for p in partners]
fund_id_to_firm_id = self._fund_service.get_fund_id_to_firm_id_map(partner_fund_ids)

if not any(fid == firm_uuid for fid in fund_id_to_firm_id.values()):
    raise PermissionDenied("CRM entity does not belong to the specified firm.")
```

Even if the query filter has a bug, this explicit check catches the IDOR. This is defense-in-depth: don't trust a single layer.

## Prevention Strategies Going Forward

### 1. Authorization at the View Level

Every view that accepts object references should validate authorization:

```python
# Pattern: Validate before processing
def get(self, request, crm_entity_uuid, firm_uuid):
    # Step 1: Validate the user can access this firm (permission class)
    # Step 2: Validate the object belongs to this firm
    self._validate_object_in_firm(crm_entity_uuid, firm_uuid)
    # Step 3: Process the request
    return self._get_data(crm_entity_uuid)
```

### 2. Use Service Methods with Built-in Filtering

Prefer service methods that enforce tenant isolation:

```python
# GOOD: Service filters by firm
partners = partner_service.list_domain_objects(
    crm_entity_ids=[uuid],
    firm_ids=[firm_uuid]
)

# RISKY: Direct model query without filtering
partner = Partner.objects.get(uuid=uuid)  # No firm check!
```

### 3. Automated Security Review

Use the `/security:idor-review` skill on PRs to catch:
- Endpoints accepting UUIDs without authorization
- Direct model queries without firm filtering
- Missing permission classes

### 4. Defense-in-Depth Pattern

Never rely on a single authorization check:

```python
def secure_endpoint(request, object_uuid, firm_uuid):
    # Layer 1: Permission class (checked by DRF)
    # Layer 2: Query filter
    obj = service.get(uuid=object_uuid, firm_id=firm_uuid)
    if not obj:
        raise PermissionDenied()

    # Layer 3: Explicit verification
    if obj.firm_id != firm_uuid:
        raise PermissionDenied()  # Catches filter bugs

    return obj
```

### 5. Principle of Least Privilege in URLs

Design URLs to include the authorization context:

```python
# BETTER: Firm is explicit in URL, can be validated
/firm/{firm_uuid}/entity/{entity_uuid}/

# WORSE: No context, harder to validate
/entity/{entity_uuid}/
```

When the firm is in the URL, middleware and permission classes can validate firm membership before the view runs.

### 6. Test for IDOR Explicitly

Write tests that attempt cross-tenant access:

```python
def test_cannot_access_other_firms_partner(self):
    """IDOR Prevention: User from Firm A cannot access Firm B's partner."""
    firm_a_user = create_user(firm=firm_a)
    firm_b_partner = create_partner(firm=firm_b)

    response = client.get(
        f"/api/partners/{firm_b_partner.uuid}/",
        user=firm_a_user
    )

    assert response.status_code == 403  # Not 200!
```

## Common IDOR Patterns to Watch For

| Pattern | Risk | Mitigation |
|---------|------|------------|
| UUID in URL without firm context | High | Include firm_uuid in URL path |
| Direct `Model.objects.get(uuid=x)` | High | Use service methods with firm filtering |
| Trusting client-provided firm_uuid | Medium | Derive firm from authenticated user when possible |
| Batch operations with UUID lists | High | Validate ALL UUIDs belong to the firm |
| File/document access by ID | High | Verify document ownership before serving |

## Summary

IDOR is prevalent in fund-admin because of multi-tenancy, complex relationships, and rapid development. We prevent it through:

1. **Permission classes** - Gate access at the endpoint level
2. **Query-level filtering** - Filter by firm in database queries
3. **Defense-in-depth** - Explicitly verify after fetching
4. **Automated review** - Catch issues in PR review
5. **Testing** - Write explicit cross-tenant access tests

The cost of an IDOR vulnerability in a financial application is severe - exposure of sensitive investor data, regulatory violations, and loss of trust. Every endpoint that accepts an object reference should be treated as a potential IDOR vector until proven otherwise.

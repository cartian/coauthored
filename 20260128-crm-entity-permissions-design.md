# CRM Entity View Permissions Design

## The Problem We're Solving

We're building a new view that shows a **CRM Entity's investment portfolio** - all the funds a person or legal entity is invested in. This is different from our existing views which are rooted at a **firm** or a **fund**.

The question: **How do we decide who can see this data?**

This sounds simple, but it bumps into an interesting mismatch between how our permission system works and what this new view needs.

---

## How Permissions Work Today

Our permission system is **fund-centric**. When you ask "can User X do Action Y?", the answer almost always involves a specific fund:

```
"Can Alice view investments?"
→ "In which fund?"
→ "Fund 123"
→ "Yes, Alice has VIEW_INVESTMENTS on Fund 123"
```

The permission classes reflect this. `HasViewInvestmentsPermission` extends `BaseFundPermission`, which extracts a `fund_uuid` from the URL and checks permissions against that fund.

This works great for fund-rooted views:
- `/fund/{fund_uuid}/partners/` → Check permissions on that fund
- `/fund/{fund_uuid}/investments/` → Check permissions on that fund

But our new CRM Entity view doesn't have a single fund. It potentially spans **multiple funds** - all the funds this investor has positions in.

---

## The Options We Considered

### Option A: New "CRM Entity Ownership" Model

The original tech design proposed a new permission concept:

```python
class CrmEntityPermissionHelper:
    def validate_access(self, user, crm_entity_uuid):
        # Check if user "owns" this CRM entity
        if crm_entity_uuid not in self._get_user_linked_crm_entities(user):
            raise PermissionDenied()
```

**Pros:**
- Directly answers "can this user view this CRM entity?"
- Fits the mental model of "my portfolio"

**Cons:**
- Introduces a new permission paradigm orthogonal to our fund-based system
- "User owns CRM entity" is undefined - how do we know which CRM entities belong to which users?
- Doesn't leverage existing infrastructure

### Option B: Check Fund Permissions on Every Returned Fund

```python
def get_crm_entity_tree(self, user_id, crm_entity_uuid):
    graph = self._build_graph(crm_entity_uuid)
    # Filter to only funds user has permission to see
    return self._filter_by_fund_permissions(graph, user_id)
```

**Pros:**
- Uses existing fund-level permissions
- Granular control over what data is visible

**Cons:**
- Complex to implement as the first step
- May be overkill for V1 where we're not showing sensitive financial data yet

### Option C: Firm-Level Gate + Future Extensibility (Selected)

```python
class EntityMapCrmEntityView(APIView, FirmMixin):
    permission_classes = [IsFirmMember | IsStaff]  # Coarse gate

    def get(self, request, crm_entity_uuid, firm_uuid):
        self._validate_crm_entity_in_firm(crm_entity_uuid, firm_uuid)
        return service.get_crm_entity_tree(...)
```

**Pros:**
- Simple, uses existing infrastructure
- Clear separation: view handles "can you enter?", service handles "what can you see?"
- Naturally extensible to fund-level filtering later

**Cons:**
- More permissive in V1 (any firm member can view any CRM entity in that firm)
- Requires future work for granular control

---

## Why We Chose Option C

The key insight is separating **two different questions**:

1. **"Can you knock on this door?"** - View-level permission check
2. **"What can you see inside?"** - Service-level data filtering

For V1, we're not showing sensitive financial metrics on fund nodes. The graph is structural - it shows relationships between funds, not dollar amounts. A firm member seeing the structure of investments within their own firm is reasonable.

When we add financial data to nodes (the near-future use case), we'll need fund-level filtering. But that filtering belongs in the **service layer**, not the view's `permission_classes`. The service already knows which funds are in the graph - it can filter or redact based on the user's fund-level permissions.

This gives us a clean architecture:

```
┌─────────────────────────────────────────────────────────────┐
│  VIEW LAYER                                                  │
│                                                              │
│  "Can you knock on this door?"                              │
│                                                              │
│  • IsFirmMember | IsStaff                                   │
│  • Validate CRM entity belongs to firm (IDOR prevention)    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  SERVICE LAYER                                               │
│                                                              │
│  "What can you see inside?"                                 │
│                                                              │
│  V1: Return full graph (no financial data)                  │
│                                                              │
│  Future: Filter/redact based on fund-level permissions      │
│  • get_crm_entity_tree(firm_id, crm_entity_uuid, user_id)  │
│  • For each fund node, check HasViewFundPerformance, etc.   │
│  • Redact financial fields if user lacks permission         │
└─────────────────────────────────────────────────────────────┘
```

---

## The Door-and-Room Analogy

Think of it like a building:

**View permissions** are like the door lock. They answer: "Are you allowed to enter this room at all?" For our CRM entity view, the answer is: "Are you a member of this firm? Then yes, you can enter."

**Service-level filtering** is like what's visible inside the room. Different people might see different things based on their clearance level. A junior analyst might see fund names and relationships. A senior partner might also see financial metrics.

V1 builds the room with basic furniture (fund relationships). Everyone who enters sees the same thing. Later, we'll add valuable items (financial data) and need to control who can see what - but the door stays the same.

---

## What We're Implementing

### Phase 2 Deliverables

1. **Replace permission classes** with `IsFirmMember | IsStaff`
2. **Add CRM entity validation** - verify the CRM entity's `organization_id` matches the firm in the URL
3. **Write tests** for both the happy path and IDOR prevention

### Future Work (Not in Phase 2)

- Add `user_id` parameter to `EntityMapService.get_crm_entity_tree()`
- Implement fund-level filtering when financial data is added to nodes
- Consider caching permission checks for graphs with many funds

---

## Summary

| Aspect | V1 Approach | Future Extension |
|--------|-------------|------------------|
| **Gate** | IsFirmMember | Same |
| **IDOR Prevention** | Validate CRM entity in firm | Same |
| **Data Filtering** | None (no sensitive data) | Fund-level permission checks |
| **Where filtering happens** | N/A | Service layer |

This approach is simple today and extensible tomorrow. We're not building abstractions we don't need yet, but we're also not painting ourselves into a corner.

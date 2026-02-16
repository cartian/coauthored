---
date: 2026-01-28
description: Comprehensive guide to the Fund Admin permission system architecture
repository: fund-admin
tags: [permissions, security, architecture, reference, rbac]
---

# Fund Admin Permission System: A Comprehensive Guide

## Introduction

This document provides a comprehensive overview of how permissions work in the Fund Admin application. It explains the architecture, patterns, known vulnerabilities, and recommendations for improvement—particularly as they relate to the CRM Entity-rooted views feature described in `tech-design.md`.

The permission system is one of the most critical security components in Fund Admin. It controls who can see what data, who can modify it, and how access is granted across the complex hierarchy of firms, funds, and users.

---

## Part 1: Understanding the Permission Model

### The Core Concept: Role-Based Access Control (RBAC)

At its heart, Fund Admin uses a **Role-Based Access Control** system. Rather than assigning individual permissions directly to users, we group permissions into **Roles**, and then assign those roles to users.

Think of it like job titles in a company:
- A "Fund Administrator" role might include permissions to view investments, edit partners, and manage fund data
- An "Auditor" role might only include read-only access to specific financial data
- A "Firm Administrator" role might include the ability to manage users and configure firm settings

This approach is easier to manage than tracking individual permissions per user, and it ensures consistency—all Fund Administrators have the same capabilities.

### The Three Scopes: Provider, Firm, and Fund

Permissions operate at three different levels, forming a hierarchy:

```
┌─────────────────────────────────────────────────────────────────┐
│  PROVIDER SCOPE (Carta / Service Provider)                      │
│  └── The broadest level, for platform-wide access               │
│                                                                 │
│      ┌─────────────────────────────────────────────────────────┐│
│      │  FIRM SCOPE                                             ││
│      │  └── Access to a specific firm/organization             ││
│      │                                                         ││
│      │      ┌─────────────────────────────────────────────────┐││
│      │      │  FUND SCOPE                                     │││
│      │      │  └── Access to a specific fund within a firm    │││
│      │      └─────────────────────────────────────────────────┘││
│      └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

**Why this matters:** A user might be a "Fund Administrator" for Fund A but only have "View Only" access to Fund B, even though both funds are in the same firm. The system tracks these distinctions at the fund level.

### The Data Model: How Permissions Are Stored

The permission system uses several interconnected database models:

**Permission** - The atomic unit of access. Examples:
- `view_investments` - Can see investment data
- `edit_partners` - Can modify partner/LP information
- `manage_fund_admin_data` - Can manage fund configuration

**Role** - A collection of permissions bundled together. Examples:
- "Fund Administrator" - Has all fund management permissions
- "Preparer" - Can prepare but not approve transactions
- "Auditor" - Read-only access for compliance review

**FirmMember** - Represents a user's membership in a firm. This is the bridge between a user account and their access to a firm's data.

**FundPermission** - Links a FirmMember to a specific Fund with specific Roles. This is where the actual access grant lives.

Here's how they connect:

```
User Account
     │
     ▼
FirmMember (user's presence in a firm)
     │
     ├── firm_permissions (firm-level access)
     │
     └── FundPermission (per-fund access)
              │
              └── roles (collection of permissions for this fund)
```

---

## Part 2: How Permissions Are Enforced

### The Permission Check Flow

When a user makes a request to an API endpoint, here's what happens:

1. **Request arrives** at a Django Rest Framework (DRF) view
2. **DRF checks** the `permission_classes` defined on the view
3. **Each permission class** runs its `has_permission()` method
4. **Permission extracts context** from the URL (firm ID, fund ID, etc.)
5. **Permission queries the database** to check if the user has the required access
6. **Request proceeds or is denied** based on the result

### The Base Permission Classes

The codebase provides a hierarchy of permission classes that handle common patterns:

**BaseGPPermission** - The foundation for all GP (General Partner) permissions. It:
- Automatically passes staff users
- Extracts firm/fund identifiers from URL parameters
- Provides utility methods for looking up firms and funds

**BaseFundPermission** - For permissions scoped to a specific fund:
```python
class HasViewInvestmentsPermission(BaseFundPermission):
    permission_level = StandardFundPermission.VIEW_INVESTMENTS
```
This checks: "Does this user have the `view_investments` permission for this specific fund?"

**BaseFirmPermission** - For permissions scoped to a firm:
```python
class HasFirmAdministratorPermission(BaseFirmPermission):
    permission_level = StandardFirmPermission.ADMIN
```
This checks: "Does this user have administrator access to this firm?"

**BaseAllFundsPermission** - For permissions requiring access to ALL funds in a firm:
```python
class HasAllViewInvestmentsPermission(BaseAllFundsPermission):
    permission_level = StandardFundPermission.VIEW_INVESTMENTS
```
This checks: "Does this user have `view_investments` for every fund in this firm?"

### Using Permissions in Views

There are two main ways to apply permissions to views:

**Method 1: Static permission_classes**
```python
class InvestmentsAPIView(APIView):
    permission_classes = (IsStaff | HasViewInvestmentsPermission,)
```
This means: "Allow if user is staff OR if user has view investments permission."

**Method 2: Dynamic get_permissions()**
```python
class FundDocumentsAPIView(APIView):
    def get_permissions(self):
        match self.request.method:
            case "GET":
                return [(IsStaff | HasViewFundAdminDataPermission)()]
            case "POST":
                return [(IsStaff | HasManageFundAdminDataPermission)()]
```
This allows different permissions for different HTTP methods.

### Permission Composition

Permissions can be combined using logical operators:

- `|` (OR): `IsStaff | HasViewInvestmentsPermission` - Either condition passes
- `&` (AND): `HasViewInvestmentsPermission & HasViewPartnersPermission` - Both must pass
- `~` (NOT): `~IsImpersonator` - Must NOT be impersonating

This is enabled by a monkey patch that extends DRF's permission operators to work with our custom `check_permission()` method.

---

## Part 3: Common Permission Patterns

### Staff Auto-Pass

Almost all GP permissions automatically pass for Carta staff users:

```python
def has_permission(self, request, view):
    if request.user.is_staff:
        return True
    # ... actual permission check
```

This is convenient for internal operations and support, but it does mean staff have broad access.

### The Checkable Interface

One unique aspect of this permission system is the "checkable" interface. Permissions can be checked both within HTTP requests AND outside of them:

```python
# Within an HTTP request (standard DRF)
permission.has_permission(request, view)

# Outside an HTTP request (service layer, gRPC, Celery tasks)
permission.check_permission(user_id=123, fund_uuid=some_uuid)
```

This is important because not all authorization checks happen during web requests. Background tasks, gRPC services, and internal operations also need to verify permissions.

### URL-Based Resource Identification

Permissions extract the firm and fund from URL parameters automatically. The system looks for several possible parameter names:

For **firms**: `firm_id`, `firm_uuid`, `firm_carta_id`
For **funds**: `fund_id`, `fund_uuid`, `fund_carta_id`

Example URL patterns:
```
/firm/<uuid:firm_uuid>/fund/<uuid:fund_uuid>/investments/
/firm/<int:firm_carta_id>/capital-account/
```

The permission classes know how to extract these identifiers and use them for authorization checks.

---

## Part 4: The IsFirmMember Problem (Critical Security Pattern)

### The Vulnerability

One of the most important security patterns in the codebase involves the `IsFirmMember` permission class. This class checks if a user has **any** access to **any** fund in a firm.

**The problem:** `IsFirmMember` alone does NOT verify:
- Which specific funds the user can access
- What permission level they have
- What data they should be able to see

Using `IsFirmMember` without additional filtering creates an **Insecure Direct Object Reference (IDOR)** vulnerability where users could potentially access data from funds they shouldn't see.

### The Dangerous Pattern (Don't Do This)

```python
# ❌ DANGEROUS - Creates security vulnerability
class FirmReportAPIView(APIView):
    permission_classes = (IsStaff | IsFirmMember,)

    def get(self, request, firm_uuid):
        # This returns ALL firm data!
        # User might only have access to 1 of 10 funds
        return ReportService().get_all_firm_data(firm_uuid)
```

### The Safe Pattern (Do This Instead)

```python
# ✅ SAFE - Filters data by accessible funds
class FirmReportAPIView(APIView):
    permission_classes = (IsStaff | IsFirmMember,)
    permission_service = PermissionService()

    def get(self, request, firm_uuid):
        # Step 1: Determine which funds user can access
        if request.user.is_staff:
            fund_ids = None  # Staff can see everything
        else:
            fund_ids = list(
                self.permission_service.get_funds_user_has_gp_permission_for(
                    user=request.user,
                    firm_uuid=firm_uuid,
                    permission_level=StandardFundPermission.VIEW_GL,
                ).values_list("id", flat=True)
            )

        # Step 2: Filter the data by those funds
        return ReportService().get_firm_data(firm_uuid, fund_ids=fund_ids)
```

### The Key Takeaway

**Rule:** Whenever you use `IsFirmMember`, you MUST also filter the returned data by the specific funds the user has access to.

This pattern appears throughout the codebase and is documented extensively in the permissions README. Always follow it when building firm-scoped endpoints.

---

## Part 5: Permission Types Reference

### Fund-Level Permissions (StandardFundPermission)

These permissions are granted per-fund. A user might have different fund permissions for different funds within the same firm.

| Permission | Description |
|------------|-------------|
| `VIEW_INVESTMENTS` | View investment data, holdings, and valuations |
| `INVESTMENT_TRANSACTIONS` | Edit investment-related transactions |
| `VIEW_GL` | View general ledger and accounting data |
| `VIEW_FUND_ADMIN_DATA` | View fund configuration and setup |
| `MANAGE_FUND_ADMIN_DATA` | Modify fund configuration and setup |
| `VIEW_PARTNERS` | View partner/LP information |
| `EDIT_PARTNERS` | Modify partner/LP information |
| `VIEW_FUND_PERFORMANCE` | View fund performance metrics |
| `APPROVE_PAYMENT` | Approve payment transactions |
| `AUDITOR` | Read-only access for audit purposes |

### Non-Standard Fund Permissions (NonStandardFundPermission)

These are newer permissions that haven't been fully standardized yet:

| Permission | Description |
|------------|-------------|
| `EDIT_GENERAL_LEDGER` | Edit GL entries directly |
| `EDIT_BANK_FEED` | Modify bank feed data |
| `PREPARE_CAPITAL_ACTIVITY` | Prepare capital calls/distributions |
| `VIEW_FINANCIALS` | View financial packages |
| `CREATE_FINANCIALS` | Create financial packages |
| `MANAGE_FINANCIALS` | Full financial package management |
| `UNPUBLISH_FINANCIALS` | Remove published financial packages |
| `VIEW_MANAGEMENT_FEES` | View management fee data |

### Firm-Level Permissions (StandardFirmPermission)

These permissions apply to the entire firm, regardless of specific funds:

| Permission | Description |
|------------|-------------|
| `ADMIN` | Full firm administrator access |
| `RFI_CONFIG_VIEWER` | View RFI (Request for Information) configuration |
| `PORTFOLIO_ASSOCIATE` | Portfolio-level associate access |
| `EMAIL_ADMIN` | Email administration (security acceptor) |

---

## Part 6: Relevance to CRM Entity-Rooted Views

### The Challenge

The tech design for CRM Entity-rooted views introduces a new challenge: **cross-firm data access**.

Currently, the permission system is firmly **firm-scoped**. Every permission check assumes:
- The user is accessing data within a single firm
- Firm boundaries are never crossed
- Authorization happens at the firm → fund hierarchy

But CRM Entities (representing real people like GP Members) can have positions **across multiple firms**. A GP Member might:
- Manage Fund A at Firm X
- Have carried interest in Fund B at Firm Y
- Serve as an advisor to Fund C at Firm Z

When we build a graph view rooted on a CRM Entity, we need to answer: "What should this person see?"

### The V1 Approach (Conservative and Safe)

The tech design proposes a conservative V1 approach with two rules:

**Rule 1: Identity Check**
Users can only view CRM Entities they are linked to. You can't look up someone else's portfolio.

**Rule 2: Firm Filter**
Even for your own CRM Entity, you only see funds in firms where you have GP access.

```python
class CrmEntityPermissionHelper:
    def validate_access(self, user, crm_entity_uuid: UUID) -> None:
        """User can only view CRM Entities they own."""
        if not self._user_owns_crm_entity(user, crm_entity_uuid):
            raise PermissionDenied("You don't have access to this entity")

    def get_accessible_firm_ids(self, user) -> list[int]:
        """Only show funds in firms where user has GP access."""
        return self._permission_service.get_gp_accessible_firm_ids(user.id)
```

### Why This Is Conservative

This approach is intentionally restrictive. Consider this scenario:

- Jane has GP access to Firm A (where she's Fund Administrator)
- Jane has Partner records in Firm B (where she's just an LP)

Under the V1 model, Jane's CRM Entity view will **only show Fund A data**, not Fund B, even though she has positions there. That's because she lacks GP access to Firm B.

This is safe but incomplete. Future iterations could introduce an "investor view" permission that allows read-only access to funds where you're invested.

### Implementation Pattern

The view should look something like this:

```python
class EntityMapCrmEntityView(APIView):
    permission_classes = [
        HasViewInvestmentsPermission & HasViewPartnersPermission | IsStaff
    ]

    def get(self, request, crm_entity_uuid):
        # Rule 1: Verify identity
        self._validate_crm_entity_access(request.user, crm_entity_uuid)

        # Rule 2: Get accessible firms
        accessible_firm_ids = self._get_accessible_firm_ids(request.user)

        # Build graph filtered to accessible firms
        return EntityMapService().get_crm_entity_tree(
            crm_entity_id=crm_entity_uuid,
            accessible_firm_ids=accessible_firm_ids,
        )
```

### Open Question: User-to-CRM-Entity Linking

The tech design raises an important question that needs resolution:

> How exactly do we determine which CRM Entities a user "owns"? Is this via `organization_id` matching?

This is the key to implementing `_validate_crm_entity_access()`. You'll need to understand:
- How users are linked to CRM Entities
- Whether this is through `organization_id`, direct linking, or another mechanism
- What the existing `CanEditPortfolio` permission does (mentioned in the tech design)

---

## Part 7: Known Vulnerabilities and Security Concerns

### Vulnerability 1: IsFirmMember Without Filtering

**Risk Level:** HIGH

As discussed earlier, using `IsFirmMember` alone creates IDOR vulnerabilities. Any endpoint that uses `IsFirmMember` must also filter returned data by the user's accessible funds.

**Mitigation:** Always follow the pattern shown in Part 4. Consider creating a helper utility that enforces this pattern automatically.

### Vulnerability 2: Cross-Firm Data Leakage

**Risk Level:** MEDIUM (for CRM Entity feature)

The current system doesn't have patterns for safely aggregating data across firms. The V1 approach of filtering by accessible firms is correct, but care must be taken when:
- Merging subgraphs from different firms
- Aggregating metrics that might reveal information about inaccessible firms
- Building any views that cross firm boundaries

**Mitigation:** Filter early (at the firm level) before building any cross-firm views.

### Vulnerability 3: Staff Auto-Pass

**Risk Level:** LOW (operational concern)

Staff users bypass all GP permission checks. While this is intentional for operational efficiency, it means:
- No audit trail differentiation for staff actions
- No "least privilege" for internal users
- Higher impact if staff credentials are compromised

**Mitigation:** Consider implementing staff audit logging and potentially more granular internal permissions for sensitive operations.

### Vulnerability 4: Implicit Firm Derivation

**Risk Level:** LOW

When a fund is provided but not a firm, the permission classes automatically derive the firm from the fund's ownership. This is usually correct, but could cause issues if:
- URL routing is misconfigured
- A fund is moved between firms (edge case)

**Mitigation:** Be explicit about firm/fund relationships in URL design.

---

## Part 8: Recommendations for Improvement

### Recommendation 1: Create a ScopedDataAccessHelper

Standardize the `IsFirmMember + filtering` pattern with a reusable utility:

```python
class ScopedDataAccessHelper:
    """Enforces the IsFirmMember + filtering pattern."""

    def __init__(self, permission_service: PermissionService = None):
        self._service = permission_service or PermissionService()

    def get_accessible_fund_ids(
        self,
        user,
        firm_uuid: UUID,
        permission_level: str,
    ) -> list[int] | None:
        """
        Returns fund IDs user can access, or None for staff.

        Usage:
            fund_ids = helper.get_accessible_fund_ids(user, firm, VIEW_GL)
            data = service.get_data(fund_ids=fund_ids)
        """
        if user.is_staff:
            return None
        return list(
            self._service.get_funds_user_has_gp_permission_for(
                user=user,
                firm_uuid=firm_uuid,
                permission_level=permission_level,
            ).values_list("id", flat=True)
        )
```

### Recommendation 2: Add CRM Entity Permission Class

For the CRM Entity feature, create a dedicated permission class:

```python
class CanViewOwnCrmEntity(BaseGPPermission):
    """User can view their own linked CRM Entities."""

    def check_permission(self, user_id, *args, **kwargs) -> bool:
        crm_entity_uuid = kwargs.get("crm_entity_uuid")
        if not crm_entity_uuid:
            return False

        user_crm_entities = self._get_user_linked_crm_entities(user_id)
        return crm_entity_uuid in user_crm_entities
```

### Recommendation 3: Future "Investor View" Permission

Consider adding a new permission type for read-only access to funds where a user is invested (even without GP access):

```python
class NonStandardFundPermission(str, Enum):
    # ... existing ...
    VIEW_OWN_INVESTMENT = "view_own_investment"
```

This would enable the "post-filter" permissions model described in the tech design, where:
1. Build the subgraph first (permission-agnostic)
2. Check per-entity permissions
3. Filter out inaccessible entities

### Recommendation 4: Permission Check Logging

Add structured logging for permission checks to improve debugging and auditing:

```python
def check_permission(self, user_id, *args, **kwargs) -> bool:
    result = self._do_permission_check(user_id, **kwargs)
    logger.info(
        "permission_check",
        permission=self.__class__.__name__,
        user_id=user_id,
        result=result,
        **kwargs
    )
    return result
```

---

## Part 9: Quick Reference

### File Locations

| What | Where |
|------|-------|
| Permission models | `fund_admin/permissions/models/` |
| GP permission classes | `fund_admin/permissions/gp_permissions/permission_classes.py` |
| Permission constants | `fund_admin/permissions/constants.py` |
| Permission service | `fund_admin/permissions/services/permission_service.py` |
| Base permission class | `fund_admin/permissions/permissions.py` |
| Full documentation | `fund_admin/permissions/README.md` |

### Common Permission Classes

| Class | Use Case |
|-------|----------|
| `HasViewInvestmentsPermission` | Can view investment data for a fund |
| `HasEditPartnersPermission` | Can modify LP/partner information |
| `HasManageFundAdminDataPermission` | Can manage fund configuration |
| `HasFirmAdministratorPermission` | Is a firm administrator |
| `IsFirmMember` | Has ANY access to firm (use with filtering!) |
| `IsFirmAdmin` | Has firm administrator role |
| `IsFundAuditor` | Has auditor access to fund |

### Permission Check Methods

```python
# In a DRF view (standard DRF pattern)
permission.has_permission(request, view)

# Outside HTTP context (service layer, tasks)
permission.check_permission(user_id=123, fund_uuid=uuid)

# Check if user has specific fund permission
PermissionService().check_has_fund_permission(
    user_id=user.id,
    firm_uuid=firm.id,
    fund_uuids=[fund.uuid],
    permission_level=StandardFundPermission.VIEW_INVESTMENTS,
)

# Get funds user has access to
PermissionService().get_funds_user_has_gp_permission_for(
    user=user,
    firm_uuid=firm.id,
    permission_level=StandardFundPermission.VIEW_GL,
)
```

---

## Conclusion

The Fund Admin permission system is a sophisticated RBAC implementation that handles complex multi-tenant scenarios. The key takeaways are:

1. **Permissions are hierarchical**: Provider → Firm → Fund
2. **Roles bundle permissions**: Assign roles, not individual permissions
3. **Always filter with IsFirmMember**: Never use it alone without data filtering
4. **Cross-firm is new territory**: The CRM Entity feature requires careful permission design
5. **V1 should be conservative**: Filter early, validate identity, expand later

For the CRM Entity-rooted views feature, the conservative V1 approach (identity check + firm filter) is the right starting point. It maintains security while establishing patterns that can be extended in future iterations.

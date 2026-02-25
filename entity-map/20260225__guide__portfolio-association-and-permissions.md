---
date: 2026-02-25
description: How users connect to portfolios and how permissions gate the entity map, across both fund-admin and carta-web
repository: fund-admin
tags: [permissions, architecture, entity-map, carta-web, portfolio]
---

# Portfolio Association and Permissions

This document explains how a logged-in user connects to a portfolio in fund-admin, and how two separate permission layers control access to the entity map.

## The user-to-portfolio chain

Fund-admin has no concept of "user." Authentication lives in carta-web's Identity Service, and fund-admin receives a resolved user identity via gRPC middleware. The chain from a login credential to a fund-admin CRM entity looks like this:

**User** (carta-web identity, e.g. user_id 77743)
→ **OrganizationMembership** (carta-web — user belongs to an Organization)
→ **Corporation** (carta-web — the portfolio entity, pk=2476, uuid=`abc-123`)
↔ **CRMEntity** (fund-admin — `CRMEntity.id` = `Corporation.uuid` after sharing)
← **Partner** records (fund-admin — each Partner has `entity` FK pointing to the CRMEntity)

There is no direct `user_id` field on CRMEntity or Partner. The system infers ownership through the Corporation linkage. When the Partner Dashboard loads, the `/app/init` endpoint translates the Corporation PK into a CRMEntity UUID and hands it to the frontend. The frontend then passes it to the entity map endpoint.

### How the linkage is established

When a Partner is "shared" (sent to the LP), fund-admin creates or matches a CRMEntity whose `id` corresponds to a Corporation's `uuid` in carta-web. The Corporation sits inside an Organization, and users access Corporations through OrganizationMembership records.

This means portfolio ownership is validated by asking carta-web "which Corporations can this user access?" — not by querying fund-admin directly.

## Two permission layers

The entity map lives inside the Partner Dashboard. A request must pass through two independent permission gates before the graph renders.

### Layer 1: Portfolio ownership (carta-web gRPC)

The Partner Dashboard view uses `CanViewPortfolioPermission`, which makes a gRPC call to carta-web's `GetPortfoliosForUser`. This aggregates portfolio access from three sources:

1. **OrganizationMembership** — the user belongs to an Organization that owns the Corporation
2. **OrgManagedCUR** — legacy permission path
3. **PartnerContacts** — additional users granted access to a partner's portfolio

If the user's portfolio list does not include the requested Corporation, the request gets a 403 before fund-admin's own permissions are ever checked.

### Layer 2: Fund-level GP permissions (fund-admin)

Once past the portfolio gate, the entity map view applies its own permission logic:

- **Gate**: `IsFirmMember | IsStaff` — the user must be a FirmMember in the relevant firm, or a staff user.
- **Filter**: `_get_permitted_fund_uuids()` queries `PermissionService.get_funds_user_has_gp_permission_for()` to find funds where the user has `view_investments`. Only these funds appear in the graph.

Staff users bypass filtering entirely (the method returns `None`, which means "show everything").

### How permissions are stored

```
FirmMember (user_id, firm_uuid)
  └─ FundPermission (firm_member → fund, via Fund.member_permissions)
       └─ Role (permission_group_key, e.g. 'gp_principal')
            └─ Permission (key, e.g. 'view_investments')
```

A FirmMember can have FundPermission records on any fund in the firm — GP entities, LP funds, or both. The entity map view doesn't distinguish; it just asks "which funds does this user have `view_investments` on?" and uses that set.

## What this means for GP users

A GP principal like John Daley typically has:
- Partner records in **GP Entity funds** (Fund II GP, Fund III GP, Fund IV GP)
- FundPermission records on those **same GP Entity funds**
- A Corporation/CRMEntity that represents him as a legal person

He does **not** have:
- Partner records in LP funds
- FundPermission records on LP funds (unless explicitly granted)

This distinction is the source of the permission filtering bug documented separately.

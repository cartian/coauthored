---
date: 2026-02-25
description: Reproducible Jupyter notebook for empirically analyzing GP permission sets across target firms to inform Entity Map permission design
repository: fund-admin
tags: [permissions, entity-map, gp-roles, jupyter, investigation]
---

# GP Permission Analysis Notebook

## Motivation

We're building the Entity Map feature and need to define what permission set GPs
should have. Rather than guessing, we want to look at real production data to see
what permissions actual GP users hold today across a representative sample of firms.

### Questions we're trying to answer

1. **What roles and permissions do GP-side users actually have?** Not what the
   schema allows — what's empirically assigned in production.
2. **How common are the key permissions?** Specifically `view_investments`,
   `view_partners`, and `view_fund_performance` — the three permissions the
   `EntityMapCrmEntityView` requires for fund-level filtering.
3. **Do most GPs have `view_investments` on LP funds?** If not, we may be gating
   the Entity Map behind a permission that many target users don't hold.
4. **What permission combinations actually exist?** Are there users with
   `view_partners` but not `view_investments`? Understanding the real distribution
   tells us which combinations to design for vs. which are theoretical.

### Data model context

The permission system is two-tiered:

- **Firm-level permissions** (`FirmMember` → `Permission` via `FirmPermissions`):
  coarse grants like `admin`, `email_admin`, `portfolio_associate`.
- **Fund-level permissions** (`FirmMember` → `FundPermission` → `Role` → `Permission`):
  per-fund role assignments that resolve to granular permissions like
  `view_investments`, `edit_partners`, `view_general_ledger`.

GP vs LP is tracked separately on the `Partner` model via `partner_type`
(`general_partner` / `managing_member` for GPs, `limited_partner` / `member`
for LPs). The permission system doesn't inherently distinguish GP from LP users —
it's role-based at the firm and fund level.

The CRM Entity UUID used in `/entity-atlas/crm-entity/:crm_entity_uuid/` maps
through `Partner.entity_id` to find the fund(s) an entity has commitments on.

### Input

A spreadsheet of target firm names and their Carta IDs (`Firm.carta_id`). These
are representative GP firms from the Entity Map target customer set.

---

## Prerequisites

- Jupyter notebook with readonly access to the fund-admin production database
- Django ORM available (the notebook must bootstrap Django settings)

## Cell 1 — Setup

```python
import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fund_admin.settings")
django.setup()

import pandas as pd
from django.db.models import Count, Q
from fund_admin.fund_admin.models import Firm, Fund
from fund_admin.permissions.models import (
    FirmMember,
    FundPermission,
    FundPermissionPermissionGroupJoin,
    Role,
    RolePermission,
    Permission,
    FirmPermissions,
)
from fund_admin.capital_account.models import Partner, PartnerContact
```

## Cell 2 — Load target firms

Populate `target_firms` with a dict of `{"Firm Name": carta_id}` from your
spreadsheet. The cell validates which firms exist in the database and flags
any that don't match. Also counts active GP partners per firm as a sanity check.

```python
# Replace with your actual firm names and carta_ids from the spreadsheet
target_firms = {
    # "Firm Name": carta_id,
}

target_carta_ids = list(target_firms.values())

firms = Firm.objects.filter(carta_id__in=target_carta_ids)
print(f"Found {firms.count()} firms out of {len(target_carta_ids)} carta_ids")

# Show what matched vs what didn't
found_ids = set(firms.values_list("carta_id", flat=True))
missing = {name: cid for name, cid in target_firms.items() if cid not in found_ids}
if missing:
    print(f"\n⚠ {len(missing)} firms not found:")
    for name, cid in missing.items():
        print(f"  {name} (carta_id={cid})")

firm_df = pd.DataFrame(firms.values("id", "name", "carta_id"))

# Count GP partners per firm
gp_counts = (
    Partner.objects
    .filter(
        fund__firm__in=firms,
        partner_type__in=["general_partner", "managing_member"],
        is_active=True,
    )
    .values("fund__firm__carta_id")
    .annotate(gp_count=Count("id", distinct=True))
)
gp_count_map = {row["fund__firm__carta_id"]: row["gp_count"] for row in gp_counts}
firm_df["gp_count"] = firm_df["carta_id"].map(gp_count_map).fillna(0).astype(int)

firm_df
```

## Cell 3 — Fund-level roles and permissions (denormalized)

Produces one row per user x fund x role x permission. This is the raw data that
all subsequent analysis cells pivot from. Denormalized intentionally — it's easier
to aggregate from flat data than to unnest later.

```python
fund_perms = (
    FundPermission.objects
    .filter(firm_member__firm__in=firms)
    .select_related("firm_member", "firm_member__firm")
    .prefetch_related("roles", "roles__permissions")
    .values(
        "firm_member__firm__name",
        "firm_member__firm__carta_id",
        "firm_member__contact_email",
        "firm_member__user_id",
        "firm_member__title",
        "fund__name",
        "fund_uuid",
        "roles__label",
        "roles__scope",
        "roles__permissions__key",
    )
)

fund_perms_df = pd.DataFrame(list(fund_perms))
fund_perms_df.columns = [
    "firm_name", "firm_carta_id", "email", "user_id", "title",
    "fund_name", "fund_uuid", "role_label", "role_scope", "permission_key",
]
print(f"{len(fund_perms_df)} rows (one per user x fund x role x permission)")
fund_perms_df.head(20)
```

## Cell 4 — Firm-level permissions

Separate from fund-level roles, these are coarse firm-wide grants (e.g. `admin`,
`email_admin`). Useful to see which users are firm admins vs regular members.

```python
firm_level = (
    FirmMember.objects
    .filter(firm__in=firms)
    .values(
        "firm__name",
        "firm__carta_id",
        "contact_email",
        "user_id",
        "title",
        "firm_permissions__key",
    )
)

firm_level_df = pd.DataFrame(list(firm_level))
firm_level_df.columns = [
    "firm_name", "firm_carta_id", "email", "user_id", "title", "firm_permission",
]
firm_level_df = firm_level_df.dropna(subset=["firm_permission"])
print(f"{len(firm_level_df)} firm-level permission assignments")
firm_level_df.head(20)
```

## Cell 5 — Per-user permission summary (all firms)

Aggregates Cell 3 into one row per user x fund, with roles and permissions as
lists. This is the primary shape for eyeballing individual user profiles.

```python
role_summary = (
    fund_perms_df
    .groupby(["firm_name", "email", "user_id", "fund_name"])
    .agg(
        roles=("role_label", lambda x: sorted(set(x.dropna()))),
        permissions=("permission_key", lambda x: sorted(set(x.dropna()))),
    )
    .reset_index()
)

print(f"{len(role_summary)} user x fund combinations")
role_summary.head(20)
```

## Cell 6 — Permission frequency across all users

Answers: "Which permissions are most common across our target population?"
The `pct_of_users` column shows what fraction of unique users hold each permission
on at least one fund.

```python
perm_freq = (
    fund_perms_df
    .dropna(subset=["permission_key"])
    .groupby("permission_key")["user_id"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
)
perm_freq.columns = ["permission", "unique_users"]
perm_freq["pct_of_users"] = (
    perm_freq["unique_users"] / fund_perms_df["user_id"].nunique() * 100
).round(1)

perm_freq
```

## Cell 7 — Role frequency

Similar to Cell 6 but at the role level. Shows which named roles are most
commonly assigned. Useful for understanding whether our target users are
"Fund Admin", "Audit", "View Only", etc.

```python
role_freq = (
    fund_perms_df
    .dropna(subset=["role_label"])
    .groupby("role_label")["user_id"]
    .nunique()
    .sort_values(ascending=False)
    .reset_index()
)
role_freq.columns = ["role", "unique_users"]
role_freq["pct_of_users"] = (
    role_freq["unique_users"] / fund_perms_df["user_id"].nunique() * 100
).round(1)

role_freq
```

## Cell 8 — GP partner entity cross-reference (optional)

Most firm members on GP firms are GP-side users, but this cell confirms that by
cross-referencing `PartnerContact` records on GP partner entities. Useful if you
need to prove that "firm member on a GP firm" is a reasonable proxy for "GP user".

```python
gp_user_ids = set(
    PartnerContact.objects
    .filter(
        partner__fund__firm__in=firms,
        partner__partner_type__in=["general_partner", "managing_member"],
        user_id__isnull=False,
    )
    .values_list("user_id", flat=True)
)

print(f"{len(gp_user_ids)} users are contacts on GP partner entities")

gp_perms_df = fund_perms_df[fund_perms_df["user_id"].isin(gp_user_ids)]
print(f"{len(gp_perms_df)} permission rows for GP-linked users")
```

## Cell 9 — Single-firm deep dive

Cells 3-8 work across all target firms at once. This cell zooms into one firm
at a time, producing the same `role_summary` shape but scoped to a single firm.
Useful for walking through individual firm permission profiles with stakeholders.

Set `lookup_firm_carta_id` to the firm you want to inspect.

```python
# --- CONFIGURE THIS ---
lookup_firm_carta_id = 0  # Replace with a carta_id from your spreadsheet
# ----------------------

firm = Firm.objects.get(carta_id=lookup_firm_carta_id)
print(f"Firm: {firm.name} (carta_id={firm.carta_id})")

# All fund-level permission data for this firm's members
firm_fund_perms = (
    FundPermission.objects
    .filter(firm_member__firm=firm)
    .values(
        "firm_member__contact_email",
        "firm_member__user_id",
        "firm_member__title",
        "fund__name",
        "fund__uuid",
        "roles__label",
        "roles__permissions__key",
    )
)

firm_perms_df = pd.DataFrame(list(firm_fund_perms))
firm_perms_df.columns = [
    "email", "user_id", "title", "fund_name", "fund_uuid",
    "role_label", "permission_key",
]

# Firm-level permissions (admin, etc.) as a lookup
firm_level_lookup = (
    FirmMember.objects
    .filter(firm=firm)
    .values("contact_email", "firm_permissions__key")
)
firm_level_map = (
    pd.DataFrame(list(firm_level_lookup))
    .rename(columns={"contact_email": "email", "firm_permissions__key": "firm_permission"})
    .dropna(subset=["firm_permission"])
    .groupby("email")["firm_permission"]
    .apply(lambda x: sorted(set(x)))
    .to_dict()
)

# Pivot into role_summary shape
firm_role_summary = (
    firm_perms_df
    .groupby(["email", "user_id", "title", "fund_name", "fund_uuid"])
    .agg(
        roles=("role_label", lambda x: sorted(set(x.dropna()))),
        fund_permissions=("permission_key", lambda x: sorted(set(x.dropna()))),
    )
    .reset_index()
)
firm_role_summary["firm_permissions"] = firm_role_summary["email"].map(firm_level_map)
firm_role_summary["firm_permissions"] = firm_role_summary["firm_permissions"].apply(
    lambda x: x if isinstance(x, list) else []
)

print(f"{firm_role_summary['email'].nunique()} members across {firm_role_summary['fund_name'].nunique()} funds")
print(f"{len(firm_role_summary)} user x fund combinations")
firm_role_summary
```

## Cell 10 — CRM Entity UUID lookup

Given a CRM Entity UUID (the path parameter from
`/entity-atlas/crm-entity/:crm_entity_uuid/`), resolves through
`Partner.entity_id` to find which fund(s) the entity has commitments on, then
shows every firm member with access to those funds and their full permission set.

The `is_entity_fund` column distinguishes the entity's fund(s) from other funds
the same users happen to have access to.

```python
# --- CONFIGURE THIS ---
lookup_crm_entity_uuid = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
# ----------------------

from fund_admin.lp_crm.models import CRMEntity

# Resolve CRM Entity -> Partner(s) -> Fund(s)
crm_entity = CRMEntity.objects.get(id=lookup_crm_entity_uuid)
print(f"CRM Entity: {crm_entity}")

partners = Partner.objects.filter(entity_id=lookup_crm_entity_uuid).select_related("fund__firm")
if not partners.exists():
    print("No partners found for this CRM Entity.")
else:
    fund_uuids = list(partners.values_list("fund__uuid", flat=True).distinct())
    fund_names = dict(partners.values_list("fund__uuid", "fund__name").distinct())
    firm_names = dict(partners.values_list("fund__firm__name", "fund__name").distinct())
    print(f"Entity has partners on {len(fund_uuids)} fund(s):")
    for fuuid in fund_uuids:
        print(f"  {fund_names[fuuid]} (uuid={fuuid})")

    # Find all firm members with access to any of these funds
    members_on_funds = (
        FirmMember.objects
        .filter(fund_permissions__fund_uuid__in=fund_uuids)
        .select_related("firm")
        .distinct()
    )
    member_ids = list(members_on_funds.values_list("id", flat=True))
    print(f"\n{len(member_ids)} users have access to these fund(s)")

    # Get ALL fund-level permissions for these users across all their funds
    all_fund_perms = (
        FundPermission.objects
        .filter(firm_member_id__in=member_ids)
        .values(
            "firm_member__contact_email",
            "firm_member__user_id",
            "firm_member__title",
            "fund__name",
            "fund__uuid",
            "roles__label",
            "roles__permissions__key",
        )
    )

    portfolio_df = pd.DataFrame(list(all_fund_perms))
    portfolio_df.columns = [
        "email", "user_id", "title", "fund_name", "fund_uuid",
        "role_label", "permission_key",
    ]

    # Mark which rows are the CRM entity's fund(s) vs other funds
    portfolio_df["is_entity_fund"] = portfolio_df["fund_uuid"].isin(fund_uuids)

    # Firm-level permissions lookup
    firm_level_lookup = (
        FirmMember.objects
        .filter(id__in=member_ids)
        .values("contact_email", "firm_permissions__key")
    )
    firm_level_map = (
        pd.DataFrame(list(firm_level_lookup))
        .rename(columns={"contact_email": "email", "firm_permissions__key": "firm_permission"})
        .dropna(subset=["firm_permission"])
        .groupby("email")["firm_permission"]
        .apply(lambda x: sorted(set(x)))
        .to_dict()
    )

    # Pivot into summary shape
    portfolio_summary = (
        portfolio_df
        .groupby(["email", "user_id", "title", "fund_name", "fund_uuid", "is_entity_fund"])
        .agg(
            roles=("role_label", lambda x: sorted(set(x.dropna()))),
            fund_permissions=("permission_key", lambda x: sorted(set(x.dropna()))),
        )
        .reset_index()
        .sort_values(["email", "is_entity_fund"], ascending=[True, False])
    )
    portfolio_summary["firm_permissions"] = portfolio_summary["email"].map(firm_level_map)
    portfolio_summary["firm_permissions"] = portfolio_summary["firm_permissions"].apply(
        lambda x: x if isinstance(x, list) else []
    )

    # Make fund_permissions readable
    portfolio_summary["fund_permissions"] = portfolio_summary["fund_permissions"].apply(
        lambda x: "\n".join(x) if x else ""
    )

    total_funds = portfolio_summary["fund_name"].nunique()
    print(f"{portfolio_summary['email'].nunique()} users across {total_funds} funds")
    print(f"Rows marked is_entity_fund=True are funds where this CRM entity has a partner")
    portfolio_summary
```

## Cell 11 — Permission coverage: GP entity funds vs LP funds

The key question for Entity Map permissions: do firm members have
`view_investments` and `view_fund_performance` on the funds they'd actually
navigate to? The answer may differ depending on whether the fund has GP partners
(entity-level context) vs LP partners (investor-level context).

This cell splits the firm's funds into two buckets — funds with GP partners and
funds with LP partners — then compares what percentage of firm members have each
permission on each bucket. A fund can appear in both buckets if it has both
partner types.

The output is a comparison table with one row per permission per bucket, showing
`users_with` / `users_total` and the percentage. If LP funds show significantly
lower coverage than GP funds, that's a signal we may need to adjust which
permissions gate the Entity Map.

Depends on Cell 9 (`firm`, `firm_role_summary`).

```python
target_perms = ["view_investments", "view_fund_performance"]

# Classify funds by partner type
gp_fund_uuids = set(
    Partner.objects
    .filter(
        fund__firm=firm,
        partner_type__in=["general_partner", "managing_member"],
        is_active=True,
    )
    .values_list("fund__uuid", flat=True)
    .distinct()
)

lp_fund_uuids = set(
    Partner.objects
    .filter(
        fund__firm=firm,
        partner_type__in=["limited_partner", "member"],
        is_active=True,
    )
    .values_list("fund__uuid", flat=True)
    .distinct()
)

print(f"Firm: {firm.name}")
print(f"  {len(gp_fund_uuids)} funds with GP partners")
print(f"  {len(lp_fund_uuids)} funds with LP partners")
print(f"  {len(gp_fund_uuids & lp_fund_uuids)} funds with both")

# Tag each user-fund row
check_df = firm_role_summary.copy()
check_df["is_gp_fund"] = check_df["fund_uuid"].isin(gp_fund_uuids)
check_df["is_lp_fund"] = check_df["fund_uuid"].isin(lp_fund_uuids)

for perm in target_perms:
    check_df[perm] = check_df["fund_permissions"].apply(lambda x: perm in x)

# Build comparison table
def summarize_bucket(df, label):
    rows = []
    for perm in target_perms:
        total = df["email"].nunique()
        with_perm = df[df[perm]]["email"].nunique()
        rows.append({
            "fund_type": label,
            "permission": perm,
            "users_with": with_perm,
            "users_total": total,
            "pct": round(with_perm / total * 100, 1) if total > 0 else 0,
        })
    return rows

results = []
results += summarize_bucket(check_df[check_df["is_gp_fund"]], "GP entity funds")
results += summarize_bucket(check_df[check_df["is_lp_fund"]], "LP funds")

comparison_df = pd.DataFrame(results)
print(f"\nPermission coverage comparison:")
comparison_df
```

## Cell 12 — Per-fund breakdown: GP entity funds vs LP funds

Drills into the per-fund detail behind Cell 11. Each row is a single fund with
its type (GP, LP, or GP + LP), total member count, and the count/percentage of
members holding each target permission.

Use this to spot specific funds where coverage drops — e.g., a fund where only
30% of members have `view_investments` might indicate a non-standard role
configuration worth investigating.

Depends on Cell 11 (`check_df`, `target_perms`).

```python
fund_detail_rows = []
for _, fund_row in check_df.groupby(["fund_name", "fund_uuid", "is_gp_fund", "is_lp_fund"]):
    fund_name = fund_row["fund_name"].iloc[0]
    is_gp = fund_row["is_gp_fund"].iloc[0]
    is_lp = fund_row["is_lp_fund"].iloc[0]

    fund_type = []
    if is_gp:
        fund_type.append("GP")
    if is_lp:
        fund_type.append("LP")
    fund_type_str = " + ".join(fund_type) if fund_type else "Neither"

    total = fund_row["email"].nunique()
    row_data = {
        "fund_name": fund_name,
        "fund_type": fund_type_str,
        "total_members": total,
    }
    for perm in target_perms:
        with_perm = fund_row[fund_row[perm]]["email"].nunique()
        row_data[f"{perm}_count"] = with_perm
        row_data[f"{perm}_pct"] = round(with_perm / total * 100, 1) if total > 0 else 0

    fund_detail_rows.append(row_data)

fund_detail_df = pd.DataFrame(fund_detail_rows).sort_values(
    ["fund_type", "view_investments_pct"], ascending=[True, False]
)

print(f"{len(fund_detail_df)} funds")
fund_detail_df
```

## Cell 13 — Users missing permissions on LP funds

Lists firm members who have access to LP funds but are missing `view_investments`
or `view_fund_performance`. These are the users who would be blocked from seeing
Entity Map data if we gate on these permissions.

If this list is long relative to the total member count on LP funds, it suggests
the current permission assignment patterns don't align with our Entity Map
permission requirements — and we may need to either adjust our gates or work with
firms to update their role configurations.

Depends on Cell 11 (`check_df`).

```python
lp_rows = check_df[check_df["is_lp_fund"]].copy()
missing = lp_rows[~(lp_rows["view_investments"] & lp_rows["view_fund_performance"])]

if missing.empty:
    print("All members on LP funds have both view_investments and view_fund_performance.")
else:
    missing_display = missing[
        ["email", "user_id", "title", "fund_name", "roles", "view_investments", "view_fund_performance"]
    ].sort_values(["email", "fund_name"])

    print(f"{missing_display['email'].nunique()} users missing at least one permission on LP funds")
    print(f"{len(missing_display)} user-fund rows affected\n")
    missing_display
```

---

## Tips for running in hosted Jupyter

- **Truncated DataFrame columns**: Use `print(row["column_name"])` to see full
  cell contents, or iterate rows with `for _, row in df.iterrows()`.
- **Truncated lists in cells**: The `fund_permissions` column in Cells 9/11/12
  stores Python lists. Use `.apply(lambda x: "\n".join(x))` on a display copy
  to render them as readable strings.
- **Pagination**: Slice with `df.iloc[start:end]` or set
  `pd.set_option("display.max_rows", None)` (may not work in all hosted
  environments).
- **Export**: `df.to_csv("/tmp/output.csv", index=False)` to download results.

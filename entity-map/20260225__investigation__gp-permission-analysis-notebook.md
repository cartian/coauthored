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

## Cell 11 — Core permission check

The `EntityMapCrmEntityView` requires three permissions for fund-level filtering:
`view_investments`, `view_partners`, and `view_fund_performance`. This cell checks
which users on the firm (from Cell 9's `firm_role_summary`) hold each of those
permissions, with a boolean column per permission and a summary `has_all_3` flag.

This directly answers: "If we gate Entity Map behind these three permissions,
how many of our target users would be blocked?"

Depends on Cell 9.

```python
core_perms = {"view_partners", "view_fund_performance", "view_investments"}

check_df = firm_role_summary.copy()

for perm in sorted(core_perms):
    check_df[perm] = check_df["fund_permissions"].apply(lambda x: perm in x)

check_df["has_all_3"] = check_df[sorted(core_perms)].all(axis=1)

display_cols = [
    "email", "user_id", "title", "fund_name", "roles",
] + sorted(core_perms) + ["has_all_3"]

core_perms_df = check_df[display_cols].sort_values(
    ["has_all_3", "email"], ascending=[False, True]
)

has_all = core_perms_df["has_all_3"].sum()
total = len(core_perms_df)
print(f"{has_all}/{total} user-fund rows have all 3 core permissions")
print(f"{core_perms_df[core_perms_df['has_all_3']]['email'].nunique()} unique users with full access")
core_perms_df
```

## Cell 12 — Permission combination sampling

Enumerates every possible subset of the three core permissions (8 combinations:
none, three singles, three pairs, all three) and finds one example user for each
combination that exists in the data. Skips combinations with no matching users.

The `total_users_with_combo` column shows how common each combination is. This
tells us whether a combination is a real pattern or a one-off anomaly.

Depends on Cell 11 (`check_df`).

```python
from itertools import combinations

core_perm_list = sorted(core_perms)

# Build a column that represents each user's exact subset of the 3 core perms
check_df["perm_combo"] = check_df["fund_permissions"].apply(
    lambda x: frozenset(p for p in core_perm_list if p in x)
)

# All possible subsets: empty set, each single, each pair, all three
all_subsets = [frozenset()]
for r in range(1, len(core_perm_list) + 1):
    for combo in combinations(core_perm_list, r):
        all_subsets.append(frozenset(combo))

examples = []
for subset in all_subsets:
    matches = check_df[check_df["perm_combo"] == subset]
    if matches.empty:
        continue
    row = matches.iloc[0]
    examples.append({
        "combination": ", ".join(sorted(subset)) if subset else "(none of the 3)",
        "count": len(subset),
        "email": row["email"],
        "user_id": row["user_id"],
        "fund_name": row["fund_name"],
        "roles": row["roles"],
        "total_users_with_combo": matches["email"].nunique(),
    })

examples_df = pd.DataFrame(examples)
print(f"{len(examples_df)} of {len(all_subsets)} possible combinations exist in the data")
examples_df
```

## Cell 13 — `view_investments` coverage on LP funds

Identifies funds that have active LP partners (i.e. actual investor funds, not
GP-only vehicles), then checks what percentage of firm members have
`view_investments` on those funds.

This answers the specific question: "If a GP user navigates to the Entity Map
for an LP's investment, will they have `view_investments` on the fund that
investment is in?"

Depends on Cell 9 (`firm`, `firm_role_summary`).

```python
# Find funds with LP partners, scoped to the firm from Cell 9
lp_funds = (
    Partner.objects
    .filter(
        fund__firm=firm,
        partner_type__in=["limited_partner", "member"],
        is_active=True,
    )
    .values_list("fund__uuid", flat=True)
    .distinct()
)
lp_fund_uuids = set(lp_funds)
print(f"{len(lp_fund_uuids)} funds with active LP partners across target firms")

# Filter firm_role_summary to only LP funds
lp_df = firm_role_summary[firm_role_summary["fund_uuid"].isin(lp_fund_uuids)].copy()
lp_df["has_view_investments"] = lp_df["fund_permissions"].apply(
    lambda x: "view_investments" in x
)

# Per-fund breakdown
firm_summary = (
    lp_df
    .groupby("fund_name")
    .agg(
        total_members=("email", "nunique"),
        members_with_view_investments=("has_view_investments", "sum"),
    )
    .reset_index()
)
firm_summary["pct"] = (
    firm_summary["members_with_view_investments"] / firm_summary["total_members"] * 100
).round(1)
firm_summary = firm_summary.sort_values("pct", ascending=False)

# Overall
total_user_fund = len(lp_df)
total_with = lp_df["has_view_investments"].sum()
total_without = total_user_fund - total_with
unique_with = lp_df[lp_df["has_view_investments"]]["email"].nunique()
unique_total = lp_df["email"].nunique()

print(f"\nOverall: {unique_with}/{unique_total} unique users ({unique_with/unique_total*100:.1f}%) "
      f"have view_investments on at least one LP fund")
print(f"{total_with}/{total_user_fund} user-fund rows ({total_with/total_user_fund*100:.1f}%) "
      f"have view_investments")
print(f"\nPer-fund breakdown:")
firm_summary
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

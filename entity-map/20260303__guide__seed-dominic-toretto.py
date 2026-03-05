"""
Seed script: Create 'Dominic Toretto' as a CRM Entity in Krakatoa
with partner records across multiple funds and GP entities,
capital account transactions, GL entries, carry assignments,
and partner contacts.

Run with: poetry run python manage.py shell_plus < scripts/seed_dominic_toretto.py

ALL DATA IS FICTIONAL. No real customer data is persisted.
Structure mirrors a representative sandbox customer for entity map testing.

==========================================================================
CROSS-SYSTEM SETUP (carta-web)
==========================================================================
After running this script in fund-admin, you must also create records in
carta-web to enable the LP portfolio view. Run these in carta-web's
Django shell (docker exec -it python python manage.py shell_plus):

CRITICAL INVARIANT: The carta-web Corporation UUID MUST match the
fund-admin CRM Entity UUID. The partner portfolio init endpoint
(GET /partner-portfolios/<corp_pk>/app/init) calls gRPC to carta-web to
fetch the Corporation UUID and uses it as the CRM Entity lookup key.
If these don't match, the portfolio 404s.

Step 1: Create User
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        email="dom@krakatoa.vc",
        username="dom@krakatoa.vc",
        password="password",
    )
    # Note user.id for later steps

Step 2: Create Organization (MUST be type='individual' for individual portfolio)
    from eshares.organizations.models import Organization
    org = Organization.objects.create(
        name="Dominic Toretto",
        organization_type="individual",  # NOT 'investment_firm' (the default)
    )
    # If organization_type='investment_firm', portfolio routes to
    # /investors/firm/<org_id>/portfolio/ instead of
    # /investors/individual/<corp_id>/portfolio/

Step 3: Create Corporation with UUID matching fund-admin CRM Entity UUID
    from eshares.corporations.models import Corporation
    import uuid as _uuid
    crm_entity_uuid = "<CRM Entity UUID from script output>"
    corp = Corporation.objects.create(
        legal_name="Dominic Toretto",
        type="Personal",
        can_hold=True,
        uuid=_uuid.UUID(crm_entity_uuid),  # MUST match fund-admin CRM Entity ID
    )
    # Wire up org relationship
    from eshares.organizations.models import EntityOrgPermission
    eop = EntityOrgPermission.objects.create(
        entity=corp,
        organization=org,
    )
    corp.parent_org = eop
    corp.save()

Step 4: Create OrganizationMembership for both dom and admin users
    from eshares.organizations.models import OrganizationMembership
    OrganizationMembership.objects.create(
        member=user, organization=org, is_admin=True,
    )
    admin_user = User.objects.get(id=25)  # admin@esharesinc.com
    OrganizationMembership.objects.create(
        member=admin_user, organization=org, is_admin=True,
    )

Step 5: Create CapitalAccounts linking carta-web to fund-admin partners
    Use the partner IDs printed by this script's output.
    FundLink maps carta-web fund corps to fund-admin fund IDs:

    | carta-web Corp | fund-admin carta_id | Description              |
    |----------------|---------------------|--------------------------|
    | 59             | 59                  | Krakatoa Ventures Fund I |
    | 58             | 58                  | Krakatoa Ventures Fund II|
    | 497            | 497                 | Krakatoa Ventures Fund III|
    | 124            | 124                 | Growth Fund I            |
    | 90             | 90                  | Fund I GP                |
    | 127            | 127                 | Fund II GP               |
    | 501            | 501                 | Fund III GP              |
    | 502            | 502                 | Fund IV GP               |

    from eshares.investor_services.models import CapitalAccount
    from eshares.corporations.models import Corporation
    import uuid as _uuid

    fund_corp = Corporation.objects.get(id=<carta_web_fund_corp_id>)
    accepter_corp = Corporation.objects.get(legal_name="Dominic Toretto", type="Personal")
    ca = CapitalAccount.objects.create(
        fund=fund_corp,
        name="Dominic Toretto",
        accepter=accepter_corp,
        fundadmin_partner_id=<partner.id from script output>,
        fundadmin_partner_uuid=_uuid.UUID("<partner.uuid from script output>"),
        sent_date=timezone.now(),
        accepted_date=timezone.now(),
    )
    # Repeat for all 8 partners (4 LP + 4 GP)

Step 6: Verify
    - Entity map: http://localhost:9000/entity-atlas/crm-entity/<entity_uuid>/
    - Portfolio (fund-admin): http://localhost:9000/partner-portfolios/<entity_uuid>/entity-list
    - Portfolio (carta-web): http://localhost:8000/investors/individual/<corp.id>/portfolio/
    - Partner dashboard init: http://localhost:9000/partner-portfolios/<corp.id>/app/init
==========================================================================
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from fund_admin.fund_admin.models import Firm, Fund
from fund_admin.lp_crm.models import CRMEntity, CRMOrganization, IndividualEntityInfo, LPCRMFullLegalName
from fund_admin.partners.models import PartnerInterestGroup
from fund_admin.capital_account.models.partner import Partner
from fund_admin.capital_account.models.cat import CapitalAccountTransaction
from fund_admin.capital_account.models.commitment import CommitmentTransaction
from fund_admin.capital_account.carried_interest.models import (
    CarriedInterestAssignment,
    PartnerCarriedInterestAssignment,
)
from fund_admin.capital_account.models.partner_contact import PartnerContact, PartnerContactPermission
from fund_admin.general_ledger.accounting.fund.models import (
    FundJournal,
    FundJournalLine,
)
from fund_admin.general_ledger.accounting.fund.models import EnabledAccount


def cents(dollars):
    """Convert dollar amount to cents."""
    return int(dollars * 100)


def find_account(fund, account_type):
    """Find an enabled FundAccount for a fund by account_type integer."""
    ea = EnabledAccount.objects.filter(
        fund=fund,
        account__account_type=account_type,
        account__deleted_date__isnull=True,
        deleted_date__isnull=True,
    ).first()
    if ea:
        return ea.account
    return None


def create_journal(fund, effective_date, event_type, description, lines_data):
    """
    Create a FundJournal with balanced lines.
    lines_data: list of (account, amount, partner_or_none) tuples.
    amount > 0 = debit for DEBIT accounts / credit for CREDIT accounts (follows normal balance).
    """
    journal_id = uuid.uuid4()
    journal = FundJournal.objects.create(
        id=journal_id,
        gluuid=uuid.uuid4(),
        fund=fund,
        effective_date=effective_date,
        event_type=event_type,
        description=description,
        posted_date=timezone.now(),
    )
    for account, amount, partner in lines_data:
        FundJournalLine.objects.create(
            id=uuid.uuid4(),
            journal=journal,
            account=account,
            amount=Decimal(str(amount)),
            partner=partner,
        )
    return journal


with transaction.atomic():
    # =========================================================================
    # 0. IDEMPOTENCY CHECK
    # =========================================================================
    firm = Firm.objects.get(name__icontains="krakatoa")
    existing = Partner.objects.filter(
        fund__firm=firm,
        name="Dominic Toretto",
        is_active=True,
    ).first()
    if existing:
        print(f"SKIP: Dominic Toretto already exists as partner {existing.uuid} "
              f"(entity={existing.entity_id}) in {existing.fund.name}.")
        print("To re-run, first deactivate existing partners.")
        import sys
        sys.exit(0)

    # =========================================================================
    # 1. FIRM & CRM SETUP
    # =========================================================================
    print(f"Using firm: {firm.name} ({firm.id})")

    # Create CRMOrganization
    org = CRMOrganization.objects.create(
        id=uuid.uuid4(),
        name="Dominic Toretto",
    )
    print(f"Created CRMOrganization: {org.id}")

    # Create CRMEntity
    entity = CRMEntity.objects.create(
        id=uuid.uuid4(),
        organization=org,
        entity_type="individual",
        taxpayer_type="us",
    )
    print(f"Created CRMEntity: {entity.id}")

    # Create legal name + IndividualEntityInfo
    legal_name = LPCRMFullLegalName.objects.create(
        organization=org,
        first_name="Dominic",
        last_name="Toretto",
    )
    IndividualEntityInfo.objects.create(
        crm_entity=entity,
        organization=org,
        legal_name=legal_name,
        date_of_birth=date(1976, 8, 15),
    )
    print("Created IndividualEntityInfo")

    # =========================================================================
    # 2. FUND LP POSITIONS (limited_partner)
    # =========================================================================
    fund_configs = [
        {
            "carta_id": 59,    # Krakatoa Ventures Fund I
            "commitment": 5_000_000,
            "contributions": [
                (date(2018, 3, 15), 1_250_000),
                (date(2018, 9, 20), 750_000),
                (date(2019, 2, 10), 500_000),
                (date(2019, 8, 15), 625_000),
                (date(2020, 1, 22), 500_000),
                (date(2020, 7, 10), 375_000),
                (date(2021, 3, 15), 500_000),
                (date(2021, 11, 20), 500_000),
            ],
            "distributions": [
                (date(2021, 6, 30), 850_000),
                (date(2022, 3, 31), 1_200_000),
                (date(2022, 12, 15), 2_500_000),
                (date(2023, 6, 30), 1_750_000),
                (date(2024, 3, 31), 3_200_000),
            ],
            "unrealized": [
                (date(2022, 12, 31), 4_500_000),
                (date(2023, 12, 31), 6_200_000),
                (date(2024, 12, 31), 5_800_000),
            ],
            "realized": [
                (date(2022, 6, 30), 1_800_000),
                (date(2023, 6, 30), 3_500_000),
                (date(2024, 6, 30), 2_100_000),
            ],
        },
        {
            "carta_id": 58,    # Krakatoa Ventures Fund II
            "commitment": 3_500_000,
            "contributions": [
                (date(2020, 4, 15), 875_000),
                (date(2020, 10, 20), 525_000),
                (date(2021, 3, 10), 437_500),
                (date(2021, 9, 15), 350_000),
                (date(2022, 2, 22), 437_500),
                (date(2022, 8, 10), 350_000),
                (date(2023, 4, 15), 262_500),
                (date(2024, 1, 20), 262_500),
            ],
            "distributions": [
                (date(2023, 6, 30), 425_000),
                (date(2024, 3, 31), 680_000),
            ],
            "unrealized": [
                (date(2023, 12, 31), 2_800_000),
                (date(2024, 12, 31), 3_950_000),
            ],
            "realized": [
                (date(2024, 6, 30), 350_000),
            ],
        },
        {
            "carta_id": 497,   # Krakatoa Ventures Fund III
            "commitment": 2_000_000,
            "contributions": [
                (date(2022, 6, 15), 500_000),
                (date(2022, 12, 20), 300_000),
                (date(2023, 5, 10), 250_000),
                (date(2023, 11, 15), 200_000),
                (date(2024, 4, 22), 300_000),
                (date(2024, 10, 10), 200_000),
            ],
            "distributions": [],
            "unrealized": [
                (date(2023, 12, 31), 450_000),
                (date(2024, 12, 31), 820_000),
            ],
            "realized": [],
        },
        {
            "carta_id": 124,   # Krakatoa Growth Fund I
            "commitment": 500_000,
            "contributions": [
                (date(2019, 7, 15), 125_000),
                (date(2019, 12, 20), 75_000),
                (date(2020, 6, 10), 62_500),
                (date(2020, 12, 15), 62_500),
                (date(2021, 5, 22), 50_000),
                (date(2021, 11, 10), 50_000),
                (date(2022, 6, 15), 37_500),
                (date(2023, 1, 20), 37_500),
            ],
            "distributions": [
                (date(2022, 9, 30), 65_000),
                (date(2023, 3, 31), 110_000),
                (date(2024, 6, 30), 185_000),
            ],
            "unrealized": [
                (date(2023, 12, 31), 320_000),
                (date(2024, 12, 31), 480_000),
            ],
            "realized": [
                (date(2023, 6, 30), 95_000),
            ],
        },
    ]

    fund_partners = {}  # carta_id -> Partner for later GL use

    for config in fund_configs:
        fund = Fund.objects.get(carta_id=config["carta_id"])
        print(f"\n--- {fund.name} ---")

        pig = PartnerInterestGroup.objects.create(
            partner_type="limited_partner",
            fund=fund,
            name="Dominic Toretto",
            entity=entity,
        )

        partner = Partner.objects.create(
            partner_type="limited_partner",
            fund=fund,
            name="Dominic Toretto",
            entity=entity,
            partner_interest_group=pig,
        )

        CommitmentTransaction.objects.create(
            partner=partner,
            amount_cents=cents(config["commitment"]),
            date=config["contributions"][0][0] - timedelta(days=30),
        )
        print(f"  Commitment: ${config['commitment']:,.0f}")

        for dt, amount in config["contributions"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Capital contribution",
                partner=partner,
                source="capital_call_creation",
            )
        print(f"  Contributions: {len(config['contributions'])} totaling ${sum(a for _, a in config['contributions']):,.0f}")

        for dt, amount in config["distributions"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Distribution",
                partner=partner,
                source="capital_activity_creation",
            )
        if config["distributions"]:
            print(f"  Distributions: {len(config['distributions'])} totaling ${sum(a for _, a in config['distributions']):,.0f}")

        for dt, amount in config["unrealized"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Unrealized gain (loss)",
                partner=partner,
                source="allocations",
            )

        for dt, amount in config["realized"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Net realized gain (loss)",
                partner=partner,
                source="allocations",
            )

        # Management fee allocations (quarterly, small amounts)
        contrib_start = config["contributions"][0][0]
        fee_date = date(contrib_start.year, ((contrib_start.month - 1) // 3) * 3 + 3, 30)
        while fee_date <= date(2025, 12, 31):
            fee_amount = int(config["commitment"] * 0.005)  # ~2% annual = 0.5% quarterly
            CapitalAccountTransaction.objects.create(
                date=fee_date,
                cash_cents=cents(fee_amount),
                transaction_type="Management fees",
                partner=partner,
                source="allocations",
            )
            # Next quarter
            if fee_date.month == 12:
                fee_date = date(fee_date.year + 1, 3, 31)
            elif fee_date.month == 9:
                fee_date = date(fee_date.year, 12, 31)
            elif fee_date.month == 6:
                fee_date = date(fee_date.year, 9, 30)
            else:
                fee_date = date(fee_date.year, 6, 30)

        fund_partners[config["carta_id"]] = partner
        print(f"  Partner created: id={partner.id}, uuid={partner.uuid}")

    # =========================================================================
    # 3. GP ENTITY POSITIONS (member) with carry
    # =========================================================================
    gp_configs = [
        {
            "carta_id": 90,    # Krakatoa Fund I GP
            "commitment": 150_000,
            "carry_pct": 0.3300,  # 33%
            "vested_pct": 0.2800,
            "contributions": [
                (date(2018, 3, 15), 37_500),
                (date(2019, 2, 10), 25_000),
                (date(2020, 1, 22), 25_000),
                (date(2021, 3, 15), 25_000),
                (date(2022, 6, 15), 18_750),
                (date(2023, 4, 15), 18_750),
            ],
            "distributions": [
                (date(2022, 12, 15), 85_000),
                (date(2023, 6, 30), 120_000),
                (date(2024, 3, 31), 350_000),
            ],
            "carry_accrued": [
                (date(2022, 12, 31), 450_000),
                (date(2023, 12, 31), 680_000),
                (date(2024, 12, 31), 920_000),
            ],
        },
        {
            "carta_id": 127,   # Krakatoa Fund II GP
            "commitment": 125_000,
            "carry_pct": 0.3200,
            "vested_pct": 0.2500,
            "contributions": [
                (date(2020, 4, 15), 31_250),
                (date(2021, 3, 10), 25_000),
                (date(2022, 2, 22), 25_000),
                (date(2023, 4, 15), 21_875),
                (date(2024, 1, 20), 21_875),
            ],
            "distributions": [
                (date(2024, 3, 31), 45_000),
            ],
            "carry_accrued": [
                (date(2023, 12, 31), 180_000),
                (date(2024, 12, 31), 310_000),
            ],
        },
        {
            "carta_id": 501,   # Krakatoa Fund III GP
            "commitment": 175_000,
            "carry_pct": 0.3230,
            "vested_pct": 0.2200,
            "contributions": [
                (date(2022, 6, 15), 43_750),
                (date(2023, 5, 10), 35_000),
                (date(2024, 4, 22), 35_000),
                (date(2024, 10, 10), 26_250),
            ],
            "distributions": [],
            "carry_accrued": [
                (date(2024, 12, 31), 65_000),
            ],
        },
        {
            "carta_id": 502,   # Krakatoa Fund IV GP
            "commitment": 100_000,
            "carry_pct": 0.0400,
            "vested_pct": 0.0140,
            "contributions": [
                (date(2024, 3, 15), 25_000),
                (date(2024, 9, 20), 15_000),
                (date(2025, 2, 10), 10_000),
            ],
            "distributions": [],
            "carry_accrued": [
                (date(2024, 12, 31), 5_000),
            ],
        },
    ]

    gp_partners = {}  # carta_id -> Partner

    for config in gp_configs:
        fund = Fund.objects.get(carta_id=config["carta_id"])
        print(f"\n--- {fund.name} (GP) ---")

        pig = PartnerInterestGroup.objects.create(
            partner_type="member",
            fund=fund,
            name="Dominic Toretto",
            entity=entity,
        )

        partner = Partner.objects.create(
            partner_type="member",
            fund=fund,
            name="Dominic Toretto",
            entity=entity,
            partner_interest_group=pig,
        )

        CommitmentTransaction.objects.create(
            partner=partner,
            amount_cents=cents(config["commitment"]),
            date=config["contributions"][0][0] - timedelta(days=30),
        )
        print(f"  Commitment: ${config['commitment']:,.0f}")

        for dt, amount in config["contributions"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Capital contribution",
                partner=partner,
                source="capital_call_creation",
            )
        print(f"  Contributions: {len(config['contributions'])}")

        for dt, amount in config["distributions"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Distribution",
                partner=partner,
                source="capital_activity_creation",
            )

        for dt, amount in config["carry_accrued"]:
            CapitalAccountTransaction.objects.create(
                date=dt,
                cash_cents=cents(amount),
                transaction_type="Carried interest accrued",
                partner=partner,
                source="allocations",
            )
        print(f"  Carry accrued: {len(config['carry_accrued'])} entries")

        # Net operating income allocations (quarterly)
        contrib_start = config["contributions"][0][0]
        income_date = date(contrib_start.year, ((contrib_start.month - 1) // 3) * 3 + 3, 30)
        while income_date <= date(2025, 12, 31):
            income_amount = int(config["commitment"] * 0.003)  # small quarterly income
            CapitalAccountTransaction.objects.create(
                date=income_date,
                cash_cents=cents(income_amount),
                transaction_type="Net operating income (loss)",
                partner=partner,
                source="allocations",
            )
            if income_date.month == 12:
                income_date = date(income_date.year + 1, 3, 31)
            elif income_date.month == 9:
                income_date = date(income_date.year, 12, 31)
            elif income_date.month == 6:
                income_date = date(income_date.year, 9, 30)
            else:
                income_date = date(income_date.year, 6, 30)

        gp_partners[config["carta_id"]] = partner
        print(f"  Partner created: id={partner.id}, uuid={partner.uuid}")

    # =========================================================================
    # 4. CARRIED INTEREST ASSIGNMENTS for GP entities
    # =========================================================================
    print("\n--- Carry Assignments ---")
    UNITS_SCALE = 1_000_000  # 1M units = 100%

    for config in gp_configs:
        fund = Fund.objects.get(carta_id=config["carta_id"])
        partner = gp_partners[config["carta_id"]]

        # Check if assignment already exists
        existing = CarriedInterestAssignment.objects.filter(
            gp_entity=fund, deleted_date__isnull=True
        ).first()

        if existing:
            assignment = existing
            print(f"  Using existing carry assignment for {fund.name}")
        else:
            assignment = CarriedInterestAssignment.objects.create(
                gp_entity=fund,
                effective_date=config["contributions"][0][0] - timedelta(days=30),
            )
            print(f"  Created carry assignment for {fund.name}")

        total_units = int(config["carry_pct"] * UNITS_SCALE)

        # NOTE: vested_units/unvested_units/residual must be None to match
        # existing records. Setting explicit values triggers a validation
        # that requires vested + residual = total.
        PartnerCarriedInterestAssignment.objects.create(
            carried_interest_assignment=assignment,
            partner=partner,
            units=total_units,
        )
        print(f"  Carry for {partner.name}: {config['carry_pct']*100:.1f}% (vested: {config['vested_pct']*100:.1f}%)")

    # =========================================================================
    # 5. GL ENTRIES for GP entities ("lived in" data)
    # =========================================================================
    print("\n--- GL Entries for GP Entities ---")

    for config in gp_configs:
        fund = Fund.objects.get(carta_id=config["carta_id"])
        partner = gp_partners[config["carta_id"]]

        # Find key accounts (account_type is an integer)
        bank_acct = find_account(fund, 1000)
        # Look for contributed capital accounts
        contrib_cap_acct = find_account(fund, 3050) or find_account(fund, 3000)
        carry_dist_acct = find_account(fund, 3151) or find_account(fund, 3150)
        mgmt_fee_acct = find_account(fund, 6000)
        audit_acct = find_account(fund, 6100)
        dist_payable_acct = find_account(fund, 2500)

        if not bank_acct:
            print(f"  SKIP {fund.name}: no bank account found")
            continue

        journal_count = 0

        # Capital contribution journals
        for dt, amount in config["contributions"]:
            if bank_acct and contrib_cap_acct:
                create_journal(
                    fund, dt, "CONTRIBUTION",
                    f"Capital contribution - {partner.name}",
                    [
                        (bank_acct, Decimal(str(amount)), partner),
                        (contrib_cap_acct, Decimal(str(-amount)), partner),
                    ],
                )
                journal_count += 1

        # Distribution journals
        for dt, amount in config["distributions"]:
            if bank_acct and (carry_dist_acct or dist_payable_acct):
                dist_acct = carry_dist_acct or dist_payable_acct
                create_journal(
                    fund, dt, "DISTRIBUTION",
                    f"Cash distribution - {partner.name}",
                    [
                        (dist_acct, Decimal(str(amount)), partner),
                        (bank_acct, Decimal(str(-amount)), partner),
                    ],
                )
                journal_count += 1

        # Quarterly management fee accruals
        if mgmt_fee_acct and bank_acct:
            fee_date = date(2023, 3, 31)
            while fee_date <= date(2025, 12, 31):
                fee = int(config["commitment"] * 0.005)
                create_journal(
                    fund, fee_date, "MANAGEMENT_FEE_EXPENSE",
                    f"Management fee - Q{(fee_date.month-1)//3+1} {fee_date.year}",
                    [
                        (mgmt_fee_acct, Decimal(str(fee)), None),
                        (bank_acct, Decimal(str(-fee)), None),
                    ],
                )
                journal_count += 1
                if fee_date.month == 12:
                    fee_date = date(fee_date.year + 1, 3, 31)
                elif fee_date.month == 9:
                    fee_date = date(fee_date.year, 12, 31)
                elif fee_date.month == 6:
                    fee_date = date(fee_date.year, 9, 30)
                else:
                    fee_date = date(fee_date.year, 6, 30)

        # Annual audit fee
        if audit_acct and bank_acct:
            for year in range(2023, 2026):
                audit_fee = 15_000 + (config["commitment"] // 100)
                create_journal(
                    fund, date(year, 12, 31), "EXPENSE",
                    f"Annual audit fee - {year}",
                    [
                        (audit_acct, Decimal(str(audit_fee)), None),
                        (bank_acct, Decimal(str(-audit_fee)), None),
                    ],
                )
                journal_count += 1

        print(f"  {fund.name}: {journal_count} journal entries created")

    # =========================================================================
    # 6. PARTNER CONTACTS (primary contact with all permissions)
    # =========================================================================
    print("\n--- Partner Contacts ---")
    all_partners = list(fund_partners.values()) + list(gp_partners.values())

    for partner in all_partners:
        contact = PartnerContact.objects.create(
            partner=partner,
            partner_interest_group=partner.partner_interest_group,
            contact_email="dom@krakatoa.vc",
            primary=True,
        )
        PartnerContactPermission.objects.create(
            partner_contact=contact,
            wire_instructions=True,
            capital_call_notices=True,
            distribution_notices=True,
            annual_and_quarterly_reports=True,
            tax_documents=True,
        )

    print(f"  Created {len(all_partners)} PartnerContact + PartnerContactPermission records")

    # =========================================================================
    # 7. MARK PIGS AND PARTNERS AS ACCEPTED/SENT
    # =========================================================================
    print("\n--- Marking PIGs and Partners as accepted ---")
    now = timezone.now()
    today = now.date()

    for partner in all_partners:
        pig = partner.partner_interest_group
        pig.accepted_date = today
        pig.sent_date = today
        pig.save(update_fields=["accepted_date", "sent_date"])

        partner.accepted_date = today
        partner.sent_date = today
        partner.save(update_fields=["accepted_date", "sent_date"])

    print(f"  Set accepted_date and sent_date on {len(all_partners)} PIGs and Partners")

    # =========================================================================
    # 8. SUMMARY
    # =========================================================================
    print("\n" + "=" * 60)
    print("SEED COMPLETE: Dominic Toretto")
    print(f"  CRM Entity UUID: {entity.id}")
    print(f"  Organization UUID: {org.id}")
    print(f"  Fund LP positions: {len(fund_configs)}")
    print(f"  GP Entity positions: {len(gp_configs)}")

    total_cats = CapitalAccountTransaction.all_objects.filter(
        partner__entity=entity
    ).count()
    print(f"  Total CATs: {total_cats}")

    total_journals = FundJournal.objects.filter(
        fund__firm=firm,
        description__icontains="Toretto",
    ).count() + FundJournal.objects.filter(
        fund__carta_id__in=[90, 127, 501, 502],
        event_type__in=["MANAGEMENT_FEE_EXPENSE", "EXPENSE"],
        deleted_date__isnull=True,
    ).count()
    print(f"  Total GL journals (approx): {total_journals}")

    print(f"\n  Entity map URL: /entity-atlas/crm-entity/{entity.id}/")
    print(f"  Portfolio URL: /partner-portfolios/{entity.id}/entity-list")
    print("=" * 60)

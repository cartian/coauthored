---
date: 2026-03-03
description: Investigation into the cross-system data requirements for LP partner portfolios, covering the fund-admin ↔ carta-web bridge and the critical Corporation UUID = CRM Entity UUID invariant.
repository: fund-admin
tags: [entity-map, partner-portfolio, cross-system, carta-web, seeding]
---

# Partner Portfolio Cross-System Architecture

## Problem

When seeding test data for Dominic Toretto's LP portfolio, the partner dashboard returned 404. The entity map worked fine (fund-admin only), but the portfolio view — which bridges both systems — required careful cross-system alignment.

## The Critical Invariant: Corporation UUID = CRM Entity UUID

The partner portfolio init endpoint is the bridge between carta-web and fund-admin:

```
GET /partner-portfolios/<corp_pk>/app/init
```

Here's the data flow:

1. carta-web renders the portfolio page for Corporation PK (e.g., 2472)
2. carta-web calls fund-admin at `/partner-portfolios/2472/app/init`
3. fund-admin's `PartnerPortfolioService.get_partner_dashboard_init_metadata(acceptor_id=2472)`:
   - Calls gRPC back to carta-web: `CorporationServiceStub.list_corporations_using_cw_ids([2472])`
   - Gets back Corporation data including its UUID
   - **Uses that UUID directly as the CRM Entity ID**: `crm_entity_id = UUID(cw_corporations[0].uuid)`
   - Looks up partners via CRM entity

**If the carta-web Corporation UUID doesn't match the fund-admin CRM Entity UUID, the lookup returns nothing and the endpoint 404s.**

For existing (real) data, the sharing flow naturally synchronizes these UUIDs. When seeding manually, you must set them explicitly.

### Key code paths

- `fund_admin/partner_portfolios/services/partner_portfolio_service.py` — `get_partner_dashboard_init_metadata()`
- `fund_admin/capital_account/services/corporation_services.py` — `CorporationService.list_corporations_using_cw_ids()` (gRPC to carta-web)
- `fund_admin/partner_portfolios/views.py` — `PartnerPortfolioInitAPIView`

## All Required Records

### fund-admin side

| Model | Purpose |
|-------|---------|
| CRMOrganization | Container for the CRM entity |
| CRMEntity | The legal identity (UUID used as lookup key) |
| IndividualEntityInfo + LPCRMFullLegalName | Name and DOB |
| PartnerInterestGroup | Groups partners by entity+fund, needs `accepted_date` and `sent_date` |
| Partner | Individual fund position, needs `accepted_date` and `sent_date` |
| CommitmentTransaction | Commitment amount per partner |
| CapitalAccountTransaction | Contributions, distributions, gains, fees |
| PartnerContact | Primary contact with email, linked to partner+PIG |
| PartnerContactPermission | Boolean flags for document access types |
| CarriedInterestAssignment / PartnerCarriedInterestAssignment | GP carry (GP entities only) |
| FundJournal / FundJournalLine | GL entries (GP entities only) |

### carta-web side

| Model | Purpose | Key fields |
|-------|---------|------------|
| User | Login identity | email, username, password |
| Organization | Container org | `organization_type='individual'` (NOT default 'investment_firm') |
| Corporation | LP entity | `uuid` MUST match fund-admin CRM Entity UUID, `type='Personal'`, `can_hold=True` |
| EntityOrgPermission | Links Corp → Org | `entity=corp, organization=org` |
| OrganizationMembership | Links User → Org | Need both LP user and admin user |
| CapitalAccount | Bridges carta-web to fund-admin | `fund` (FK to fund corp), `accepter` (FK to LP corp), `fundadmin_partner_id`, `fundadmin_partner_uuid`, `sent_date`, `accepted_date` |

### FundLink mapping (carta-web Corp → fund-admin Fund)

The `FundLink` model in carta-web maps corporation IDs to fund-admin fund IDs. For Krakatoa Ventures:

| carta-web Corp ID | fund-admin Fund (carta_id) | Description |
|-------------------|---------------------------|-------------|
| 59 | 59 | Krakatoa Ventures Fund I |
| 58 | 58 | Krakatoa Ventures Fund II |
| 497 | 497 | Krakatoa Ventures Fund III |
| 124 | 124 | Growth Fund I |
| 90 | 90 | Fund I GP |
| 127 | 127 | Fund II GP |
| 501 | 501 | Fund III GP |
| 502 | 502 | Fund IV GP |

## Common Pitfalls

### Organization type defaults to 'investment_firm'
If you create an Organization without setting `organization_type='individual'`, the portfolio routes to `/investors/firm/<org_id>/portfolio/` instead of `/investors/individual/<corp_id>/portfolio/`. The firm view has different data requirements and may not work with individually-seeded data.

### Multiple admin users
`User.objects.get(email='admin@esharesinc.com')` returns multiple results. Use `User.objects.get(id=25)` — that's the active admin with `is_staff=True` and `is_superuser=True`.

### Docker container name
carta-web's main container is `python`, not `app`. Shell access: `docker exec -it python python manage.py shell_plus`.

### accepted_date / sent_date
PIGs and Partners need both `accepted_date` and `sent_date` set. Without these, the bulk_accept flow in carta-web won't find them, and various permission checks may fail.

## Reference: Existing Test Data

John Daley (known working LP):
- carta-web Corporation ID: 2470, UUID: `a2f23ebe-...` (matches his CRM Entity UUID)
- carta-web Organization ID: 163153, type: 'individual'
- Portfolio URL: `/investors/individual/2470/portfolio/`

Dominic Toretto (seeded):
- carta-web Corporation ID: 2472, UUID: `6ad327a3-cfe4-4326-932f-c02709f71c9b`
- carta-web Organization ID: 165153, type: 'individual'
- fund-admin CRM Entity UUID: `6ad327a3-cfe4-4326-932f-c02709f71c9b` (matches corp UUID)
- Portfolio URL: `/investors/individual/2472/portfolio/`

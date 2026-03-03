# fund-admin — Session 2026-03-03

## What we shipped
- Seeded complete Dominic Toretto test data across fund-admin and carta-web
  - fund-admin: CRM Entity, 8 PIGs, 8 Partners, ~257 CATs, ~52 GL journals, 4 carry assignments, 8 PartnerContacts w/ permissions
  - carta-web: User (dom@krakatoa.vc, id=77737), Organization (id=165153, type=individual), Corporation (id=2472, uuid matching CRM Entity), 8 CapitalAccounts, OrganizationMemberships
- Working LP portfolio for Dominic Toretto at both:
  - fund-admin: `/partner-portfolios/<entity_uuid>/entity-list`
  - carta-web: `/investors/individual/2472/portfolio/`
- Updated seed script (`scripts/seed_dominic_toretto.py`) with:
  - PartnerContact + PartnerContactPermission creation
  - accepted_date/sent_date on PIGs and Partners
  - Comprehensive carta-web setup instructions in docstring
- Documented the full cross-system architecture for partner portfolios

## What's in flight

### Branch: `gpe-310.cartian.as_of_date_in_entity_map_response`
- Clean, 2 commits ahead of master
- `as_of_date` in entity map API response

### Other open PRs
- PR #51788 (GPE-299 permission gate fix) — draft
- PR #50989 (fetcher registry refactor) — open
- PR #50927 (architecture readme) — open, docs-only

## What's next
- Open PR for as_of_date branch
- Continue entity map feature work
- Carry branch (`gpe-276.cartian.carried_interest_on_entity_map`) needs fresh PR

## Key decisions made
- **Corporation UUID = CRM Entity UUID**: The critical cross-system invariant. fund-admin's `PartnerPortfolioService.get_partner_dashboard_init_metadata()` fetches Corporation UUID via gRPC from carta-web and uses it directly as the CRM Entity lookup key. These MUST match.
- **Organization.organization_type must be 'individual'**: Default is 'investment_firm' which routes to firm portfolio view instead of individual portfolio view.
- **PartnerContacts needed for LP permissions**: Primary contact with all permission flags enabled.
- **Accepted/sent dates required**: PIGs and Partners need `accepted_date` and `sent_date` set for the portfolio to function properly.

## Key data references
- CRM Entity UUID: `6ad327a3-cfe4-4326-932f-c02709f71c9b`
- CRM Organization UUID: `67cd533f-7f1a-40d1-a7c7-dbede1205398`
- carta-web Corporation ID: 2472 (uuid matches CRM Entity)
- carta-web Organization ID: 165153
- carta-web User ID: 77737 (dom@krakatoa.vc)
- Admin user: id=25 (admin@esharesinc.com)

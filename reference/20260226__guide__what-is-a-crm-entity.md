---
date: 2026-02-26
description: Comprehensive guide to the CRMEntity model in fund-admin — what it is, how it relates to Partner/Organization/carta-web, and common gotchas
repository: fund-admin
tags: [crm-entity, permissions, entity-map, architecture, data-model]
---

# What Is a CRMEntity?

## One sentence

CRMEntity is the legal identity behind an investor — the LLC, the trust, the individual — that persists across all the funds they commit to.

## The relational picture

```
CRMOrganization  (= carta-web Organization)
  └─ CRMEntity   (= carta-web Corporation/Portfolio, after sharing)
       ├─ Partner on Fund A     (a commitment)
       ├─ Partner on Fund B     (another commitment)
       ├─ Partner on Fund C     (another commitment)
       └─ tax info, address, credit info, entity type...
```

Partner is a *position* — "this entity committed $5M to Fund II." CRMEntity is the *who* — "Acme Holdings LLC, EIN 12-3456789, a Delaware LLC." One CRMEntity can have many Partners across many funds in the same firm. Without CRMEntity, each Partner would carry its own copy of tax info, addresses, and entity classification — and they'd drift.

## Why it exists

Fund-admin has two concerns about an investor that pull in different directions:

1. **Per-fund accounting** — how much did they commit, what's their capital account balance, what distributions are they owed? This is the Partner model. It's fund-scoped.

2. **Cross-fund identity** — what's their tax ID, what type of entity are they, where do we mail their K-1, are they a non-resident alien? This is CRMEntity. It's firm-scoped.

CRMEntity exists because the same LLC invests in Fund II, Fund III, and Fund IV, and you don't want to re-enter (or reconcile) their tax info three times. It's the normalization layer for investor identity.

## Lifecycle: before and after sharing

CRMEntity has two distinct phases:

**Before sharing (draft):** The GP creates a Partner on a fund. Fund-admin mints a CRMEntity with a random UUID. This is a placeholder — it holds whatever entity data the GP entered, but it doesn't correspond to anything in carta-web yet. The LP hasn't seen it.

**After sharing:** The Partner gets "shared" to the LP (sent to their portal). Carta-web matches it to a Corporation (portfolio) with its own UUID. Fund-admin then **force-matches** — it replaces the CRMEntity's random UUID with the Corporation's UUID, merges any data from the dummy entity into the matched one, and deletes the dummy. From this point on, `CRMEntity.id == Corporation.uuid` in carta-web. That's how the two systems stay in sync without a mapping table — the primary key *is* the foreign key.

## Key fields

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID (PK) | After sharing, equals carta-web Corporation UUID |
| `organization` | FK to CRMOrganization | Groups entities under a carta-web Organization |
| `entity_type` | CharField (EntityTypes enum) | Tax classification: individual, LLC, trust, C-corp, etc. |
| `taxpayer_type` | CharField (TaxpayerType enum) | Taxpayer classification |
| `tax_id` / `encrypted_tax_id` | CharField / EncryptedCharField | SSN/EIN (plaintext being deprecated) |
| `default_credit_info` | FK to CreditInfo | Payment/credit qualification defaults |
| `default_address` | FK to Address | Mailing address |
| `individual_info` | OneToOne to IndividualEntityInfo | Extra fields for individuals |
| `corporate_info` | OneToOne to CorporateEntityInfo | Extra fields for corporations |
| `disregarded_entity_info` | OneToOne to DisregardedEntityInfo | Extra fields for DREs |
| `foreign_investor_info` | OneToOne to ForeignInvestorInfo | W-8 data for non-resident aliens |
| `beneficiary_info` | FK to LPBeneficiaryInformation | Distribution beneficiary data |

## Who points at CRMEntity

| Model | Field | Context |
|---|---|---|
| `Partner` | `entity` (FK, nullable) | Fund commitment |
| `PartnerInterestGroup` | `entity` (FK, nullable) | Commitment group (will replace Partner.entity) |
| `Prospect` | FK | Fundraising prospect |
| `ClosingsContact` | FK | Closing contact |
| `TaxFormW89` | FK | Tax form association |
| `ExtractionResult` | FK | Fundraising extraction |

## How the entity map uses it

When you hit `/entity-atlas/crm-entity/:uuid/`, the view:

1. Takes the CRMEntity UUID
2. Finds all Partners where `partner.entity_id == uuid`
3. Gets the funds those Partners are in
4. For GP Entity funds, traverses to the main funds they manage (via ManagingEntityLinks)
5. Filters to funds where the requesting user has `view_investments` permission
6. Builds the graph

The CRMEntity is the root of the tree — the "you are here" dot on the entity map that fans out to all their fund relationships.

## The passport analogy

CRMEntity is like a passport. It identifies *who you are* (legal name, nationality, ID number) regardless of which countries you've visited. Partner is like a visa stamp — it records that you entered a specific country (fund) on a specific date with specific terms. You have one passport but many stamps. If you change your address, you update the passport once, not every visa.

## Gotchas

1. **CRMEntity.id is not stable until sharing.** Before the LP sees it, the UUID is throwaway. After sharing, it locks to the carta-web Corporation UUID permanently. Code that caches CRMEntity UUIDs before sharing will break.

2. **Partner.entity is nullable.** A freshly created Partner has no CRMEntity yet. Any code traversing `partner.entity.organization` needs to handle `None`.

3. **CRMEntity is firm-scoped via CRMOrganization, not fund-scoped.** One CRMEntity spans all funds in a firm. If you filter Partners by fund, you'll get a subset of the CRMEntity's commitments, not all of them. The entity map explicitly gathers *all* Partners for the entity and then filters by permissions.

4. **entity_type is a tax classification, not a role.** The `EntityTypes` enum contains values like `individual`, `llc_taxed_as_partnership`, `corporation_c`, `charitable_trust` — these are IRS entity classifications, not business roles like "fund" or "firm."

## CRMEntity vs PartnerInterestGroup

These two models solve different problems at different levels.

**CRMEntity** answers: *"Who is this investor, legally?"*
Tax ID, entity type, mailing address, W-8 status. It spans the entire firm — the same CRMEntity appears across Fund II, Fund III, Fund IV. It's identity.

**PartnerInterestGroup** answers: *"What is this investor's commitment to this specific fund?"*
Contacts, wire instructions, document delivery, sharing status. It's scoped to one fund. It's the relationship between an entity and a fund.

### The three-layer hierarchy

```
CRMEntity  (firm-scoped identity — "Acme Holdings LLC")
  └─ PartnerInterestGroup  (fund-scoped commitment — "Acme's commitment to Fund III")
       ├─ Partner/Interest  (economic position — "Acme's Class A interest, $1M")
       └─ Partner/Interest  (economic position — "Acme's Class B interest, $500K")
```

Three layers, three concerns:

1. **CRMEntity**: Who are you? (tax, legal, identity)
2. **PartnerInterestGroup**: What's your deal with this fund? (contacts, access, wire info, sharing)
3. **Partner (→ Interest)**: What are your economic terms? (share class, commitment amount, capital account)

### Why PartnerInterestGroup was introduced

The old model had Partner doing double duty — it held both the fund relationship (contacts, wire info, sharing status) *and* the economic position (class, commitment, metrics). When one investor had two share classes in the same fund, they got two Partner records, which meant duplicate K-1s, duplicate emails, duplicate everything.

PartnerInterestGroup pulls the relationship-level stuff up one layer. Now Spencer Holton with Class A and Class B interests gets one PartnerInterestGroup (one set of contacts, one K-1, one email) and two Partners/Interests underneath (two sets of economic terms).

### How they relate to CRMEntity differently

Both have an `entity` FK to CRMEntity, but the semantics differ:

- **CRMEntity → PartnerInterestGroup**: one-to-many *across funds*. The same CRMEntity has one PartnerInterestGroup per fund it's invested in. Enforced by a unique constraint on `(fund, entity)`.
- **CRMEntity → Partner**: one-to-many *across funds and share classes*. This is the legacy path — being phased out as Partner gets stripped down to just economic fields.

During the transition, both FKs exist and a health check ensures they stay in sync. Eventually Partner loses its `entity` FK entirely.

### What stays where after the migration

| Concern | Before | After |
|---|---|---|
| Tax ID, entity type, address | CRMEntity | CRMEntity (unchanged) |
| Contacts, wire info, sharing status | Partner | PartnerInterestGroup |
| Document delivery, access perms | Partner | PartnerInterestGroup |
| Share class, commitment, metrics | Partner | Partner (renamed Interest) |
| Name, partner_type | Partner (duplicated) | PartnerInterestGroup (authoritative) |

### The feature flag

`USE_PARTNER_INTEREST_GROUPS` controls which model is source of truth. When off, Partner is authoritative and health checks backfill PartnerInterestGroup. When on, PartnerInterestGroup is authoritative. The flag is rolled out per-firm.

### Extended analogy

CRMEntity is your passport. PartnerInterestGroup is your membership at a specific gym. Partner/Interest is the specific classes you're enrolled in at that gym. You have one passport, memberships at several gyms, and multiple class enrollments at each gym. The passport doesn't change when you switch gyms; the membership doesn't change when you switch classes.

## Key files

| File | What's there |
|---|---|
| `fund_admin/lp_crm/models.py` | CRMEntity and CRMOrganization model definitions |
| `fund_admin/lp_crm/constants.py` | EntityTypes, TaxpayerType, TaxIDTypes enums |
| `fund_admin/lp_crm/services/crm_entity_service.py` | Service layer for CRMEntity operations |
| `fund_admin/lp_crm/services/partner_sharing_service.py` | Sharing flow (creates/matches CRMEntities) |
| `fund_admin/lp_crm/services/partner_matching_service.py` | Cross-fund entity matching |
| `fund_admin/entity_map/views/entity_map_crm_entity_view.py` | Entity map view using CRMEntity as root |
| `fund_admin/entity_map/invested_in_relationship_graph.py` | Graph builder that traverses from CRMEntity |
| `fund_admin/capital_account/models/partner.py` | Partner model with entity FK |

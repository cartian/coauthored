---
date: 2026-02-18
description: Exploration of the partner_portfolios app, deal containers, allocations, and carry attribution in fund-admin. Combines technical breakdown with accessible explanations.
repository: fund-admin
tags: [deal-attribution, partner-portfolios, allocations, deal-containers, carry, exploration]
---

# Partner Portfolios, Deal Containers, and Allocations

This document is the foundational exploration for the deal-attribution project. It maps the key models, relationships, and data flows in fund-admin that govern how money moves from journal entries to individual partner accounts, and how deals are tracked through their lifecycle.

## The Plain-Language Version

Imagine you manage a venture fund. Dozens of investors (partners) pooled their money. You invest that pooled money into startups (deals). When something happens financially -- a capital call, a distribution, a management fee -- you need to divide that event proportionally among your partners. That division process is **allocation**.

Here's how the system models this:

1. **Partners** are the investors. Each partner belongs to a fund and has a commitment (how much they promised to invest).

2. **Journals and journal lines** are the accounting entries. When the fund calls capital or distributes profits, a journal is created with line items.

3. **Allocation rules** are the instructions for dividing journal line amounts among partners. The simplest rule is pro-rata (proportional to commitment), but rules can be custom, class-based, time-bounded, and scoped to specific accounts, issuers, or assets.

4. **Allocations** connect a journal line to the rule that governs how it's divided.

5. **Partner records** are the atomic result: "Partner X gets $Y from this journal line." The sum of all partner records for an allocation equals the journal line amount.

6. **Deal containers** track the lifecycle of a single investment. When the fund invests in Company A, a deal container is created. If that investment converts (e.g., a SAFE converts to equity), the new asset is linked to the same container. This lets you calculate deal-level metrics like MOIC and IRR.

7. **Carry attribution** tracks how carried interest (the GP's performance fee) is attributed to specific deals. When the fund earns carry, that carry can be split across the deals that generated it.

Think of it as a pipeline:

```
Journal Entry
    |
    v
Allocation Rule (how to split)  +  Allocation Bucket (what category)
    |
    v
Allocation (the split event)
    |
    v
Partner Records (individual amounts per partner)
```

And in parallel, for investment tracking:

```
Investment made  -->  DealContainer created
    |
Asset added     -->  DealAsset links asset to container
    |
Carry earned    -->  CarryAttributionGroup + CarryAttribution per deal
```

---

## Technical Breakdown

### The Allocation System

The allocation system lives in `fund_admin/general_ledger/accounting/fund/allocations/`. It has a clear hierarchy:

#### AllocationBucket

**File:** `allocations/models.py:548`
**Table:** inherited from `BaseAllocationsModel`

Categories for partner capital account statements. These are the line items partners see: "Management fees", "Investments", "Legal fees", etc. Global and unique -- not fund-specific.

```
AllocationBucket
  - name: CharField (unique, indexed)
```

#### AllocationBucketLink

**File:** `allocations/models.py:588`

Fund-specific configuration mapping accounts to buckets. Each fund decides which GL accounts roll up into which statement categories.

```
AllocationBucketLink
  - account -> FundAccount
  - fund -> Fund
  - allocation_bucket -> AllocationBucket
  unique: (account, fund) where not soft-deleted
```

#### AllocationRule

**File:** `allocations/models.py:682`

The core instructions for how to divide a journal line amount among partners.

```
AllocationRule
  - fund -> Fund
  - strategy: CharField (pro-rata, custom, etc.)
  - partner_selection_strategy: CharField (determines which partners participate)
  - partner_class -> PartnerClass (optional, for class-based selection)
  - effective_date / expiration_date: DateField (time-bounded rules)
  - is_default: BooleanField
  - name, notes: descriptive fields
```

Key design constraints:
- If `partner_selection_strategy` is `USE_PARTNER_CLASS`, then `partner_class` must be set.
- `effective_date <= expiration_date` when both are present.
- Default rules cannot have date bounds.
- The `effective_date` and `expiration_date` fields are protected by a `pgtrigger.ReadOnly` trigger -- updates must go through official interfaces that ignore the trigger.

**How rules work:** The `strategy` field determines percentages (pro-rata by commitment, custom percentages, etc.). The `partner_selection_strategy` determines *who* participates. If neither is set, the `ParticipatingPartner` records define both.

#### ParticipatingPartner

**File:** `allocations/models.py:846`

Join table linking partners to allocation rules. Also stores custom allocation percentages when the rule strategy doesn't dictate them automatically.

```
ParticipatingPartner
  - partner -> Partner
  - allocation_rule -> AllocationRule
  - allocation_percentage: Decimal(9,6) (nullable -- null means pro-rata strategy decides)
```

#### AllocationRuleScenario

**File:** `allocations/models.py:918`

Defines *when* to use a particular allocation rule. This is the matching layer: when a journal line comes in, the system finds the right rule by matching the line's account, issuer, or asset against scenarios.

```
AllocationRuleScenario
  - allocation_rule -> AllocationRule
  - fund -> Fund
  - account -> FundAccount (optional)
  - issuer -> Issuer (optional)
  - asset -> Asset (optional)
  - effective_date / expiration_date: synced from AllocationRule via pgtrigger
```

Constraints enforce:
- At least one of account, issuer, or asset must be present (no scope-less scenarios).
- Issuer and asset cannot coexist on the same scenario.
- Time-range exclusion constraints prevent overlapping scenarios for the same fund+account, fund+issuer+account, or fund+asset+account combinations.

This enables three levels of allocation granularity:
1. **Fund-level:** scenario has only an account (all journal lines to that account use this rule)
2. **Issuer-level:** scenario has issuer + account (lines for a specific issuer use this rule)
3. **Asset-level:** scenario has asset + account (lines for a specific asset use this rule)

#### Allocation

**File:** `allocations/models.py:1129`

The bridge between a journal line and the partner records it produces.

```
Allocation
  - fund -> Fund
  - allocation_bucket -> AllocationBucket
  - allocation_rule -> AllocationRule (optional)
  - journal_line -> FundJournalLine (optional, unique when not deleted)
  - effective_date: DateField
  - gluuid: UUIDField (tracks versions over time)
  - source: CharField (enum)
  - is_posted: BooleanField (denormalized from journal)
```

One allocation per journal line (enforced by unique constraint). Multiple Postgres triggers fire on insert/update/delete to maintain metrics caches.

#### PartnerRecord

**File:** `allocations/models.py:1268`

The atomic unit. One record per partner per allocation.

```
PartnerRecord
  - partner -> Partner
  - allocation -> Allocation
  - calculated_amount: Decimal(22,2) (what the rule computed)
  - amount: Decimal(22,2) (actual amount, may differ from calculated due to manual override)
  - notes: TextField (explains adjustments)
  - is_transfer: BooleanField
  - transfer_type: TextField
```

The distinction between `calculated_amount` and `amount` is important: fund admins can override the system's calculation for a specific partner. The `notes` field explains why. This audit trail is critical for compliance.

A pgtrigger prevents creating partner records on soft-deleted allocations.

---

### The Deal Container System

Deal containers live in `fund_admin/general_ledger/accounting/fund/deal/`. They track investment lineage.

#### DealContainer

**File:** `deal/models.py:150`
**Table:** `gl_deal_container`

```
DealContainer (extends GLCoreModel -- has soft-delete via deleted_date)
  - id: UUIDField (primary key)
  - fund -> Fund (PROTECT)
  - name_override: CharField (optional display name)
  - initial_investment_date: DateField
```

A deal container is created when a fund first invests in something. It intentionally excludes `issuer_id` to support M&A scenarios where a deal spans multiple issuers (e.g., Company A acquires Company B, and the fund's investment in B continues through A).

The conditional index on `fund` excludes soft-deleted records for query performance.

#### DealAsset

**File:** `deal/models.py:224`
**Table:** `gl_deal_asset`

```
DealAsset (extends GLCoreModel)
  - deal_container -> DealContainer (CASCADE)
  - asset -> Asset (PROTECT)
  - asset_type: CharField (NEW_INVESTMENT or CONVERSION)
  - journal_gluuid: UUIDField (the journal that triggered this link)
  unique: (deal_container, asset) where not soft-deleted
```

Links assets to their deal container. The `asset_type` distinguishes initial investments from conversions (e.g., SAFE to equity). The `journal_gluuid` provides traceability back to the specific accounting event.

---

### The `deal_specific` App

The `deal_specific` app lives at `fund_admin/gp_entities/deal_specific/` and implements deal-level tracking and carry attribution for GP entities. It follows clean architecture with distinct domain, service, data, and API layers:

```
Views (API) → Services → Domain ← Data (Repository)
                ↓          ↑
           Domain Service
```

The domain layer has no infrastructure dependencies. Validators inject via protocols. The repository depends on domain objects, not vice versa.

#### Models (Persistence)

**File:** `gp_entities/models/deal_specific.py`

##### GPDeal (Line 206)

```
GPDeal (extends BaseModel)
  - id: UUIDField (primary key)
  - deal_container_id: UUIDField (indexed, NOT a ForeignKey -- loose coupling)
  - gp_entity -> Fund (PROTECT, related_name='gp_entity_deals')
  - fund -> Fund (PROTECT, related_name='lp_fund_deals')
  unique: (deal_container_id, gp_entity)
  indexes: deal_container_id, gp_entity
```

Thin adapter bridging general_ledger's `DealContainer` into the GP entity domain. Uses UUID reference instead of ForeignKey to maintain domain separation. Both `gp_entity` and `fund` are `Fund` model instances -- `Fund` is the polymorphic entity type in fund-admin (LP funds, GP entities, and management companies are all `Fund` records differentiated by `entity_type`).

##### CarryAttributionGroup (Line 283)

```
CarryAttributionGroup (extends BaseModel)
  - id: UUIDField (primary key)
  - gp_entity -> Fund (CASCADE)
  - fund -> Fund (CASCADE)
  - journal_gluuid: UUIDField
  - journal_line_gluuid: UUIDField
  - effective_date: DateField
  - total_available_to_attribute: Decimal(22,2)
  - is_stale: BooleanField (default=False)
  unique: (journal_gluuid, gp_entity, fund)
```

Created when a carry-related journal line needs its carry distributed across deals. The `is_stale` flag marks groups where the underlying journal has changed since attribution was calculated -- currently marks stale but does not auto-recalculate. Recalculation is triggered via the update endpoint or journal repost.

##### CarryAttribution (Line 349)

```
CarryAttribution (extends BaseModel)
  - id: UUIDField (primary key)
  - carry_attribution_group -> CarryAttributionGroup (CASCADE)
  - gp_deal -> GPDeal (CASCADE)
  - amount: Decimal(20,2)
  - created_by / modified_by: IntegerField (user IDs)
  unique: (carry_attribution_group, gp_deal)
```

The atomic unit of carry attribution. Sum of all `amount` values in a group should equal the group's `total_available_to_attribute`.

**Sign convention:** Carried interest accrued accounts are credit-normal, so attribution amounts are stored as negative values in the DB. The display layer flips signs (`-attribution.amount`) for the UI.

---

#### Domain Layer

**Location:** `gp_entities/deal_specific/domain/`

The domain layer models business rules as pure dataclasses with no ORM dependencies.

##### GPDealDomain / EnrichedGPDealDomain (`domain/gp_deal.py`)

`GPDealDomain` is a lightweight projection of the ORM model with a `from_model` factory. `EnrichedGPDealDomain` extends it with an `EnrichedDealContainerDomain` for display -- provides a `deal_name` property that returns `name_override` or `display_name` from the container.

##### CarryAttributionGroupDomain — the Aggregate Root (`domain/carry_attribution.py`)

This is the core domain object. `CarryAttributionGroupDomain` is an aggregate root that owns a list of `CarryAttributionDomain` children and enforces the central business invariant: **total attributed cannot exceed total available**.

```python
CarryAttributionGroupDomain
  - id, gp_entity_id, lp_fund_id, journal_gluuid, journal_line_gluuid
  - effective_date, total_available_to_attribute, is_stale
  - _deal_attributions: list[CarryAttributionDomain]  # private, modified only through aggregate

  Properties:
    deal_attributions  → tuple (immutable view)
    total_attributed   → sum of all attribution amounts
    remaining_to_attribute → available - attributed

  Methods:
    add_deal_attribution(attribution)
    update_deal_attribution(attribution_id, amount, modified_by)
    bulk_set_deal_attributions(updates: list[DealAttributionInput], modified_by)
    handle_journal_posted(event: JournalPostedEvent)  # marks stale if amounts/dates changed
```

Every mutation validates totals via `_validate_totals()` in `__post_init__` and after each write operation. Children (`CarryAttributionDomain`) expose a `set_amount(amount, modified_by)` method and `to_model`/`from_model` factories.

Supporting value objects:
- `JournalPostedEvent`: journal_gluuid, journal_line_gluuid, effective_date, amount
- `DealAttributionInput`: deal_id, amount

##### Validation Protocols (`domain/validation_protocols.py`)

Abstract base classes defining cross-aggregate validation contracts:

- `GPEntityFundValidator.validate_gp_manages_fund(gp_entity_id, fund_id) -> bool`
- `GPDealContextValidator.validate_deal_context(deal_id, expected_gp_entity_id, expected_fund_id) -> bool`

These are implemented by adapters in the data layer, keeping the domain free of infrastructure concerns.

##### CarryAttributionDomainService (`domain/carry_attribution_domain_service.py`)

Orchestrates cross-aggregate validation and creation. All carry attribution objects should be created through this service.

```
Dependencies (injected via protocols):
  - GPEntityFundValidator
  - GPDealContextValidator
  - FundJournalLineService
  - FundJournalService
  - AllocationService

Methods:
  create_carry_attribution(gp_entity_id, journal_line_gluuid)
      → CarryAttributionGroupDomain (empty, validated)
  create_carry_attribution_with_deals(...)
      → CarryAttributionGroupDomain (with initial attributions)
  add_deal_attribution(...)
  set_deal_attributions(...)  # bulk replace
```

Internally validates: GP entity manages the fund, each deal belongs to the correct GP entity + fund context, journal line exists and has an allocation.

---

#### Data Layer

**Location:** `gp_entities/deal_specific/data/`

##### CarryAttributionRepository (`data/carry_attribution_repository.py`)

Abstracts persistence for the carry attribution aggregate.

**Retrieval:**
- `get_attribution_for_journal_gluuid(journal_gluuid)` → single group or None
- `get_groups_for_period(gp_entity_id, start_date, end_date)` → list of groups in date range
- `get_group_by_id_and_gp_entity(group_id, gp_entity_id)` → single group, scoped
- `get_groups_for_period_with_fund_filter(...)` → period query with optional fund filter
- `get_source_funds(gp_entity_id)` → funds with carry attributions
- `get_available_periods(gp_entity_id)` → quarters with attribution data

**Persistence:**
- `save(attribution)` → atomic save with `update_or_create`, deletes removed attributions
- `delete(attribution)` → cascading delete

Uses the domain service during reconstitution from DB to ensure invariants hold.

##### Validator Adapters (`data/validators.py`)

- `GPEntityFundValidatorAdapter`: Uses `ManagingEntityLinksService` and `FundService` to check GP entity manages fund. Raises `DealValidationError` on failure.
- `GPDealContextValidatorAdapter`: Uses Django ORM to verify GPDeal exists with correct gp_entity_id and fund_id.

---

#### Service Layer

**Location:** `gp_entities/deal_specific/services/`

##### GPDealService (`services/gp_deal_service.py`)

Manages GPDeal CRUD and enrichment. Key methods:

- `list_deals(gp_entity_id, fund_id?)` → deals grouped by fund with container names
- `list_enriched_gp_deals(gp_entity_id, gp_deal_ids?)` → enriched with DealContainer data
- `get_deals_for_deal_containers(gp_entity_id, deal_container_ids)` → dict[container_id, GPDealDomain]
- `get_deals_for_assets(gp_entity_id, asset_ids)` → dict[asset_id, GPDealDomain] via the DealAsset → DealContainer → GPDeal chain

##### GPDealAutomationService (`services/gp_deal_automation_service.py`)

Automates GPDeal creation. Derives GP entity from a fund's management company relationship and creates the GPDeal via `get_or_create`. Publishes `GPDealCreatedDomainEvent` on creation. Returns None if no managing GP entity found. Transaction-wrapped.

##### CarryAttributionService (`services/carry_attribution_service.py`)

The main orchestration service. Coordinates automated calculation, manual adjustments, and query operations.

**Event handlers:**
- `handle_journal_posted(event)` — processes journals on GP entities, finds the carried interest accrued journal line, creates or updates the attribution group. If new: calculates via `CarryAttributionCalculator`. If existing: recalculates and marks stale if needed. Enforces one carry line per journal.
- `handle_journal_deleted(event)` — deletes the attribution group. Handles a race condition: checks if the journal was recreated before deleting (entity accounting sync pattern where journals are delete-then-recreate).

**Queries:**
- `get_aggregated_attribution(gp_entity_id, period, year, source_fund_id?)` → summary with deal breakdown, using full-period gains
- `get_attribution_list(gp_entity_id, period, year, source_fund_id?)` → detailed list with groups and individual attributions, using per-effective-date gains (point-in-time)
- `get_deal_metrics(gp_entity_id, source_fund_id, as_of_date)` → deal-level investment gains, period determined by fund's carry reporting cadence
- `get_source_funds(gp_entity_id)` / `get_available_periods(gp_entity_id)`

**Writes:**
- `update_group_attributions(group_id, gp_entity_id, request, modified_by)` — manual update
- `create_group_with_attributions(...)` — manual creation

**Carried interest account types:** The service identifies carry lines by matching against a defined list of COA account types (`CARRIED_INTEREST_ACCRUED_ACCOUNTS`).

##### CarryAttributionCalculator (`services/carry_attribution_calculator.py`)

Calculates deal-level gains and attribution percentages. Two strategies:

1. **Gains-based attribution (primary):** Distribute carry proportionally to each deal's investment gains in the period. Calculates gains by aggregating journal lines with investment gain/loss account types, mapping assets → DealAsset → DealContainer → GPDeal.

2. **Cost-basis fallback:** When carry and gains have opposite signs (mismatch scenario), falls back to cost-basis weighting via `IssuerWithAssetsMetricsService`. Skips assets with no/negative cost basis.

Key methods:
- `calculate_deal_attributions_for_journal(journal_gluuid)` → list[DealAttributionInput]
- `calculate_gains_by_deal(gp_entity_id, fund_id, start_date, end_date)` → dict[deal_id, DealGains]
- `get_gain_calculation_period_for_carry_booking_date(fund_id, booking_date)` → (start_date, end_date) based on fund's carry reporting cadence

Returns empty dict if total gains are zero. Raises ValueError if an asset isn't linked to a deal.

---

#### Domain Events

**Location:** `gp_entities/deal_specific/domain_events/`

Three event listeners drive automation, all feature-flagged for gradual rollout:

| Listener | Listens for | Feature flag | Action |
|----------|-------------|-------------|--------|
| `GPDealAutomationListener` | `DealContainerCreatedDomainEvent` | `GPE_102_AUTOMATED_DEAL_CREATION` | Creates GPDeal via automation service |
| `GPDealCarryListener` | `FundJournalPostedDomainEvent` | `GPE_129_AUTOMATED_CARRY_ATTRIBUTION` | Triggers carry attribution calculation |
| `GPDealJournalDeletedListener` | `FundJournalDeletedDomainEvent` | `GPE_129_AUTOMATED_CARRY_ATTRIBUTION` | Cleans up attribution groups |

The app also publishes `GPDealCreatedDomainEvent` (with gp_deal_id, deal_container_id, fund_id, gp_entity_id) which triggers grant-to-deal association for carry calculation downstream.

---

#### API Layer

**Location:** `gp_entities/deal_specific/api/` and `gp_entities/deal_specific/views.py`

All views use `dc_exposed` decorator for dataclass-based serialization. Serializers use `rest_framework_dataclasses`.

| Method | Path | View | Permissions | Purpose |
|--------|------|------|-------------|---------|
| GET | `<gp_entity_id>/deals/` | `GPDealListView` | IsStaff | List deals, optionally filtered by fund |
| GET | `<fund_pk>/deals/metrics` | `DealMetricsView` | IsStaff \| HasFundPermission | Deal-level investment gains as of date |
| GET | `<fund_pk>/carry-attribution/` | `CarryAttributionSummaryView` | IsStaff \| HasFundPermission | Aggregated attribution summary for period |
| GET | `<fund_pk>/carry-attribution/list/` | `CarryAttributionListView` | IsStaff \| HasFundPermission | Detailed attribution list with groups |
| GET | `<fund_pk>/carry-attribution/source-funds/` | `CarryAttributionSourceFundsView` | IsStaff \| HasFundPermission | Funds with carry attributions |
| GET | `<fund_pk>/carry-attribution/periods/` | `CarryAttributionPeriodsView` | IsStaff \| HasFundPermission | Quarters with attribution data |
| POST | `carry-attribution-groups/` | `CarryAttributionGroupCreateView` | IsStaff | Create attribution group with deals |
| PATCH | `<fund_pk>/carry-attribution-groups/<group_id>/` | `CarryAttributionGroupUpdateView` | IsStaff \| HasFundPermission | Update attributions within a group |

Note: `fund_pk` refers to GP entity ID in these routes -- GP entities are specialized funds.

The update DTO (`CarryAttributionUpdateItem`) flips the sign on `amount` when converting to `DealAttributionInput`, translating between display-positive and storage-negative conventions.

---

#### Exceptions

`DealValidationError` (`deal_specific/exceptions.py`) covers GPDeal context mismatches, attribution constraint violations, and missing journal/allocation references. Caught at the view layer and re-raised as DRF `ValidationError` or `NotFound`.

---

### The Partner Portfolio Layer

The `partner_portfolios` app (`fund_admin/partner_portfolios/`) is a read-only aggregation layer. It has no database models -- only dataclass domains and services that pull data from the systems above.

#### Key Concepts

- **CRM Entity**: A corporation in the CRM system that represents an investor. One CRM entity may have partners across multiple funds.
- **PartnerPortfolioContext**: A pre-fetched data bundle (partners, funds, sharing dates) built once per request to avoid redundant gRPC/DB calls.
- **Sharing date**: The date from which a partner is allowed to see fund information. Controls what metrics are visible.

#### Services

**PartnerPortfolioService** (`services/partner_portfolio_service.py`):
- Builds the `PartnerPortfolioContext` from CRM entity ID
- Computes dashboard mode (GP vs LP vs both) based on partner types
- Aggregates capital metrics across all partners for a CRM entity
- Produces entity list (funds grouped by firm) with per-fund metrics
- Generates carried interest accrued timeseries (quarterly)

**PartnerPortfolioInvestmentService** (`services/partner_portfolio_investment_service.py`):
- Single-fund investment overview
- Fund-specific metrics summary
- Carry grants summary per partner

Both services delegate metric calculation to `PartnerAccountMetricsService` and carry data to `CarriedInterestGrantService`.

#### Metrics Calculated

The standard partner metrics pulled for portfolio views:
- Commitment
- Called capital
- Capital contributed (GAAP)
- Prepaid capital contribution
- Capital contributed (paid)
- Distribution
- Net asset value
- Carried interest accrued
- Capital call liabilities

---

### Data Flow: End to End

#### From Journal to Partner Statement

```
1. Journal posted with line items
2. Each journal line matched to AllocationRuleScenario
   (by fund + account, or fund + account + issuer/asset)
3. Matched scenario yields an AllocationRule
4. Allocation record created, linking journal line to rule and bucket
5. Rule's strategy + partner selection determine participating partners and percentages
6. PartnerRecord created for each participating partner
7. Partner capital account statements aggregate PartnerRecords by AllocationBucket
```

#### From Investment to Deal-Level Carry

```
1. Investment journal posted
2. DealContainer created → DealContainerCreatedDomainEvent published
3. GPDealAutomationListener (flag: GPE_102) derives GP entity from
   fund's management company and creates GPDeal via get_or_create
   → GPDealCreatedDomainEvent published (triggers grant-to-deal association)
4. DealAsset links the investment's asset to the container
5. When carry is earned (journal posted with carried interest accrued line):
   → FundJournalPostedDomainEvent published
   → GPDealCarryListener (flag: GPE_129) triggers CarryAttributionService
   a. Service finds the carried interest accrued journal line
   b. CarryAttributionCalculator computes deal-level gains for the period
   c. Primary strategy: distribute carry proportional to gains
      Fallback: cost-basis weighting if carry and gains have opposite signs
   d. CarryAttributionGroup + CarryAttribution records created
   e. Sum of attributions = total carry from that line
6. If journal is later modified:
   → Existing group marked is_stale=True if effective_date or amount changed
   → Attributions recalculated on journal repost
7. If journal is deleted:
   → GPDealJournalDeletedListener cleans up the attribution group
   → Race condition guard: checks if journal was recreated before deleting
8. Partner portfolio views query carry attributions for dashboard display
```

---

## Key Architectural Observations

**Domain separation is deliberate.** The `DealContainer` lives in `general_ledger`, while `GPDeal` lives in `gp_entities`. They're linked by UUID, not ForeignKey. This keeps the accounting domain independent of the GP entity domain -- important for a system where not all funds have GP entities.

**`Fund` is polymorphic.** LP funds, GP entities, and management companies are all `Fund` records. The `GPDeal` model has two Fund ForeignKeys (`gp_entity` and `fund`) pointing to different entity types. This is a pattern throughout fund-admin.

**Time-bounded rules with exclusion constraints.** Allocation rules and scenarios use PostgreSQL range exclusion constraints to prevent overlapping effective date ranges. This is a sophisticated approach that handles temporal data integrity at the database level rather than in application code.

**Calculated vs. actual amounts.** The `PartnerRecord` dual-amount pattern (`calculated_amount` vs. `amount`) provides both auditability and override flexibility. Fund admins can adjust allocations while preserving what the system originally computed.

**The portfolio layer is read-only.** `partner_portfolios` composes data from the capital account, allocation, GP entity, and metrics subsystems. It has no models of its own -- it's purely a presentation/aggregation concern.

**Carry attribution is both automated and manual-capable.** Event-driven listeners handle automated creation and calculation behind feature flags (`GPE_102`, `GPE_129`). The `CarryAttribution` model tracks `created_by` and `modified_by` for audit, and the API exposes create/update endpoints for manual adjustments. The `is_stale` flag marks groups needing recalculation when journals change.

**The `deal_specific` app uses aggregate-root DDD.** `CarryAttributionGroupDomain` is the aggregate root -- child attributions are modified only through the aggregate, which validates totals after every mutation. Cross-aggregate validation (GP entity manages fund, deal belongs to correct context) is handled by a domain service injecting validators via protocols. This keeps the domain layer free of infrastructure concerns.

**Calculation has a deliberate fallback strategy.** Gains-based attribution (proportional to investment gains) is primary. When carry and gains have opposite signs -- a mismatch scenario that can occur in certain fund structures -- the calculator falls back to cost-basis weighting. Zero-gains scenarios return an empty attribution set rather than failing.

## Related

- [reference/decisions.md](../reference/decisions.md) -- decision log (add entries as deal-attribution design progresses)

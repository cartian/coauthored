---
name: entity-map-context
description: Load entity map domain context — architecture, permission model, key abstractions, gotchas, and pointers to deeper docs
user_invocable: true
---

# Entity Map — Domain Context

Use this skill to bootstrap sessions working on the Entity Map feature in fund-admin. This is curated context, not exhaustive documentation.

## What It Is

A graph visualization of fund investment structure embedded in the Partner Portfolio (GP Dashboard). Shows funds, GP entities, partners, portfolios, and assets as a directed graph. Four view modes: fund, firm, CRM entity (investor-rooted), and journal impact.

## The Pipeline

Every request flows through five stages:

```
View → EntityMapService → InvestedInRelationshipGraph → GraphBuilder → NodeFetcherService → Graph
```

**InvestedInRelationshipGraph** — lightweight topology layer. Maps which funds invest in which other funds. Three build methods: `build_for_firm()`, `filtered_to_fund_subgraph()`, `build_for_crm_entity()`. Fund-level permission filtering happens here (before GraphBuilder sees the data).

**GraphBuilder** — converts topology into renderable `Graph` with typed nodes and edges. Four phases: collect identifiers → fetch node data → assemble graph → connect fund trees. Factory methods configure different pipelines: default (full metrics), lightweight (structure only), CRM entity (no aggregated LP node, adds investor root).

**NodeFetcherService** — dispatches identifiers to type-specific fetchers: `FundNodeFetcher`, `FundPartnersNodeFetcher`, `PortfolioNodeFetcher`, `GPEntityNodeFetcher`, `IndividualPortfolioNodeFetcher`. Batch-fetches by type to avoid N+1 queries.

## Permission Model

Three-layer defense:
1. **View layer** — `IsFirmMember | IsStaff` (door lock)
2. **Topology layer** — `InvestedInRelationshipGraph` filters to permitted fund UUIDs
3. **IDOR defense** — `FundService.get_fund_id_to_firm_id_map` verifies entity-firm ownership

Fund-level gate: `view_investments` permission. Hard prune — unpermitted funds and entire subtrees disappear (no placeholders).

Permission flow: views pass `set[UUID]` of permitted fund UUIDs. `None` = staff/no filter, `set()` = no permissions (empty graph).

## Three-State Metric Semantics

Metrics use three states: `Decimal` = real value, `None` = couldn't calculate, **absent key** = not permitted. This matters for carry gating — `MetricsOverTime.filtered_by_keys()` strips keys from unpermitted funds rather than zeroing them. Aggregation via `_add_dicts()` unions keys, so root metrics naturally exclude hidden values.

## Key Abstractions

| Abstraction | File | Purpose |
|-------------|------|---------|
| `InvestedInRelationshipGraph` | `invested_in_relationship_graph.py` | Fund topology + permission filtering |
| `GraphBuilder` | `graph_builder.py` | Graph assembly with factory configs |
| `NodeFetcherService` | `services/node_fetcher_service.py` | Type-dispatched batch node fetching |
| `CrmEntityGraphBuilder` | `graph_builder.py` | Composition wrapper for investor-rooted views |
| `NAVMetrics` | `domain.py` | NAV with component breakdown, `__add__` derives ending_nav from components |
| `MetricsOverTime` | `domain.py` | Point-in-time metrics with start/end/change snapshots |
| `DefaultPartnerMetricsHandler` | `services/node_fetcher_service.py` | Partner metrics + carry gating |

## Node Types and IDs

| Type | ID Format | Notes |
|------|-----------|-------|
| `fund` | `{fund_uuid}` | |
| `fund_partners` | `{fund_uuid}_all_partners` | Excluded in CRM entity views |
| `portfolio` | `{fund_uuid}_portfolio` | |
| `gp_entity` | `{fund_uuid}_{gp_entity_uuid}` | Composite to prevent cross-contamination |
| `individual_portfolio` | `{crm_entity_uuid}` | CRM entity views only |

## Gotchas and Footguns

- **GP Entity traversal**: GP Members have Partner records in GP Entity funds, not main funds. Must follow management relationship via `ManagingEntityLinksService` to find connected main funds.
- **Intra-firm investment filtering**: When Fund A invests in Fund B, the Partner record is excluded from `fund_partners` (shown as fund→fund edge instead). Forgetting this creates duplicate representations.
- **Lightweight mode**: Returns structure without metrics. Root `individual_portfolio` node always included (structural, not metric). Frontend fetches metrics incrementally after initial load.
- **NAV aggregation**: `NAVMetrics.__add__()` derives `ending_nav` from component sums. Don't add pre-calculated ending_nav directly.
- **Sharing dates**: Use `information_sharing_date` on `PartnerAccountMetricsService`, not `to_date`.

## Current State (updated 2026-02-17)

MVP targeting week of Feb 17, feature-flagged via Flipper + carta_id. Key open PRs tracked in the entity-map project README.

## For Deeper Context

Read these from `~/Projects/coauthored/entity-map/`:

- **Architecture**: `20260211__guide__architecture-onboarding.md` — full pipeline walkthrough with code references
- **Background**: `20260206__guide__background-context.md` — product vision, business case, personas
- **Permissions**: `20260213__design__fund-level-permissions.md` — fund-level permission design
- **Carried interest**: `20260216__design__carried-interest-on-entity-map.md` — carry implementation
- **Decision log**: `~/Projects/coauthored/reference/decisions.md` — all architectural decisions with rationale

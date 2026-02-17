# Decision Log

Architectural decisions made during product development. Append-only — newest at the bottom.

---

### 2026-01-26 — GP entity traversal follows management relationships

**Context:** GP Members have Partner records in GP Entity funds, not directly in the main funds they want to see on the entity map.
**Decision:** Follow GP Entity → Main Fund management relationships using `ManagingEntityLinksService`, then traverse connected fund subgraphs. Non-GP-Entity funds included directly.
**Rationale:** Matches actual legal/investment structure. Reuses existing `get_funds_from_managing_entity()`. Rejected showing only GP Entity funds (unhelpful) and inferring main funds from heuristics (fragile).
**Project:** entity-map

### 2026-01-26 — Build CRM entity graphs per-firm then merge

**Context:** A CRM entity may have positions across multiple firms. Need a strategy for multi-firm graph construction.
**Decision:** Build per-firm subgraphs via `build_for_firm()`, filter each to relevant funds via `filtered_to_fund_subgraph()`, then merge.
**Rationale:** Reuses proven firm graph infrastructure. Each subgraph respects that firm's relationship topology. Rejected building a cross-firm graph from scratch (expensive, novel code) and showing only the primary firm (incomplete).
**Project:** entity-map

### 2026-01-28 — CRM entity view permissions: simple entry gate, defer data filtering

**Context:** CRM entity view spans multiple funds across potentially multiple firms. How to handle permissions?
**Decision:** `IsFirmMember | IsStaff` at view layer with IDOR validation. Data filtering deferred to service layer as future work.
**Rationale:** Separates "can you enter?" from "what can you see?" Simple for v1 where no sensitive financial data is shown. Naturally extends to fund-level filtering when metrics land. Rejected a new "CRM entity ownership" model (orthogonal to existing permissions) and immediate fund-level filtering (overkill for structural-only v1).
**Project:** entity-map

### 2026-02-03 — Separate PortfolioEntry.tsx for CRM entity views

**Context:** Entity map `Entry.tsx` required firm metadata from init endpoint, causing failures when embedding in Partner Dashboard.
**Decision:** Create dedicated `PortfolioEntry.tsx` exposed via Module Federation as `./PortfolioApp`.
**Rationale:** CRM entity view fetches its own data via `useGetCrmEntityMap`, doesn't need firm metadata. Separate entry points avoid conditional logic and unnecessary API calls. Rejected reusing Entry with conditionals (fragile) and making firm context optional (audit burden).
**Project:** entity-map

### 2026-02-05 — Node type name: `individual_portfolio`

**Context:** Need a node type to represent the investor at the root of CRM entity views.
**Decision:** Use `individual_portfolio` as the node type name.
**Rationale:** Aligns with Partner Dashboard naming. Distinct from fund `portfolio` type. Rejected `investor` (too generic), `crm_entity` (implementation detail leaking into UX), `person` (some entities are trusts/LLCs).
**Project:** entity-map

### 2026-02-05 — Separate CrmEntityGraphBuilder via composition

**Context:** CRM entity-specific graph building logic needs a home. Should it modify the shared GraphBuilder?
**Decision:** Create `CrmEntityGraphBuilder` that composes `GraphBuilder`. Shared builder unchanged.
**Rationale:** Preserves existing behavior for firm/fund/journal views. individual_portfolio node only appears in CRM entity API. Rejected modifying GraphBuilder (view-specific pollution) and putting logic in the service layer (wrong abstraction level).
**Project:** entity-map

### 2026-02-13 — `view_investments` as single permission gate for fund visibility

**Context:** CRM entity view needs fund-level permission filtering. GP users typically lack some view permissions.
**Decision:** Use `view_investments` as the single permission gate. Funds without this permission are hard-pruned — entire subtree disappears.
**Rationale:** Entity map shows investment structure, so `view_investments` is the natural semantic fit. Single-permission check is the most permissive reasonable gate. Hard prune (vs. placeholder) prevents leaking structural information about unpermitted funds. Rejected requiring all 5 view permissions (too restrictive for most GPs) and per-permission filtering (unnecessary complexity for v1).
**Project:** entity-map

### 2026-02-13 — Permission filtering at InvestedInRelationshipGraph level

**Context:** Where in the pipeline should fund permission filtering occur?
**Decision:** Filter at `InvestedInRelationshipGraph` before subgraph traversal. GraphBuilder and NodeFetcherService never see unpermitted funds.
**Rationale:** Permissions are a topology constraint, not a presentation concern. Early filtering means downstream code operates on clean data without permission awareness. Rejected post-fetch filtering (wastes expensive data fetching on invisible funds).
**Project:** entity-map

### 2026-02-13 — Pass `set[UUID]` of permitted fund UUIDs, `None` means no filtering

**Context:** How should permission information flow from view to graph builder?
**Decision:** Pass `set[UUID]` of permitted fund UUIDs. `None` means no filtering (staff users).
**Rationale:** Simple data type, builder doesn't need to know about users or permissions. Clear semantics: `None` = staff, `set()` = no permissions (empty graph). Rejected passing user object (couples builder to auth) and passing permission checker (couples builder to permission system).
**Project:** entity-map

### 2026-02-13 — Aggregate only visible funds in root node metrics

**Context:** Individual portfolio root node aggregates metrics from multiple funds. Include unpermitted funds?
**Decision:** Aggregate visible funds only. Root metrics must match partner_portfolio summary/entity-list API numbers.
**Rationale:** Including unpermitted funds leaks financial information. Must be consistent with other Partner Dashboard APIs. Rejected "aggregate all but hide details" (still leaks total exposure).
**Project:** entity-map

### 2026-02-16 — Sharing dates use `information_sharing_date`, not `to_date`

**Context:** Which date field should control point-in-time for partner metrics?
**Decision:** Use `information_sharing_date` on `PartnerAccountMetricsService`.
**Rationale:** `information_sharing_date` reflects when data was shared with the partner, which is the correct business concept for partner-facing views.
**Project:** entity-map

### 2026-02-16 — NAVMetrics.__add__() derives ending_nav from component sums

**Context:** How should `ending_nav` be calculated when aggregating multiple fund metrics?
**Decision:** Derive `ending_nav` from component sums rather than adding pre-calculated ending_nav values.
**Rationale:** Component-level addition is numerically correct. Pre-calculated ending_nav values from different funds may use different calculation methods, making direct addition meaningless.
**Project:** entity-map

### 2026-02-16 — Carried interest flows through NAV_COMPONENT_METRICS with three-state key semantics

**Context:** How should carried interest flow through the metrics pipeline and handle per-fund visibility gating?
**Decision:** Carry flows through `NAV_COMPONENT_METRICS`. Gate strips the key entirely from unpermitted funds. Three states: `Decimal` = value, `None` = couldn't calculate, absent key = not permitted.
**Rationale:** Absent key (vs. zeroing) provides unambiguous permission signal. Aggregation via `MetricsOverTime._add_dicts()` unions keys, so root node carry naturally reflects only permitted funds. Adding carry to `INCLUDED_METRICS` costs zero additional DB queries (partner transactions dataframe already loaded). Rejected zeroing hidden funds (false data) and always including the key (loses permission signal).
**Project:** entity-map

### 2026-02-16 — Carry gating centralized in DefaultPartnerMetricsHandler

**Context:** Where should per-fund carry visibility gating be applied?
**Decision:** In `DefaultPartnerMetricsHandler.get_partner_metadata_for_funds()` — batch-check `show_carry_metrics_by_fund_ids()`, then strip carry key from hidden-carry funds using `MetricsOverTime.filtered_by_keys()`.
**Rationale:** Centralizes gating in one place. Batch check is efficient (single query). Happens after metric computation but before aggregation, so root metrics naturally exclude hidden carry. Rejected gating at fetch time (complex per-fund metric tracking) and gating at view layer (service layer owns business logic).
**Project:** entity-map

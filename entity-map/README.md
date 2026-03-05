# entity-map

Design documents, architecture analysis, and reference material for the Portfolio Entity Map feature in fund-admin. Reorganized post-R1 release (2026-03-05).

## Current Reference

### Architecture & Onboarding
- [Architecture onboarding](20260211__guide__architecture-onboarding.md) — five-stage pipeline, all four view modes
- [Entity map explainer](20260213__guide__entity-map-explainer.md) — data models, node types, permissions (best first-read)
- [Background context](20260206__guide__background-context.md) — product vision, fund structure, Carta business context
- [Portfolio entry architecture](20260203__design__portfolio-entry-architecture.md) — why CRM entity views use a separate entry point

### Data Flow & Metrics
- [Metrics data flow](20260222__guide__metrics-data-flow.md) — carry, NAV, distributions from DB to API response
- [Node fetchers and builders](20260222__guide__node-fetchers-and-builders.md) — strategy pattern, `INodeTypeFetcher`, registry dispatch
- [Generic NAV components display](20260218__design__generic-nav-components-display.md) — frontend `displayNavComponents` architecture

### Permissions
- [Portfolio association and permissions](20260225__guide__portfolio-association-and-permissions.md) — user-to-portfolio chain, two permission layers, final intersection
- [CRM entity portfolio identity proof](20260205__investigation__crm-entity-portfolio-identity-proof.md) — `crm_entity_id` = `portfolio_uuid` invariant

### Carry & Cross-System
- [Carry and cross-system architecture](20260303__investigation__carry-and-cross-system-architecture.md) — carry discrepancy root cause, carry gate, fund-admin <-> carta-web bridge, debugging checklist

### Investigations
- [Graph building inversion bug](20260225__investigation__graph-building-inversion-bug.md) — why non-staff GPs saw empty entity maps
- [Portfolio node unification](20260209__investigation__portfolio-node-unification.md) — why `portfolio` and `individual_portfolio` stay separate

### Developer Tools
- [DevApp debugger design](20260204__design__devapp-debugger.md) — local entity map visualizer
- [Debugger guide](20260204__guide__debugger.md) — how to use the debugger

### Active Artifacts
- [Seed script](20260303__guide__seed-dominic-toretto.py) — Dominic Toretto LP test data
- [R1 testing guide](20260304__test__r1-testing-session-guide.md) — manual test plan for R1 pre-release

### Future Work
- [Graph building architecture fix](20260225__plan__graph-building-architecture-fix.md) — Option B root-outward traversal (deferred)

## Pull Requests

| PR | Repo | Description | Docs |
|----|------|-------------|------|
| #50962 | fund-admin | Multi-fund root edges | [architecture onboarding](20260211__guide__architecture-onboarding.md) |
| #50989 | fund-admin | Factory classmethods refactor | [node fetchers guide](20260222__guide__node-fetchers-and-builders.md) |
| #51129 | fund-admin | Aggregate root metrics | [metrics data flow](20260222__guide__metrics-data-flow.md) |
| #51154 | fund-admin | Per-fund sharing dates | [carry investigation](20260303__investigation__carry-and-cross-system-architecture.md) |
| #51165 | fund-admin | Fund-level permissions | [permissions guide](20260225__guide__portfolio-association-and-permissions.md) |
| #19928 | carta-frontend-platform | Strip firm-admin UI from GP view | [portfolio entry architecture](20260203__design__portfolio-entry-architecture.md) |
| #52234 | fund-admin | Carry gate on entity map | [carry investigation](20260303__investigation__carry-and-cross-system-architecture.md) |

## Archive

Historical documents (superseded designs, completed plans, point-in-time status updates) are in [`archive/`](archive/). They're preserved in git history and accessible for context on how the architecture evolved, but no longer represent current state.

## Project Status

Post-R1 status as of Feb 10: [project status](20260210__status__project.md) (best architecture snapshot with learnings from code review).

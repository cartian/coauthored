---
date: 2026-02-03
description: Status update on Entity Map CRM entity integration changes
repository: fund-admin
tags: [entity-map, crm, partner-dashboard, idor, security]
---

# Entity Map CRM Integration - Status Update

## Summary

Changes made to the Entity Map CRM entity view since Feb 2 afternoon, addressing PR feedback and enabling the Partner Dashboard integration.

## Key Changes

### New Feature: Firmless CRM Entity Endpoint

Added a new endpoint that allows fetching the entity graph without requiring `firm_uuid`:

```
GET /entity-atlas/crm-entity/{crm_entity_uuid}/
```

This is critical for the Partner Dashboard integration where we only have `portfolioUuid` (which equals `crmEntityId`). The endpoint derives `firm_uuid` from the CRM entity's partner relationships.

### Security Fixes

1. **IDOR Vulnerability Fix** - Changed validation to use `PartnerService.list_domain_objects(crm_entity_ids=[...], firm_ids=[...])` instead of direct model queries

2. **Defense-in-Depth Verification** - Added explicit post-fetch verification using `FundService.get_fund_id_to_firm_id_map` to ensure partners belong to funds in the specified firm, not relying solely on query filters

### Bug Fixes

- Fixed `get_fund` -> `get_by_fund_id` method name mismatch that caused 500 errors
- Fixed unit tests to mock `PartnerService` instead of `CRMEntityService` (tests were validating non-existent code paths)

### Code Quality

- Consolidated duplicate TODO(GPE-215) comments - main comment in `invested_in_relationship_graph.py`, reference in `graph_builder.py`
- Regenerated API schema to include new endpoint

## Commits (Feb 2-3)

| Date | Commit | Description |
|------|--------|-------------|
| Feb 3 | `2215cffb3a0` | Consolidate duplicate TODO comment |
| Feb 3 | `8060de9c53c` | Regenerate API schema for CRM entity endpoint |
| Feb 3 | `b5fac1affa7` | Add defense-in-depth IDOR verification |
| Feb 3 | `d92fd1cf3fb` | Fix FundService method name |
| Feb 3 | `f6bf8b5540d` | Fix test mocks (PartnerService not CRMEntityService) |
| Feb 2 | `e4bdfce0378` | Allow CRM entity graph lookup without firm_uuid |
| Feb 2 | `4969fbbce95` | Fix IDOR vulnerability in CRM entity validation |
| Feb 2 | `38f7bc714cc` | Update unit test mock to match refactored service |

## Testing

Both endpoints verified working locally:

```bash
# With firmUuid
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/firm/{firm_uuid}/entity-atlas/crm-entity/{crm_entity_uuid}/?lightweight=true"

# Without firmUuid (new)
curl -H "x-carta-user-id: 25" \
  "http://localhost:9000/entity-atlas/crm-entity/{crm_entity_uuid}/?lightweight=true"
```

## Remaining Work

- **GP Entity Query Duplication** - Tracked in TODO(GPE-215). `ManagingEntityLinksService` is called in both `InvestedInRelationshipGraphBuilder` and `GraphBuilder`. Future refactor should have the graph builder return GP entities as part of the graph structure.

## Frontend Integration Note

`portfolioUuid` and `crmEntityId` are the same UUID - they're different names for the same concept:
- `portfolioUuid` - investor/frontend perspective
- `crmEntityId` - backend/CRM system perspective

The frontend can pass `portfolioUuid` directly to the new endpoint.

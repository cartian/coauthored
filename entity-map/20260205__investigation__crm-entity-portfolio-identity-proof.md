---
date: 2026-02-05
description: Onboarding document proving that crm_entity_id and portfolio_uuid are the same UUID, with architectural context and future possibilities
repository: fund-admin
tags: [entity-map, crm-entity, portfolio, onboarding, architecture]
---

# The Great Naming Mystery: Why `crm_entity_id` = `portfolio_uuid`

Welcome! If you've been working with the Entity Map and wondered why we sometimes call something a "portfolio" and sometimes a "CRM entity," you're not alone. This document proves they're the same thing, explains why, and shows what this opens up for us.

## The Short Answer

**`crm_entity_id` and `portfolio_uuid` are the same UUID.**

They're different names for the same concept, used in different contexts:

| Name | Domain | Who Uses It |
|------|--------|-------------|
| `portfolio_uuid` / `portfolio_id` | Frontend, investor-facing | Partner Dashboard, investor views |
| `crm_entity_id` / `crmEntityId` | Backend, CRM system | Entity Atlas APIs, internal services |

Think of it like how "William" and "Bill" refer to the same person—the UUID identifies the entity regardless of what we call it.

---

## The Proof

### Evidence 1: Direct Code Assignment

In `fund_admin/entity_map/kyc/service.py`, we see `entity_id` directly assigned to `portfolio_id`:

```python
for partner_uuid_str, partner_metadata in partner_metadata_dict.items():
    entity_id = partner_metadata.entity_id
    if entity_id:
        entity_id_to_partner_uuid[entity_id] = partner_uuid_str
        portfolio_by_fund_ids.append(
            PortfolioByFund(
                fund_carta_id=fund.carta_id,
                portfolio_id=entity_id,  # <-- Same UUID, different name
            )
        )
```

The `entity_id` (which comes from a CRM Entity) is passed directly as `portfolio_id` to the KYC service. No transformation, no lookup—it's the same value.

### Evidence 2: The Data Model Chain

Let's trace the relationship through the models:

```
┌─────────────────────────────────────────────────────────────┐
│                       CRMEntity                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ id: UUID  ← This is the crm_entity_id               │    │
│  │ represents: a legal entity (person, trust, LLC)     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ ForeignKey (entity_id)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        Partner                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ entity_id: FK → CRMEntity.id                        │    │
│  │ represents: an investment position in a fund        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

When the frontend requests a "portfolio view," it's asking: *"Show me all investment positions (Partners) for this legal entity (CRMEntity)."*

The `portfolio_uuid` in that request **is** the `CRMEntity.id`.

### Evidence 3: The URL Convention

From the original carta_web integration:

```
Assumption: portfolio_id = CRM Entity UUID
Rationale: Existing carta_web convention; reuse this pattern
```

The frontend already uses `portfolio_id` in URLs to identify investors. This convention was established because, from the investor's perspective, their CRM Entity *is* their portfolio—it's the root of all their investments.

### Evidence 4: Permission Validation

The `CanEditPortfolio` permission class validates user access to a CRM Entity using `portfolio_id`:

```python
# From firm_permissions.py
# The permission class takes portfolio_id and validates access to... a CRM Entity
```

The system treats these as interchangeable because they are.

---

## Why Two Names? Historical Context

### The Investor Perspective ("Portfolio")

When building investor-facing features, product teams think in terms of **portfolios**:
- "Jane's portfolio includes investments in Fund A, Fund B, and Fund C"
- "Show me the portfolio dashboard"
- "What's the total value across this portfolio?"

The word "portfolio" is investor-friendly and intuitive.

### The Backend Perspective ("CRM Entity")

When engineers built the CRM system, they thought in terms of **entities**:
- "A CRM Entity represents any legal entity that can own things"
- "Entities can be people, trusts, LLCs, corporations"
- "Each entity has a unique identifier in our CRM"

The term "CRM Entity" is precise and reflects the data model.

### The Collision

Both teams were right! They were describing the same thing:
- **Portfolio** = "all investments belonging to one investor"
- **CRM Entity** = "the legal identity that owns those investments"

Same concept, different mental models. The UUID bridges both worlds.

---

## The Entity Map Insight

Here's where it gets exciting. The Entity Map uses the CRM Entity as the **root node** of an investment graph:

```
                    ┌──────────────────┐
                    │   CRM Entity     │
                    │   (Jane Smith)   │
                    │                  │
                    │  id: abc-123...  │  ← This UUID is both crm_entity_id
                    │                  │    AND portfolio_uuid
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Partner  │  │ Partner  │  │ Partner  │
        │ in Fund A│  │ in Fund B│  │ in Fund C│
        └──────────┘  └──────────┘  └──────────┘
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │  Fund A  │  │  Fund B  │  │  Fund C  │
        │          │  │          │  │          │
        │  ... has │  │  ... has │  │  ... has │
        │ portfolio│  │ portfolio│  │ portfolio│
        │ companies│  │ companies│  │ companies│
        └──────────┘  └──────────┘  └──────────┘
```

The CRM Entity is the natural root because it answers the question: **"For this investor, show me everything they're connected to."**

---

## What This Opens Up

### 1. Unified Entry Points

Because `portfolio_uuid` = `crm_entity_id`, we can build features that work from either direction:
- Start from Partner Dashboard (has `portfolio_uuid`) → Get full entity graph
- Start from CRM system (has `crm_entity_id`) → Get portfolio view

No translation layer needed. Same UUID, same result.

### 2. Cross-Fund Visibility

An investor's CRM Entity connects to *all* their Partners across *all* funds in a firm. The Entity Map can show:
- "You're invested in 7 funds through this identity"
- "These 3 funds share common portfolio companies"
- "Your aggregate exposure to Company X across all funds is $2.3M"

### 3. Fund-to-Fund Investment Graphs

When Fund A invests in Fund B (fund-to-fund), the investing fund's UUID serves as the `entity_id` on the Partner record. This means:
- We can trace capital flows: LP → Fund A → Fund B → Portfolio Company
- The Entity Map can visualize multi-level fund structures
- The same graph traversal works whether the "investor" is a person or a fund

### 4. KYC and Compliance Aggregation

KYC data lives at the CRM Entity level. Because `portfolio_uuid` = `crm_entity_id`:
- Compliance status aggregates naturally across all investment positions
- "This investor's KYC is complete" means it's complete for all their Partners
- No need to duplicate KYC per fund—it's entity-level by design

### 5. Future: Investor-Centric Everything

The CRM Entity as the root enables investor-centric features we haven't built yet:
- **Consolidated K-1s**: "Here's your tax documents across all funds"
- **Total return analysis**: "Your overall performance across the firm"
- **Communication preferences**: "How this investor wants to be contacted"
- **Document vault**: "All documents for this investor, organized by fund"

---

## Key Takeaway

When you see `crm_entity_id` or `portfolio_uuid` in the code, remember:

> **They're the same UUID, representing the same legal entity, viewed from different perspectives.**

The CRM Entity is the investor identity. The portfolio is what that identity owns. Same thing, different lens.

This architectural insight—that the CRM Entity is the natural root of an investor's world—is what makes the Entity Map powerful. We're not just showing fund structures; we're showing *investment relationships from the investor's point of view*.

---

## Quick Reference

| When you see... | It means... | Context |
|-----------------|-------------|---------|
| `crm_entity_id` | UUID of a legal entity | Backend services, Entity Atlas |
| `portfolio_uuid` | UUID of a legal entity | Frontend, Partner Dashboard |
| `portfolio_id` | UUID of a legal entity | URL parameters, API requests |
| `entity_id` on Partner | UUID of the CRM Entity (or investing Fund) | Partner model foreign key |

They're all pointing to the same thing: the unique identifier of whoever (or whatever fund) is doing the investing.

---

*Questions? The Entity Map codebase lives in `fund_admin/entity_map/`. Start with `crm_entity_graph_service.py` for the graph construction logic.*

## Related

- [20260205__design__individual-portfolio-node.md](20260205__design__individual-portfolio-node.md) — Design document that uses the crm_entity_id/portfolio_uuid equivalence established by this proof
- [20260206__guide__background-context.md](20260206__guide__background-context.md) — Background guide explaining the broader entity map architecture and investor-centric view concepts

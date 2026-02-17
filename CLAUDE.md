# Coauthored Repository — Claude Instructions

This is a personal documentation repository for LLM co-authored artifacts: design documents, architectural analyses, session summaries, learning notes, and technical write-ups.

## When to Write Here

Documents are saved here (not in the source repo) when they represent **notes, write-ups, analyses, or recorded thinking** — anything that is not production code or test code. This includes:

- Technical design documents
- Architecture decision records
- Session summaries and investigation logs
- Learning notes and concept explainers
- Manual test plans and results
- Debugging narratives

## Directory Structure

**NEVER place document files in the repository root.** Every document must go in a subdirectory. The only files that belong in root are `README.md`, `CLAUDE.md`, and dotfiles.

Before writing a file, check existing subdirectories with `ls` and place the document in the correct one. If no matching directory exists, create one.

### Current directories

| Directory | Purpose | Examples |
|-----------|---------|---------|
| `entity-map/` | Entity Map feature work in fund-admin | Design docs, graph architecture analysis, CRM entity views |
| `reference/` | General technical reference material and cross-cutting knowledge | Permissions overviews, proxy architecture notes, security guides, decision log |
| `private/` | Sensitive or personal notes | (not committed to shared repos) |
| `transcripts/` | Notable conversation moments — debugging breakthroughs, design debates, learning checkpoints | Atomic excerpts of valuable reasoning, not full sessions |

### Adding New Directories

When working on a new project area that doesn't fit existing directories, create a new subdirectory named after the project or domain (e.g., `capital-calls/`, `tax-reporting/`, `frontend/`). Use kebab-case.

## File Naming Convention

Files use three segments separated by double underscores (`__`):

```
YYYYMMDD__type__description-in-kebab-case.md
```

### Document types

| Type | Use for |
|------|---------|
| `design` | Architecture decisions, technical designs, feature designs |
| `plan` | Implementation plans, execution plans, upcoming work |
| `status` | Project updates, leadership summaries, MVP status |
| `investigation` | Debugging narratives, root cause analysis, research |
| `guide` | Onboarding docs, how-tos, explainers, reference guides |
| `walkthrough` | Code path walkthroughs, annotated traces |
| `test` | Manual test plans and results |
| `session` | Session summaries |
| `review` | Code review notes and feedback |
| `transcript` | Notable conversation moments — debugging breakthroughs, design debates, learning checkpoints |

### Examples

- `20260209__investigation__portfolio-node-unification.md`
- `20260128__design__crm-entity-permissions.md`
- `20260211__status__leadership-notes.md`
- `20260205__plan__crm-graph-refinements.md`

### Filtering by type

```bash
ls *__design__*     # all designs in current directory
ls *__status__*     # all status updates
```

## Required Frontmatter

Every document must include YAML frontmatter:

```yaml
---
date: YYYY-MM-DD
description: Brief summary of the document's purpose
repository: Name of the related project/repo (if applicable)
tags: [relevant, tags, here]
---
```

## Choosing the Right Directory

Use this decision guide:

1. **Is it about a specific feature or project area?** → Use or create a project directory (e.g., `entity-map/`, `capital-calls/`)
2. **Is it general reference material, a guide, or cross-cutting knowledge?** → `reference/`
3. **Is it sensitive or personal?** → `private/`

When in doubt, prefer a project-specific directory over `learning/`. Project directories provide better context grouping when revisiting past decisions.

## Cross-Referencing Conventions

### Backlinks (`## Related` sections)

Every document should have a `## Related` section at the bottom with relative markdown links to related docs and PRs. Add these when relationships are obvious (design ↔ plan, investigation → design, doc → PR). Don't force it on docs that stand alone.

```markdown
## Related
- [Fund-level permissions design](20260213__design__fund-level-permissions.md) — this plan implements that design
- [PR #51165](https://github.com/pccarta/fund-admin/pull/51165) — implementation
```

### Decision Log (`reference/decisions.md`)

Append-only file tracking architectural decisions across all projects. Add an entry when making a non-trivial design choice — especially when alternatives were considered and rejected. Format:

```markdown
### YYYY-MM-DD — Short title

**Context:** 1-2 sentences on the problem.
**Decision:** What we decided.
**Rationale:** Why, including what we rejected.
**Project:** entity-map | fund-admin | etc.
```

### PR Archaeology (project README tables)

Project READMEs include a `## Pull Requests` table mapping PR numbers to repos, descriptions, and links to related docs. Update when PRs ship.

### Transcripts (`transcripts/`)

Save notable conversation moments as standalone files in `transcripts/`. One file per moment — a debugging breakthrough, a design debate, a learning checkpoint where the reasoning process has value beyond the outcome. Standard naming convention with `transcript` type. Frontmatter includes `source_session` (date of conversation) and `decisions` (links to decision log entries produced).

### Domain Skills (`.claude/skills/`)

Curated domain context files that Claude Code loads on invocation. Each skill summarizes architecture, key abstractions, permission models, gotchas, and includes pointers to deeper docs. Update periodically as features evolve.

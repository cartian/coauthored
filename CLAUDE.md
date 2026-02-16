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
| `reference/` | General technical reference material and cross-cutting knowledge | Permissions overviews, proxy architecture notes, security guides |
| `private/` | Sensitive or personal notes | (not committed to shared repos) |

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

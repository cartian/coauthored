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
| `learning/` | General technical learning and reference material | Permissions overviews, proxy architecture notes, security guides |
| `private/` | Sensitive or personal notes | (not committed to shared repos) |

### Adding New Directories

When working on a new project area that doesn't fit existing directories, create a new subdirectory named after the project or domain (e.g., `capital-calls/`, `tax-reporting/`, `frontend/`). Use kebab-case.

## File Naming Convention

All files must be prefixed with the date:

```
YYYYMMDD-descriptive-name.md
```

Examples:
- `20260209-portfolio-node-unification-analysis.md`
- `20260128-crm-entity-permissions-design.md`
- `20260203-debugging-cross-service-404-fund-admin-networking.md`

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
2. **Is it general learning, a reference guide, or cross-cutting knowledge?** → `learning/`
3. **Is it sensitive or personal?** → `private/`

When in doubt, prefer a project-specific directory over `learning/`. Project directories provide better context grouping when revisiting past decisions.

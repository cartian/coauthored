---
date: 2026-02-17
description: Design for five organizational improvements to the coauthored repo
repository: coauthored
tags: [meta, organization, tooling]
---

# Coauthored Repo Organization Improvements

## Motivation

The repo has solid naming conventions and project-based directories, but lacks cross-referencing, accumulated decision history, and tooling to reduce session startup cost. Five improvements address this.

## 1. Backlinks (`## Related` sections)

Every doc gets a `## Related` section at the bottom with relative markdown links to related docs and PRs. Retrofitted where relationships are obvious (designs ↔ plans, investigations → designs). Docs that stand alone don't need one.

## 2. Decision Log (`reference/decisions.md`)

Single append-only file. Each entry has date, short title, context, decision, rationale, and project tag. Seeded from breadcrumb "Key decisions" sections and decisions buried in existing design docs.

## 3. PR Archaeology (project README tables)

Project READMEs get a `## Pull Requests` table mapping PR numbers to repos, descriptions, and links to related docs. Maintained as PRs ship.

## 4. Transcripts (`transcripts/`)

New directory for notable conversation moments — debugging breakthroughs, design debates, learning checkpoints. One file per moment, standard naming convention. Frontmatter includes `source_session` date and `decisions` links.

## 5. Entity-Map Domain Skill

Claude Code skill at `.claude/skills/entity-map-context.md` invoked via `/entity-map`. Static curated context (architecture, permission model, key abstractions, gotchas) with pointers to deeper docs. Updated periodically as the feature evolves.

## CLAUDE.md Updates

Document all new conventions so future sessions follow them automatically.

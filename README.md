# coauthored
LLM co-authored artifacts / Notes on product development, architecture, and engineering

![kermit going off](https://media0.giphy.com/media/v1.Y2lkPTc5MGI3NjExNnk5MDB1bWdvaTE2ejcxbjYxbWc4cjQzdjF4bmsxbmZtNGlrcTdjZiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/XIqCQx02E1U9W/giphy.gif)

---

## Structure

```
entity-map/        # Entity Map feature — designs, plans, investigations, status
reference/         # Cross-cutting knowledge — permissions, proxy architecture, security
private/           # Not committed
transcripts/       # Notable conversation moments worth keeping
breadcrumbs/       # Session continuity — where things stand, what's next
.claude/skills/    # Domain context skills for Claude Code
```

Files follow `YYYYMMDD__type__description.md`. Types: `design`, `plan`, `status`, `investigation`, `guide`, `walkthrough`, `test`, `session`, `review`, `transcript`.

## How things connect

**Decision log** (`reference/decisions.md`) — append-only record of architectural decisions with context and rationale. The thing you'll actually search six months from now.

**Backlinks** — docs have a `## Related` section at the bottom linking to related designs, plans, investigations, and PRs. Not every doc needs one. The ones that stand alone, stand alone.

**PR tables** — project READMEs map PR numbers to the docs that produced them. Trace from "why did we build it this way" to "here's the PR."

**Transcripts** — one file per notable moment. A debugging session that cracked the problem. A design argument that clarified the tradeoff. Saved when the reasoning has value beyond the outcome.

## Tooling

**Domain skills** (`.claude/skills/`) are curated context documents that Claude Code loads on demand. Architecture, key abstractions, permission models, gotchas, and pointers to deeper docs. Faster than re-reading everything. `/entity-map` loads the entity map context.

**Breadcrumbs** (`breadcrumbs/`) are per-project session state. Overwritten each session. What shipped, what's in flight, what's next. Designed to be read by a future session that has zero context.


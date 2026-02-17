# Transcripts

Notable conversation moments preserved as standalone artifacts — debugging breakthroughs, design debates, learning checkpoint exchanges.

## What belongs here

A transcript is worth saving when the *reasoning process* has value beyond the outcome it produced. If the decision log captures *what* was decided, transcripts capture *how* you got there.

Examples:
- A back-and-forth that resolved a tricky architectural tradeoff
- A debugging session that revealed a non-obvious root cause
- A learning checkpoint where reasoning about failure modes clarified the design

## What doesn't belong here

- Routine file reading and editing
- Sessions where the outcome is fully captured by a design doc or decision log entry
- Anything where the final artifact tells the whole story

## Naming

```
YYYYMMDD__transcript__description-in-kebab-case.md
```

## Frontmatter

```yaml
---
date: YYYY-MM-DD
description: What this transcript captures
source_session: YYYY-MM-DD
decisions:
  - ../reference/decisions.md#YYYY-MM-DD — short title
tags: [relevant, tags]
---
```

`source_session` is the date of the original conversation. `decisions` links to decision log entries this transcript produced, if any.

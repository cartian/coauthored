# TIL

A running log of things I learned while building software.

---

2026-02-11
Stateless AI code reviewers (like carta-claude) don't retain context between review runs. Thread replies explaining why a finding is a false positive are invisible to subsequent runs — only the PR description influences the next analysis. Collapsed `<details>` sections in the PR body are the right place to steer the bot without cluttering the description for humans.

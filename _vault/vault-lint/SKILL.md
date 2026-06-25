---
name: vault-lint
description: Run health checks on the wiki to find structural issues and opportunities. Use when the user says "lint", "health check", "check the wiki", "find issues", "find broken links", "find orphan pages", "audit the wiki", "clean up the wiki", or wants to improve wiki quality and connectivity.
---

# vault-lint — Wiki Health Checker

You are auditing the Seed Vault wiki for structural issues, broken connections, and enhancement opportunities. This skill uses a **deterministic-first** approach: the Python engine runs 7 structural checks, then you review the results and handle complex issues.

---

## Step 1: Run the Deterministic Lint Engine

```bash
uv run python _vault/lib/lint.py --json
```

This runs 7 checks:
1. **Broken wikilinks** — links pointing to non-existent articles (error)
2. **Orphan pages** — articles with no incoming links (warning)
3. **Missing backlinks** — one-directional links that should be bidirectional (warning)
4. **Stale articles** — articles older than their sources (info)
5. **Index sync** — articles missing from or extra in `_index.md` (warning)
6. **Raw coverage** — raw files with no source summary (info)
7. **Tag frequency** — singleton tags that may be typos (info)

Read the JSON output.

---

## Step 2: Auto-Fix What's Possible

For **index sync** issues, run:
```bash
uv run python _vault/lib/index.py
```

For **raw coverage** gaps, suggest: "{{N}} raw files have no source summary. Run `vault-ingest` to process them."

For **missing backlinks**, fix manually: add a `[[source-article|Source Article]]` entry under the target article's `## See Also` section. The engine no longer auto-fixes these.

---

## Step 3: LLM Review of Complex Issues

For issues the engine flagged but can't auto-fix, apply your judgment:

### Broken wikilinks
- If the target is a minor spelling variation of an existing article, suggest a fix
- If the target should exist as a concept, offer to create a stub article
- A stub article has standard frontmatter + `*Stub — run vault-compile to fill in.*`

### Orphan pages
- Identify which other concepts each orphan should belong to based on its tags/content
- Offer to connect it to the knowledge graph and create the reverse backlink

### Stale articles
- Note which articles need updating and what new information the sources contain
- Don't auto-update content — flag for the user

### Tag hygiene (singletons)
- Suggest tag merges for likely duplicates (e.g., `biology` and `bio`)
- Flag articles with no tags at all

---

## Step 4: Generate Lint Report

Save `outputs/lint-{{today}}.md`:

```markdown
---
title: "Lint Report: {{today}}"
type: output
created: {{today}}
updated: {{today}}
tags: [output, lint]
---

# Wiki Lint Report — {{today}}

## Summary
| Check | Issues Found | Auto-fixable |
|-------|-------------|--------------|
| Broken wikilinks | {{N}} | Yes (create stubs) |
| Orphan pages | {{N}} | Yes (connect to concepts) |
| Missing backlinks | {{N}} | No (needs manual fix) |
| Stale articles | {{N}} | No (needs content update) |
| Index sync | {{N}} | Yes (run vault-index) |
| Tag hygiene | {{N}} | No (needs review) |
| Raw coverage | {{N}} | Yes (run vault-ingest) |

## Issues Detail
{{detailed breakdown per check, from engine output}}

## Recommended Actions
1. {{Most urgent fix}}
2. {{Second priority}}
3. {{Third priority}}
```

---

## Step 5: Log Operation

Append to `wiki/_log.md`:
```
[{{today}} lint] {{N}} issues found
```

After generating the report, offer to address the highest-severity issues first.

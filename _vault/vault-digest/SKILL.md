---
name: vault-digest
description: Generate a status briefing and summary of the wiki. Use when the user says "briefing", "status report", "what's in the wiki", "what do we have", "wiki summary", "overview of the vault", "what have we collected", "show me the state of the wiki", or wants a high-level orientation without asking a specific question. Fully deterministic — no LLM reasoning needed.
---

# vault-digest — Wiki Status Briefing

You are generating an orientation briefing of the Seed Vault wiki. This skill is **fully deterministic** — it runs the Python engine and presents the output.

---

## Step 1: Run the Digest Engine

```bash
uv run python _vault/lib/digest.py --markdown
```

This scans all wiki files, parses frontmatter, counts by type/status/tag, builds a link frequency map, finds hub nodes, orphans, knowledge gaps, and outputs a formatted markdown report.

---

## Step 2: Present the Results

Read the engine's output and present it to the user. The report includes:

- **Contents at a Glance**: Total articles by type and status
- **Recently Updated**: Articles modified in the last 7 days
- **Hub Nodes**: The 5 most-linked articles
- **Orphan Pages**: Articles with no incoming links
- **Tag Distribution**: Tag frequency across the wiki
- **Knowledge Gaps**: Raw files without summaries, singleton tags, concepts without hubs

---

## Step 3: Suggest Next Actions

Based on the digest output, suggest actionable next steps:

1. If there are unsummarized raw files → "Run `vault-ingest` to process {{N}} raw files"
2. If there are many drafts → "Run `vault-verify` to fact-check draft articles"
3. If there are orphan pages → "Run `vault-lint` to connect orphan pages to topic hubs"
4. If the index seems stale → "Run `vault-index` to rebuild"

---

## Step 4: Save if Requested

If the user wants to save the briefing:

Save to `outputs/digest-{{today}}.md` with frontmatter:
```yaml
---
title: "Wiki Digest: {{today}}"
type: output
created: {{today}}
tags: [output, digest]
---
```

Otherwise, deliver the briefing inline — no file needed.

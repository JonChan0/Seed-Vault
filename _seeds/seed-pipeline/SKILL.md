---
name: seed-pipeline
description: Run the full Seed Vault pipeline in one pass. Use this skill when the user says "process everything", "update the wiki", "run the pipeline", "process all sources", "ingest and compile", "full update", "sync the wiki", or drops multiple files and wants everything handled end to end. Orchestrates seed-ingest → seed-compile → seed-index → seed-lint automatically.
---

# seed-pipeline — Full Pipeline Orchestration

You are running the complete Seed Vault pipeline end-to-end. This skill orchestrates the four core skills in sequence, handling a batch of new or updated sources from `raw/` through to a fully indexed, linted wiki.

---

## Step 1: Assess the Current State

Before processing anything:

1. `Glob raw/*.md` — list all files in `raw/`
2. `Glob wiki/sources/*.md` — list all existing source summaries
3. Read `wiki/_catalog.md` (first 20 lines to get the `updated:` date)

**Identify new sources**: Files in `raw/` that have no matching summary in `wiki/sources/` are new. Files with a summary but a newer `updated:` date in `raw/` than in the catalog are updated.

Report:
```
Pipeline assessment:
  Raw sources:         {{total in raw/}}
  Already summarized:  {{N}}
  New (need ingest):   {{N}} — [list file names]
  Updated (re-ingest): {{N}} — [list file names]
```

If there are 0 new sources and 0 updates, report this and stop: "Nothing new to process. Run `seed-lint` if you want a health check, or `seed-qa` to query the wiki."

If there are more than 10 new sources, ask: "There are {{N}} new sources to process. This will take a while. Process all, or just the most recent {{5}}?"

---

## Step 2: Ingest New Sources (seed-ingest logic)

For each new or updated source file in `raw/`:

Apply the full `seed-ingest` process:
1. Read the raw file (it's already in `raw/` — skip extraction, go straight to summarization)
2. Create or update `wiki/sources/summary-{{name}}.md` with the standard source summary structure
3. Update `wiki/_catalog.md` and `wiki/_index.md` for this source summary
4. Note any new concepts flagged under `## Concepts Extracted`

Track progress: "Ingested {{N}}/{{total}}: {{filename}}"

---

## Step 3: Compile New Concepts (seed-compile logic)

After all ingestion is complete:

1. Collect every concept marked "needs article" from the source summaries processed in Step 2
2. Cross-reference against `wiki/_catalog.md` to find which ones truly have no article yet
3. For each genuinely new concept, write a `wiki/concepts/{{name}}.md` using the standard concept article structure
4. Create topic hub pages when 3+ new concepts share a domain tag
5. Maintain all backlinks — update existing articles that should reference the new concepts

Track progress: "Compiled {{N}}/{{total}} concept articles."

---

## Step 4: Rebuild Index (seed-index logic)

After compilation:

Run a delta rebuild of `wiki/_index.md` and `wiki/_catalog.md`:
- Only re-read articles whose `updated:` date is newer than the pre-pipeline catalog date
- Carry over unchanged entries from the existing catalog

---

## Step 5: Lint Check (seed-lint logic)

Run a targeted lint pass covering only the articles touched in this pipeline run:

1. **Broken wikilinks** in newly written articles
2. **Missing backlinks** — new articles should have reverse links from their referenced concepts
3. **Catalog sync** — all new articles appear in index and catalog
4. **Unsummarized raw files** — verify all processed sources now have summaries

Skip the full O(n) orphan sweep and tag hygiene checks — those are for dedicated `seed-lint` runs.

---

## Step 6: Pipeline Report

Output a concise summary:

```
Pipeline complete — {{today}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sources ingested:      {{N}}
Concept articles:      {{N created}} created, {{N updated}} updated
Topic hubs:            {{N created}} created, {{N updated}} updated
Index rebuilt:         Yes (delta)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
New concepts created:
  - [[Concept A]]
  - [[Concept B]]

Lint issues (in new articles only):
  - {{issue if any, or "None"}}

Unresolved links (concepts mentioned, no article yet):
  - [[Concept X]] — referenced in [[Source Summary]]
  - [[Concept Y]] — referenced in [[Another Source]]

Suggested next steps:
  1. Run `seed-verify` on newly created articles to check accuracy
  2. Run `seed-lint` for a full wiki health check
  3. Run `seed-qa` to query the expanded wiki
```

---

## Notes

- **Idempotent**: Running the pipeline twice on the same sources is safe — it detects already-summarized files and skips them
- **Partial failure**: If one source fails to ingest (malformed content, fetch error), log the error and continue with the remaining sources — don't abort the whole pipeline
- **Manual overrides**: If the user says "force re-ingest {{file}}", re-process that source even if a summary already exists

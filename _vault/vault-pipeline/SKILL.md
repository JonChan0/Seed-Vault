---
name: vault-pipeline
description: Run the full pipeline in one pass. Use when the user says "process everything", "update the wiki", "run the pipeline", "process all sources", "ingest and compile", "full update", "sync the wiki", or drops multiple files and wants everything handled end to end. Orchestrates vault-ingest → vault-compile → vault-index → vault-verify → vault-lint automatically.
---

# vault-pipeline — Full Pipeline Orchestration

You are running the complete Seed Vault pipeline end-to-end. This skill orchestrates the core skills in sequence, handling a batch of new or updated sources from `raw/` through to a fully indexed, verified, and linted wiki.

---

## Step 1: Assess the Current State (Deterministic)

Run the pipeline assessment engine:

```bash
uv run python _vault/lib/pipeline.py --json
```

This scans `raw/` and `wiki/sources/`, classifying files as new, updated, or unchanged. Read the JSON output to understand what needs processing.

If there are 0 new sources and 0 updates, report this and stop: "Nothing new to process. Run `vault-lint` if you want a health check, or `vault-qa` to query the wiki."

If there are more than 10 new sources, ask: "There are {{N}} new sources to process. This will take a while. Process all, or just the most recent 5?"

---

## Step 2: Convert Non-Markdown Files (Deterministic)

For each new file that `needs_conversion` (PDF, HTML, DOCX, etc.):

```bash
uv run python _vault/lib/convert.py "{{raw_filepath}}" raw/
```

This produces clean markdown in `raw/`. If conversion fails, fall back to Claude's native file reading capabilities.

---

## Step 3: Ingest New Sources (LLM — vault-ingest logic)

For each new or updated source file in `raw/`:

1. Read the raw file
2. Create or update `wiki/sources/summary-{{name}}.md` with the standard source summary structure
3. Note any new concepts flagged under `## Concepts Extracted`

Track progress: "Ingested {{N}}/{{total}}: {{filename}}"

---

## Step 4: Compile New Concepts (LLM — vault-compile logic)

After all ingestion is complete:

1. Collect every concept marked "needs article" from the source summaries processed in Step 3
2. Cross-reference against `wiki/_index.md` to find which ones truly have no article yet
3. For each genuinely new concept, write a `wiki/concepts/{{name}}.md` using the standard concept article structure
4. Maintain all backlinks — update existing articles that should reference the new concepts

Track progress: "Compiled {{N}}/{{total}} concept articles."

---

## Step 5: Rebuild Index (Deterministic)

Run the index engine. Pass `--no-cleanup` so mid-pipeline summaries that have not
yet been wired up to concept articles are not eagerly deleted as orphans:

```bash
uv run python _vault/lib/index.py --rebuild-qmd --no-cleanup
```

This regenerates `wiki/_index.md` and rebuilds the qmd search index.
Run `vault-lint` afterwards to handle orphaned-source cleanup at end-of-pipeline.

---

## Step 6: Verify New Articles (Clean-Context Subagent)

For each newly compiled concept article, run verification using a **clean-context subagent** to prevent confirmation bias:

### 6a: Run Deterministic Claim Extraction

```bash
uv run python _vault/lib/verify.py "{{article_path}}" --json
```

This extracts verifiable claims and matches them against raw sources.

### 6b: Launch Verification Subagent

For each article, launch a subagent with `Agent(subagent_type="general-purpose")` containing ONLY:
- The article content
- The verify.py JSON output (including the `source_warnings` list)
- The raw source file contents referenced by the article
- These instructions:

```
You are a fact-checker. You have NO prior context about this wiki or its creation.

Given:
- ARTICLE: [article content]
- SOURCE MATCH REPORT: [verify.py output]
- SOURCE WARNINGS: [source_warnings list from verify.py — may be empty]
- RAW SOURCES: [source files]

Tasks:
1. If SOURCE WARNINGS is non-empty, the source resolution was incomplete —
   note that vault-lint should be run for raw_coverage / broken_wikilinks issues
2. For each claim in the article, assess if the raw sources support it
3. Flag claims with no source support as UNSUPPORTED
4. Flag claims that contradict sources as CONTRADICTED
5. Rate overall confidence: HIGH / MEDIUM / LOW
6. Output a verification report in markdown
```

### 6c: Process Verification Results

Read the subagent's verification report. If any claims are CONTRADICTED:
- Fix the article to match the source
- Update `updated:` date

If confidence is LOW, add `status: draft` and a note about unverified claims.

---

## Step 7: Lint Check (Deterministic + LLM)

Run a targeted lint pass:

```bash
uv run python _vault/lib/lint.py --json
```

Review the output. For the articles touched in this pipeline run, check:
1. **Broken wikilinks** in newly written articles
2. **Missing backlinks** — new articles should have reverse links
3. **Index sync** — all new articles appear in the index

Fix missing backlinks manually: for each pair A→B where B lacks a link back to A, append `- [[a-stem|A Title]]` under B's `## See Also` section.

---

## Step 8: Log and Report

Append to `wiki/_log.md`:
```
[{{today}} pipeline] Ingested {{N}} sources, compiled {{N}} concepts, verified {{N}} articles
```

Output a concise summary:

```
Pipeline complete — {{today}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sources ingested:      {{N}}
Concept articles:      {{N created}} created, {{N updated}} updated
Index rebuilt:         Yes (+ qmd updated)
Verification:          {{N}} articles checked
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
New concepts created:
  - [[concept-a|Concept A]]
  - [[concept-b|Concept B]]

Verification issues:
  - {{issue if any, or "None — all claims supported"}}

Lint issues:
  - {{issue if any, or "None"}}

Suggested next steps:
  1. Review any verification warnings in newly created articles
  2. Run `vault-lint` for a full wiki health check
  3. Run `vault-qa` to query the expanded wiki
```

---

## Notes

- **Idempotent**: Running the pipeline twice on the same sources is safe — pipeline.py detects already-summarized files and skips them
- **Partial failure**: If one source fails to ingest, log the error and continue with the remaining sources — don't abort the whole pipeline
- **Manual overrides**: If the user says "force re-ingest {{file}}", re-process that source even if a summary already exists
- **Verification bias prevention**: The verify step uses a clean-context subagent that has never seen the compilation conversation — this prevents the LLM from rubber-stamping its own work

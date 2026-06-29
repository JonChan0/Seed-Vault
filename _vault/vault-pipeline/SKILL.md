---
name: vault-pipeline
description: Run the full pipeline in one pass. Use when the user says "process everything", "update the wiki", "run the pipeline", "process all sources", "ingest and compile", "full update", "sync the wiki", or drops multiple files and wants everything handled end to end. Orchestrates context-bounded subagents — parallel source-ingestor → single wiki-synthesizer → parallel clean-room-verifier — with deterministic assess/lint/digest in between.
---

# vault-pipeline — Agent-Orchestrated Pipeline

You are the **orchestrator**. You do not ingest, synthesize, or verify yourself —
you run the deterministic engines, then spawn **context-bounded subagents** that
each call the relevant `vault-*` skill. Parallelise where context is disparate
(ingest, verify); serialise where context is shared (synthesis).

    assess (deterministic)
       → N × source-ingestor   (parallel — one per raw file, Sonnet)
       → 1 × wiki-synthesizer   (serial — whole graph, Opus)
       → N × clean-room-verifier (parallel — one per new article, Haiku)
       → apply fixes (orchestrator) + lint + digest (deterministic)
       → log + report

Agents live in `.claude/agents/` (generated from `_vault/agents/`). Spawn them
with the `Agent` tool using `subagent_type: "<agent-name>"`. **To run instances
in parallel, emit multiple `Agent` calls in a single message.** Each agent's
`model` is pinned in its profile — do not pass a `model` override.

---

## Step 1: Assess (Deterministic — orchestrator)

```bash
uv run python _vault/lib/pipeline.py --json
```

Classifies `raw/` files as new / updated / unchanged.

- 0 new + 0 updated → stop: "Nothing new to process. Run vault-lint for a health
  check, or vault-qa to query the wiki."
- >10 new → ask: "There are {{N}} new sources. Process all, or just the most
  recent 5?"

---

## Step 2: Ingest — parallel `source-ingestor` fan-out

For each new/updated source, spawn one `source-ingestor` agent. **Batch all
spawns into a single message** so they run in parallel. Each agent receives one
`raw/` filepath and handles its own conversion (`convert.py`) internally.

```
Agent(subagent_type="source-ingestor",
      description="Ingest <filename>",
      prompt="Ingest exactly this one raw source: raw/<filename>. Convert first if non-markdown. Return summary_path and concepts_needing_article.")
```

Collect each agent's hand-back. On a single ingest failure, log it and continue —
do not abort the batch. Aggregate the union of `concepts_needing_article` and the
list of summary paths created.

---

## Step 3: Synthesize — single `wiki-synthesizer` (serial)

After **all** ingestors return, spawn exactly **one** `wiki-synthesizer`. It owns
whole-graph interlinking, so never run two in parallel.

```
Agent(subagent_type="wiki-synthesizer",
      description="Synthesize new concepts",
      prompt="Source summaries just ingested: <list>. Concepts flagged needing articles: <aggregated list>. Compile genuinely-new concept articles with bidirectional links, then rebuild the index (--no-cleanup). Return articles_created / articles_updated.")
```

Capture `articles_created`.

---

## Step 4: Verify — deterministic gate, then parallel `clean-room-verifier` fan-out

First run the **deterministic gate** over the new articles. It runs verify.py on
each and partitions them into those that still need an LLM pass and those whose
every extracted claim already matched a source exactly (no source warnings):

```bash
uv run python _vault/lib/verify.py --gate <wiki/concepts/stem.md ...> --json
```

Spawn a `clean-room-verifier` **only** for the articles in the `verify` list.
For each article in the `skip` list, set `status: reviewed` deterministically and
record it as **gate-skipped** in the report — do not spawn a verifier for it.

> **Escape hatch:** if the user said "force verify" / passed `--force-verify`,
> skip the gate and verify every article in `articles_created`. The gate trusts
> exact numeric matches and cannot catch contradictions or qualitative errors —
> `--force-verify` is the way to demand a full semantic pass.

If the gate skips **everything**, Step 4 spawns zero agents — this is the common
case and the pipeline's largest token saving.

For each article in the gate's `verify` list, spawn one `clean-room-verifier`.
**Batch all spawns into a single message** for parallelism. Verifiers are
read-only and context-isolated — they return reports, they do not edit.

```
Agent(subagent_type="clean-room-verifier",
      description="Verify <article>",
      prompt="Fact-check this one article with no prior context: wiki/concepts/<stem>.md. Run verify.py, follow vault-verify, return per-claim status, confidence, and recommended_fixes.")
```

---

## Step 5: Apply fixes + Lint + Digest (Deterministic — orchestrator)

1. For any CONTRADICTED claim in a verifier report, apply the `recommended_fixes`
   to the article and bump its `updated:` date. If a verifier returned LOW
   confidence, set `status: draft` and note the unverified claims.
2. Insert reciprocal backlinks deterministically (the synthesizer only authors
   forward links; reverse links are pure string work):
   ```bash
   uv run python _vault/lib/lint.py --fix-backlinks
   ```
3. If you edited any article, rebuild the index:
   ```bash
   uv run python _vault/lib/index.py --rebuild-qmd
   ```
4. Final lint (handles orphaned-source cleanup deferred by Step 3's `--no-cleanup`):
   ```bash
   uv run python _vault/lib/lint.py --json
   ```
   Fix any remaining broken wikilinks in the run's articles (missing backlinks
   were already auto-fixed in sub-step 2).
5. Digest for the summary stats:
   ```bash
   uv run python _vault/lib/digest.py
   ```

---

## Step 6: Log and Report

Append to `wiki/_log.md`:
```
[{{today}} pipeline] Ingested {{N}} sources, compiled {{N}} concepts, verified {{N}} articles
```

Output:
```
Pipeline complete — {{today}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sources ingested:   {{N}}   (parallel source-ingestor)
Concept articles:   {{C}} created, {{U}} updated   (wiki-synthesizer)
Index rebuilt:      Yes (+ qmd)
Verification:       {{V}} verified, {{S}} gate-skipped (clean exact matches)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
New concepts:
  - [[concept-a|Concept A]]
Gate-skipped (deterministically marked reviewed — spot-check if desired):
  - {{stem or "None"}}
Verification issues:
  - {{issue or "None — all claims supported"}}
Lint issues:
  - {{issue or "None"}}
Next steps:
  1. Review verification warnings in new articles
  2. vault-lint for full health check
  3. vault-qa to query the expanded wiki
```

---

## Notes

- **Why agents:** each profile is a context boundary. Ingest and verify have
  disparate per-item context → parallel instances. Synthesis needs the whole
  graph → one serial instance. See `_vault/agents/SPEC.md`.
- **Idempotent:** pipeline.py skips already-summarized files; rerunning is safe.
- **Partial failure:** one agent failing does not abort the batch — log and go on.
- **Force re-ingest:** if the user says "force re-ingest {{file}}", spawn a
  source-ingestor for it even if a summary exists.
- **Bias prevention:** verification runs in fresh-context agents that never saw
  the synthesis conversation — they cannot rubber-stamp their own work, and they
  hold no Write tool so they cannot silently "fix" to agree.
- **Visualization & QA** are not in this path — spawn `visualizer` or
  `qa-responder` directly when the user asks for a chart or a question.

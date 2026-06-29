# SPEC — Leaner Seed Vault Pipeline (Determinism-First Token Reduction)

**Status:** Draft — awaiting approval
**Author:** Claude (claude-opus-4-8)
**Date:** 2026-06-29
**Framework baseline:** 3.0.0
**Scope:** `_vault/vault-pipeline`, `_vault/agents/*`, individual `vault-*` skills, `_vault/lib/*.py`

---

## 1. Objective

Reduce LLM token usage across the Seed Vault pipeline by moving work currently
done by LLM agents into deterministic Python engines and external non-LLM tools,
**without degrading core function**. Core function = the same artifacts the
pipeline produces today (source summaries, interlinked concept articles with
bidirectional links + web grounding, a rebuilt index, and verified articles)
remain present and of equivalent quality.

### Target users
- **Primary:** the vault owner (Jon) running `vault-pipeline` and individual
  skills on a personal knowledge wiki.
- **Operators:** the orchestrator + subagents defined in `_vault/agents/`.

### Non-goals
- No change to the three-layer architecture (raw → wiki → schema).
- No change to frontmatter schema, linking conventions, or directory layout.
- No model-pin downshifts (decided: **determinism only, keep pins**).
- Web grounding stays **mandatory** for new concept articles (decided — core).

### Locked decisions (from requirements interview)
| Decision | Choice |
|----------|--------|
| Verification gating | **Gate hard** — skip the per-article LLM verifier when verify.py finds zero unmatched / partial claims and zero source warnings |
| Web grounding in compile | **Keep mandatory** — not trimmed |
| Model pins | **Keep** — savings come from determinism + gating only |
| Deliverable | **Spec + phased task plan** with token-impact estimates; implement only after approval |

---

## 2. Current State (baseline)

```
assess (pipeline.py, det)
  → N × source-ingestor   (Sonnet)  convert.py[det] + vault-ingest[LLM summary]
  → 1 × wiki-synthesizer  (Opus)    vault-compile[LLM + mandatory web] + vault-index[det]
  → N × clean-room-verifier (Haiku) verify.py[det] + vault-verify[LLM semantic]   ← always spawned
  → apply fixes + lint + digest (det) + report
```

Already deterministic (keep as-is): `pipeline.py` (assess), `index.py`,
`digest.py`, `lint.py` (7 checks), `convert.py` (opendataloader-pdf → pandoc),
`verify.py` (regex claim extraction + thefuzz fuzzy match), qmd retrieval,
external verify APIs (Semantic Scholar / CrossRef / Wayback).

### Heaviest repeated LLM costs
1. **clean-room-verifier fan-out** — one LLM agent per new article, *every run*,
   even when verify.py already matched every claim exactly.
2. **wiki-synthesizer** — whole-graph synthesis (genuine LLM; out of scope to cut).
3. **source-ingestor** — per-file summarization (genuine LLM; pin kept).
4. **Backlink maintenance** inside synthesis — string manipulation done by LLM.

---

## 3. Changes (what gets leaner)

### C1 — Hard verification gate (deterministic gate before LLM fan-out)
**Problem:** Step 4 spawns an LLM verifier per article unconditionally.
**Change:** Add a deterministic gate. After synthesis, run `verify.py --json` on
each new article (cheap, already exists). Spawn a `clean-room-verifier` **only**
for articles where the report shows `stats.unmatched > 0` **or**
`stats.partial > 0` **or** non-empty `source_warnings`. Articles where every
extracted claim is an exact match and there are no source warnings are auto-marked
`status: reviewed` deterministically and skipped.

**New engine:** `verify.py --gate <article...> --json` (or a thin
`gate_articles()` helper) returning `{ "verify": [...stems...], "skip": [...stems...] }`.
The orchestrator consumes this to decide the fan-out.

**Trade-off (must be documented in skill + report):** verify.py only extracts
*valued* claims (%, $, years, measurements, named numbers). It does **not** detect
contradictions or check qualitative/causal claims. Hard-gating therefore trusts
that an article with all-exact numeric matches needs no semantic pass. Mitigation:
- A manual escape hatch — `vault-verify` (and a `--force-verify` pipeline flag)
  always runs the full LLM pass on demand.
- The pipeline report explicitly lists which articles were **gate-skipped** so the
  user can spot-check.

### C2 — Deterministic backlink insertion (move string work out of LLM)
**Problem:** `vault-compile` / `wiki-synthesizer` perform bidirectional-link
maintenance (read target, add reverse link) in the LLM. `lint.py`
`check_missing_backlinks` already *detects* these but `auto_fixable: False`.
**Change:** Add `lint.py --fix-backlinks` that inserts the missing reciprocal
`[[kebab-stem|Title]]` under the target article's `## See Also` section
(creating the section if absent), and bumps `updated:`. Flip
`check_missing_backlinks` to `auto_fixable: True`. The synthesizer then only
needs to author *forward* links; reciprocal links become a deterministic pass in
Step 5.

**Engine work:** new `fix_missing_backlinks()` in `lint.py`; respects the
aliased-wikilink rule and the "don't backlink the index" exclusion already
encoded in the check.

### C3 — Deterministic frontmatter schema validation (new lint check #8)
**Problem:** Required-field/enum correctness (`type`, `status`, `framework_version`,
`llm_model` format, presence of `sources:` on concepts) is currently only enforced
by LLM diligence; errors surface late.
**Change:** Add `check_frontmatter_schema()` to `lint.py`:
- required keys present per `type`,
- `type ∈ {concept, source-summary, visualization, output}`,
- `status ∈ {draft, reviewed, verified}`,
- `framework_version` matches `_vault/VERSION`,
- `llm_model` non-empty.
Pure validation, no LLM. Surfaces in the lint report and pipeline lint step.

### C4 — Deterministic network-graph visualization (optional, standalone)
**Problem:** "Visualize connections between concepts" is full-LLM, but the data
(wikilink adjacency) is mechanical.
**Change:** Add `viz.py --network` that reads `wiki/**/*.md`, extracts
`[[wikilinks]]`, builds an adjacency list, and emits the self-contained D3
force-graph HTML + the Obsidian wrapper `.md` from a fixed template — zero LLM.
`vault-visualize` keeps the LLM path for *bespoke* charts; the network graph
becomes a deterministic shortcut it can shell out to.
**Note:** standalone (not in the core pipeline path) — lowest priority.

### C5 — Skill/agent prose trimming (DRY cleanup, not behavior change)
**Problem:** Some procedure detail is duplicated between agent bodies and
`SKILL.md`, and a few skills restate frontmatter blocks verbatim. Every agent
spawn re-reads its body + the invoked SKILL.md cold.
**Change:** Audit for duplication; ensure agent bodies stay thin wrappers (per
`_vault/agents/SPEC.md` DRY principle) and skills don't repeat the full
frontmatter template more than once. Document the gate (C1) in `vault-pipeline`
and `vault-verify` SKILL.md. No semantic change — pure context-size reduction.

---

## 4. Commands

```bash
# Existing (unchanged)
uv run python _vault/lib/pipeline.py --json            # assess
uv run python _vault/lib/convert.py "<path>" raw/      # convert
uv run python _vault/lib/index.py --rebuild-qmd        # index + qmd
uv run python _vault/lib/digest.py --markdown          # digest
uv run python _vault/lib/verify.py "<article>" --json  # claim extraction

# New / changed
uv run python _vault/lib/verify.py --gate <article...> --json   # C1: gate decision
uv run python _vault/lib/lint.py --fix-backlinks                # C2: auto-insert reciprocal links
uv run python _vault/lib/lint.py --json                         # C3: now includes frontmatter check
uv run python _vault/lib/viz.py --network --out viz/wiki-network-graph.html   # C4

# Pipeline escape hatch
# vault-pipeline ... --force-verify   → bypass C1 gate, full LLM verification
```

---

## 5. Project Structure (deltas only)

```
_vault/lib/
  verify.py        ← + gate_articles() / --gate flag        (C1)
  lint.py          ← + fix_missing_backlinks() / --fix-backlinks   (C2)
                     + check_frontmatter_schema() (8th check)      (C3)
  viz.py           ← NEW: deterministic network-graph generator    (C4)
_vault/vault-pipeline/SKILL.md   ← gate step + --force-verify + det backlink pass
_vault/vault-verify/SKILL.md     ← document the gate + escape hatch
_vault/vault-lint/SKILL.md       ← document --fix-backlinks + frontmatter check
_vault/vault-visualize/SKILL.md  ← document viz.py --network shortcut
_vault/agents/clean-room-verifier.md  ← note: spawned only when gated-in
tests/                           ← add coverage for C1/C2/C3 (see §6)
```
No new directories. `_vault/lib` is framework-owned — these edits are the
explicit subject of this task and override the default "do not modify" guidance.

---

## 6. Testing Strategy

Deterministic engines get unit tests (project already uses pytest under `tests/`);
agent/skill prose gets structural + behavioral validation.

| Change | Test |
|--------|------|
| C1 gate | Unit: article with all-exact claims → `skip`; with one `none`/`partial`/warning → `verify`. Fixture articles + raw sources. |
| C2 backlinks | Unit: A links B, B lacks backlink → after `--fix-backlinks`, B has `[[a|A]]` under `## See Also`, `updated:` bumped, idempotent on rerun, index excluded. |
| C3 frontmatter | Unit: missing key / bad enum / stale `framework_version` each flagged; valid file passes. |
| C4 viz | Unit: adjacency built from known wikilink fixtures; output HTML is self-contained (no external data deps beyond CDN); wrapper frontmatter valid. |
| Pipeline behavioral (manual) | Small `raw/` batch: confirm verifier fan-out only for gated-in articles; `--force-verify` overrides; report lists skipped articles. |
| Regression | Full existing suite passes (`uv run pytest`); lint on the live wiki returns no new false errors. |

**Acceptance criteria**
1. On a batch where verify.py matches all claims, **zero** `clean-room-verifier`
   agents spawn; those articles are marked `reviewed` and listed as gate-skipped.
2. Reciprocal backlinks are created by `lint.py --fix-backlinks`, not the LLM;
   `check_missing_backlinks` reports `auto_fixable: True` and clean after fix.
3. `lint.py --json` includes a `frontmatter_schema` check catching at least the
   five validation classes in C3.
4. `--force-verify` reproduces today's always-on behavior exactly.
5. All artifacts the baseline pipeline produced are still produced; full test
   suite green.

---

## 7. Code Style

- Match existing engine idioms: `from __future__ import annotations`,
  `pathlib.Path`, `__file__`-relative `VAULT_ROOT`, `argparse` CLI with
  `--json`, graceful degradation when an optional dep is missing (mirror the
  thefuzz pattern in verify.py).
- New flags are additive and backward-compatible; default behavior of existing
  commands is unchanged except where a change is explicitly specified (C3 adds a
  check to `lint.py --json` output).
- Agent bodies remain thin wrappers; `SKILL.md` stays the single source of truth.
- No new heavy dependencies. Reuse: `thefuzz` (present), stdlib `re`/`difflib`,
  `qmd` (present). No new external tool is required by core changes; viz uses
  D3 via CDN (already the project convention).

---

## 8. Boundaries

**Always**
- Keep `SKILL.md` the single source of truth; agents call skills, don't copy them.
- Keep `clean-room-verifier` read-only (no Write/Edit) — gating changes *when* it
  spawns, never its isolation.
- Run `bash _vault/install.sh` after editing any agent/skill source.
- Preserve every baseline artifact and the mandatory web-grounding step.
- List gate-skipped articles in the pipeline report (transparency for the C1 trade).

**Ask first**
- Any change to a model pin or the agent↔skill mapping (none planned here).
- Changing the C1 gate condition (e.g. also gating on partial matches).
- Editing framework-owned `install.sh` / `manifest.txt`.
- Removing or weakening web grounding.

**Never**
- Duplicate procedure logic from `SKILL.md` into agent bodies.
- Let the verifier inherit synthesis context.
- Modify `raw/` content or the `_vault/` schema beyond the files listed in §5.
- Silently skip verification without recording it in the report.

---

## 9. Phased Implementation Plan (ranked by token impact ÷ effort)

> Token-impact estimates are **per pipeline run on N new articles**, relative to
> baseline. They assume the common case (sources cleanly match), which is exactly
> when the savings are largest.

### Phase 1 — Hard verification gate  ★ highest impact
- **Changes:** C1 (`verify.py --gate`), `vault-pipeline` Step 4 rewrite,
  `--force-verify`, report lists skipped, `vault-verify` doc.
- **Token impact:** eliminates up to **N × (clean-room-verifier spawn + article
  + raw-source ingest + report)** per run. In the all-match case this is the
  single largest cut — the entire Step-4 LLM fan-out drops to ~0.
- **Effort:** S–M (gate helper is a few lines over existing `stats`; most work is
  skill prose + report wiring).
- **Risk:** Medium — trades contradiction-catching on numeric-clean articles.
  Mitigated by `--force-verify` + skipped-article transparency.
- **Exit:** Acceptance #1, #4.

### Phase 2 — Deterministic backlink insertion  ★ high impact
- **Changes:** C2 (`lint.py --fix-backlinks`), flip `check_missing_backlinks`
  auto_fixable, pipeline Step 5 runs it, trim backlink prose from `vault-compile`.
- **Token impact:** removes the read-target-and-edit reverse-link loop from the
  Opus synthesizer — **per new cross-link** savings on the most expensive agent.
- **Effort:** M (string insertion + idempotency + tests).
- **Risk:** Low — detection logic already exists and is trusted.
- **Exit:** Acceptance #2.

### Phase 3 — Frontmatter schema validation  ★ medium impact
- **Changes:** C3 (`check_frontmatter_schema()`), lint report + skill docs.
- **Token impact:** indirect — catches errors deterministically that otherwise
  cost LLM rounds to find/fix later. Small per-run, compounding over time.
- **Effort:** S.
- **Risk:** Low.
- **Exit:** Acceptance #3.

### Phase 4 — Prose/DRY trim  ★ small, steady impact
- **Changes:** C5 audit; document gate + new flags; remove duplication.
- **Token impact:** smaller cold-context per agent spawn; applies every run.
- **Effort:** S.
- **Risk:** Low.

### Phase 5 — Deterministic network viz  ☆ optional, standalone
- **Changes:** C4 (`viz.py --network`).
- **Token impact:** removes full-LLM generation for the one mechanical viz type;
  not in core pipeline, so per-run impact only when a network graph is requested.
- **Effort:** M.
- **Risk:** Low.
- **Defer** unless network graphs are requested often.

---

## 10. External / Non-LLM Tools Evaluated

| Tool | Verdict | Rationale |
|------|---------|-----------|
| **qmd** (BM25+vector) | Keep | Already core retrieval; nothing to add. |
| **thefuzz** | Keep / extend | Powers verify.py matching; reuse for C1, no new dep. |
| **opendataloader-pdf + pandoc** | Keep | convert.py already optimal for ingest conversion. |
| Semantic Scholar / CrossRef / Wayback APIs | Keep | Non-LLM external verification already wired in vault-verify. |
| **D3.js (CDN)** | Adopt for C4 | Project convention; deterministic network graph from adjacency. |
| markdownlint / remark | Reject | Overlaps lint.py; adds a Node dep for marginal gain. |
| Vale (prose linter) | Reject | Style-opinionated; out of scope, no token saving. |
| TextRank/sumy extractive summarizer | Reject | Would pre-draft summaries deterministically, but quality drop vs LLM ingest is too high for the saving; ingest pin kept anyway. |
| ripgrep for link extraction | Reject | Python glob+regex already fast at wiki scale; not worth a hard dep. |

---

## 11. Open Questions
- None blocking. Confirm approval of the phased plan; on approval I implement
  Phase 1 → 5 in order, with tests per phase before moving on.

# Spec: Context-Bounded Agent Profiles for the Vault Pipeline

## Objective

Introduce a layer of **subagents** between the `vault-pipeline` meta-skill and the
individual `vault-*` skills, so the pipeline runs steps in parallel where the
context is disparate, and serially where context is shared.

**Design principle — context, not function, defines an agent.** Two operations
that load the same context belong in one agent even if they do different jobs.
One operation whose context is *disparate per invocation* (e.g. per raw file,
per article) becomes N parallel agent instances.

**Hierarchy:**

```
vault-pipeline (meta-skill, main thread)
  ├─ deterministic assess  (pipeline.py)           — main thread
  ├─ N × source-ingestor   (parallel, Sonnet)      — one per raw file
  ├─ 1 × wiki-synthesizer  (serial, Opus)          — whole-graph context
  ├─ N × clean-room-verifier (parallel, Haiku)     — one per new article
  └─ deterministic lint + digest + report          — main thread
```

Each agent is a **thin wrapper**: it sets a context boundary, pins a model,
grants a tool subset, then invokes the relevant `vault-*` skill via the Skill
tool. `SKILL.md` files stay the single source of truth for procedures (DRY).

Standalone (not in the pipeline path) but defined for direct use:
`visualizer` (Sonnet), `qa-responder` (Haiku).

### Success criteria

- 5 agent files exist in `_vault/agents/` with valid Claude Code frontmatter
  (`name`, `description`, `tools`, `model`).
- `install.sh` generates `.claude/agents/<name>.md` symlinks; `bootstrap update`
  keeps them in sync (covered by `manifest.txt`'s `_vault/` entry).
- `vault-pipeline` SKILL.md spawns the three pipeline agents, parallelising
  ingest and verify, serialising synthesis.
- Each agent invokes exactly the skills its context owns — no procedure logic
  duplicated from SKILL.md into agent bodies.
- Running `install.sh` then listing `.claude/agents/` shows all 5; lint passes.

## Tech Stack

- Claude Code project-local agents (`.claude/agents/*.md`), generated from
  `_vault/agents/*.md`.
- Existing `vault-*` skills + Python engines (`_vault/lib/*.py`, run via `uv`).
- Framework version 3.0.0 (`_vault/VERSION`).

## Commands

```
Install/refresh agents + skills:  bash _vault/install.sh
Assess pipeline state:            uv run python _vault/lib/pipeline.py --json
Convert a raw file:               uv run python _vault/lib/convert.py "<path>" raw/
Rebuild index:                    uv run python _vault/lib/index.py --rebuild-qmd
Lint:                             uv run python _vault/lib/lint.py --json
List installed agents:            ls -l .claude/agents/
```

## Project Structure

```
_vault/agents/                 → Agent profile source (framework-owned, tracked)
  SPEC.md                      → this spec
  source-ingestor.md           → Sonnet — per raw file (parallel)
  wiki-synthesizer.md          → Opus   — whole graph (serial)
  clean-room-verifier.md       → Haiku  — per article (parallel, read-only)
  visualizer.md                → Sonnet — per viz (standalone)
  qa-responder.md              → Haiku  — per query (standalone, read-only)
.claude/agents/<name>.md       → generated symlinks (gitignored)
_vault/vault-*/SKILL.md        → procedures (unchanged single source of truth)
```

## Code Style

Agent file = YAML frontmatter + a short markdown body. Body states the context
boundary, the skill(s) to invoke, and the hand-back contract. No duplicated
procedure steps.

```markdown
---
name: source-ingestor
description: Ingest ONE raw source file into a wiki source summary. Spawned one per file by vault-pipeline for parallel ingest.
tools: Read, Write, Edit, Bash, Glob, Skill
model: sonnet
---

You ingest exactly ONE raw source file. Your context is that file only — you
neither know nor need the rest of the wiki.

You will be given: a single `raw/` filepath.

1. Invoke the `vault-ingest` skill (Skill tool) and follow it for this one file.
2. Hand back: the summary path created, and concepts flagged "needs article".
```

## Testing Strategy

No unit-test framework for prose agents. Validation is structural + behavioural:

- **Structural:** `install.sh` runs clean; `.claude/agents/` lists 5 files;
  each frontmatter parses (name/description/tools/model present, model ∈
  {sonnet, opus, haiku}).
- **Reference integrity:** every skill an agent names exists under `_vault/vault-*`.
- **Behavioural (manual):** a pipeline dry-run on a small `raw/` batch spawns the
  expected agent fan-out and produces summaries + concept articles.

## Boundaries

- **Always:** keep `SKILL.md` the single source of truth; agents call skills, not
  copy them. Keep `clean-room-verifier` read-only (no Write/Edit) to preserve
  unbiased verification. Run `install.sh` after editing any agent source.
- **Ask first:** changing agent→skill mapping; changing a model pin; adding new
  agents; editing framework-owned `install.sh` / `manifest.txt`.
- **Never:** duplicate procedure logic into agent bodies; let the verifier inherit
  synthesis context; commit secrets.

## Model pins (user-specified)

| Agent | Model | Context boundary | Parallel |
|-------|-------|------------------|----------|
| source-ingestor | sonnet | one raw file | yes (per file) |
| wiki-synthesizer | opus | whole wiki graph | no (serial) |
| clean-room-verifier | haiku | one article + sources, clean | yes (per article) |
| visualizer | sonnet | one concept's data | yes (per viz) |
| qa-responder | haiku | one query + retrieved snippets | per query |

## Open Questions

Resolved in conversation: install = generate from `_vault`; synthesizer =
compile+index only (lint/digest run by orchestrator after verify); subagents
invoke skills via the Skill tool at runtime.

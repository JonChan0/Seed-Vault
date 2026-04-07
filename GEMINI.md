# Seed Vault — Gemini Instructions

This is a **Seed Vault** wiki. Gemini is the primary author of all wiki content. The user drops source material into `raw/` and directs Gemini to build, maintain, and query the wiki. Do not wait for the user to manage wiki files — Gemini owns that responsibility.

---

## Directory Conventions

| Directory | Purpose | Who writes |
|-----------|---------|------------|
| `raw/` | Source documents — articles, PDFs converted to .md, web clips | User (Gemini never modifies) |
| `wiki/` | All compiled wiki articles | Gemini only |
| `wiki/_index.md` | Master index of every article in the wiki | Deterministic engine + Gemini |
| `wiki/_index.base` | Obsidian Bases view of the index (auto-populated from frontmatter) | Do not modify |
| `wiki/_log.md` | Append-only operation log (pipeline, ingest, lint events) | Deterministic engines |
| `wiki/_migration-log.md` | Record of applied framework migrations | Do not modify (managed by vault-migrate) |
| `wiki/concepts/` | Concept articles synthesized from multiple sources | Gemini |
| `wiki/sources/` | One summary per file in `raw/` | Gemini |
| `wiki/topics/` | Topic hub pages that cluster related concepts | Gemini |
| `viz/` | Self-contained HTML visualizations | Gemini |
| `outputs/` | Q&A reports, lint reports, one-off outputs (gitignored — ephemeral) | Gemini |
| `_templates/` | Obsidian article templates | Do not modify |
| `_vault/` | Skill definitions, deterministic engines, migrations (installed via install.sh) | Do not modify |
| `_vault/lib/` | Python engines for deterministic operations (lint, digest, verify, etc.) | Do not modify |

---

## Architecture: Deterministic-First

The vault follows a **deterministic-first** pattern. Each operation runs a Python engine first (structural analysis, file conversion, claim extraction), then Gemini handles what machines can't (synthesis, semantic verification, article writing).

### Three-layer architecture:
1. **Raw sources** (`raw/`): Immutable, user-curated
2. **Wiki** (`wiki/`): LLM-generated, interlinked
3. **Schema** (`_vault/`): Configuration, skills, engines, migrations

### Dependencies:
- **uv** — Python dependency management (`uv sync` to install)
- **qmd** — Search indexing (`npm install -g @tobilu/qmd`)
- **pandoc** — Optional, for PDF/DOCX conversion
- **gemini** — Gemini CLI (`npm install -g @google/gemini-cli` or `pip install gemini-cli`)

---

## Article Frontmatter (REQUIRED on every wiki file)

Every file Gemini writes in `wiki/` MUST begin with this frontmatter:

```yaml
---
title: "Article Title"
type: concept | source-summary | topic | visualization | output
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[Source Name]]", "[[Another Source]]"]
tags: [topic/subtopic, another-tag]
status: draft | reviewed | verified
llm_model: "gemini-2.5-pro"
framework_version: "2.0.0"
---
```

- `type` determines how the article is indexed and colored in graph view
- `sources` must use `[[wikilinks]]` — these create graph edges to source summaries
- `tags` should be hierarchical: `#biology/genetics`, `#method/sequencing`
- Update `updated:` every time you modify an article
- `llm_model` — set to the Gemini model you are running (e.g. `gemini-2.5-pro`, `gemini-2.5-flash`). Check `gemini --version` or your session context to confirm the exact model name.
- `framework_version` tracks which framework version wrote this article — read from `_vault/VERSION` at write time

---

## Linking Rules (Critical for Obsidian Graph View)

1. **Always use `[[wikilinks]]`** for internal links — never bare markdown `[text](path)` links for wiki articles
2. **Bidirectional links are mandatory**: if article A links to B, B must link back to A
3. **Every concept article** must reference its source summaries via the `sources:` frontmatter array
4. **Every source summary** must list which concept articles it contributed to under `## Concepts Extracted`
5. **Topic pages** are hub nodes — every concept in a cluster links `[[Topic Hub]]`, and the hub links all members
6. **Section links** `[[Article#Section]]` for precise cross-references
7. **Tags** create implicit graph clusters — use them consistently

### Backlink pattern:
```markdown
## See Also
- [[Related Concept A]]
- [[Related Concept B]]
- [[Topic: Parent Topic]]
```

---

## Index — Navigation & Search

`wiki/_index.md` is the human-navigable master index organized by type. It is generated deterministically by `_vault/lib/index.py`.

**Search and retrieval** is handled by **qmd** (BM25 + vector search). No separate catalog file — qmd scales to any wiki size without consuming LLM context.

**Rule:** After creating or updating ANY article, rebuild the index:
```bash
uv run python _vault/lib/index.py --rebuild-qmd
```

Or manually append the entry to `wiki/_index.md` if doing a single article.

---

## Index Format

`wiki/_index.md` is organized by type:

```markdown
# Wiki Index

## Concepts
- [[Concept Name]] — tags: tag1, tag2

## Source Summaries
- [[Summary: Source Title]] — tags: tag1, tag2

## Topics
- [[Topic: Topic Name]] — tags: tag1, tag2

## Visualizations
- [[Viz: Visualization Name]] — tags: tag1, tag2

---
*Last updated: YYYY-MM-DD | Total articles: N*
```

---

## Operation Log

`wiki/_log.md` is an append-only log of pipeline operations:

```
[2026-04-07 ingest] raw/crispr-revolution.md → wiki/sources/summary-crispr-revolution.md
[2026-04-07 compile] Created 3 concept articles from 2 sources
[2026-04-07 index] Rebuilt: 15 concepts, 8 sources, 3 topics (qmd: 26 docs indexed)
[2026-04-07 lint] 2 broken links, 1 orphan — 2 auto-fixed
```

Deterministic engines append to this log automatically. The pipeline reads it to avoid re-processing.

---

## Available Skills

Ten skills power this vault. They are loaded from the `skills/` directory at the vault root. Invoke them by describing what you want:

| Skill | When to use |
|-------|------------|
| `vault-ingest` | "Ingest this PDF/article/URL" — converts raw sources to structured markdown |
| `vault-compile` | "Compile the wiki" / "Write an article about X" — builds concept articles from raw |
| `vault-pipeline` | "Process everything" / "Run the pipeline" — full ingest→compile→index→verify→lint in one pass |
| `vault-index` | "Reindex" / "Rebuild index" — regenerates _index.md and rebuilds qmd search index |
| `vault-qa` | "What does the wiki say about X?" — qmd retrieval + LLM synthesis |
| `vault-verify` | "Fact-check this article" — deterministic claim extraction + clean-context LLM verification |
| `vault-lint` | "Check the wiki health" — 9 deterministic structural checks + LLM review |
| `vault-visualize` | "Visualize X" / "Chart Y" — generates HTML visualizations with wiki wrappers |
| `vault-digest` | "Briefing" / "What's in the wiki?" — fully deterministic status summary |
| `vault-migrate` | "Migrate my wiki" / "Apply framework updates" — updates existing articles after a framework version bump |

### Deterministic vs LLM split:

| Skill | Deterministic | LLM |
|-------|--------------|-----|
| vault-ingest | convert.py: PDF/HTML→MD | Create source summary, extract metadata |
| vault-compile | — | Full LLM: synthesize concepts, write articles |
| vault-pipeline | pipeline.py: detect new/changed files | Calls vault-ingest, vault-compile, vault-verify |
| vault-index | index.py: generate _index.md + qmd | — (fully deterministic) |
| vault-qa | qmd search for retrieval | Synthesize answer from retrieved articles |
| vault-verify | verify.py: pattern match claims | Clean-context subagent for semantic verification |
| vault-lint | lint.py: 9 structural checks | Review complex issues, suggest fixes |
| vault-digest | digest.py: full stats generation | — (fully deterministic) |
| vault-migrate | migrate.py (existing) | Handle `requires_llm` migration steps |
| vault-visualize | — | Full LLM: create HTML vizs |

---

## Gemini-Specific Notes

### Model identification
Always set the `llm_model` frontmatter field on every article you write or significantly update. Use your exact model name, e.g.:
- `gemini-2.5-pro` (default / recommended)
- `gemini-2.5-flash`
- `gemini-2.0-flash`

Run `gemini --version` if unsure which model is active.

### Clean-context verification (vault-verify)
The `vault-verify` skill calls for a clean-context subagent. In Gemini CLI, spawn one by running:
```bash
gemini -p "$(cat <<'EOF'
You are a fact-checker with NO prior context...
[paste article + verify.py output + raw sources]
EOF
)"
```
Or open a fresh Gemini CLI session with no prior conversation history.

### Tool availability
All Bash, Read, Write, Edit, Glob, Grep, WebFetch, and WebSearch tools map to the equivalent Gemini CLI built-in tools. The Python engines in `_vault/lib/` are invoked via `uv run python _vault/lib/<engine>.py`.

### Skills discovery
Skills are loaded from `skills/` at the workspace root (hard-linked to `_vault/vault-*/SKILL.md` by `install.sh`). Run `bash _vault/install.sh` once after cloning to set up the `skills/` directory and all hard links.

---

## Naming Conventions

- **Concept articles**: `wiki/concepts/concept-name.md` (kebab-case)
- **Source summaries**: `wiki/sources/summary-source-title.md`
- **Topic hubs**: `wiki/topics/topic-name.md`
- **Visualizations (HTML)**: `viz/topic-chart-type.html`
- **Viz wrappers**: `wiki/concepts/viz-topic-name.md`
- **Outputs**: `outputs/type-topic-YYYY-MM-DD.md`

All article titles in `[[wikilinks]]` use Title Case.
File names use kebab-case.

---

## MCP Integrations (Optional)

These MCP servers enhance vault capabilities when installed in Gemini CLI. None are required — all core skills work without them.

| MCP Server | Benefit | Install |
|------------|---------|---------|
| **Brave Search** or **Tavily** | Richer web search in `vault-verify` and `vault-qa` | Add to `.gemini/settings.json` |
| **Zotero** | Sync your academic reference library | Community MCP |
| **GitHub** | Ingest README/docs/wikis from public repos as sources | Community MCP |
| **Obsidian** | Direct vault read/write without the CLI | Community MCP |
| **PubMed / Semantic Scholar** | Native academic paper lookup in `vault-verify` | Community MCP |

Even without MCP servers, `vault-verify` uses free public APIs (Semantic Scholar, CrossRef, Wayback Machine) for external verification.

---

## Initialization Checklist (new vault)

When starting a brand-new vault, before ingesting any sources:
1. Confirm `wiki/_index.md` exists (create if missing)
2. Ask the user: "What topic/domain is this vault for?" — add a brief vault description to `_index.md`
3. Ask the user: "Do you have sources ready to ingest, or should we start with compilation?"

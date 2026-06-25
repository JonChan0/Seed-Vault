# Vault Architecture

Seed Vault follows a **deterministic-first** pattern. Each operation runs a Python engine first (structural analysis, file conversion, claim extraction), then the LLM handles what machines can't (synthesis, semantic verification, article writing).

## Three-Layer Architecture

```
raw/          ← you drop source files here (PDFs, web clips, text)
  └── article.pdf, webpage.md, paper.pdf

_vault/lib/   ← deterministic Python engines
  ├── convert.py     file conversion (PDF/HTML/DOCX → MD)
  ├── lint.py        9 structural health checks
  ├── digest.py      statistics generator
  ├── verify.py      claim extraction & source matching
  ├── index.py       index generator + qmd rebuild
  └── pipeline.py    orchestration (detect new/changed files)

wiki/         ← LLM writes everything here
  ├── _index.md        master index (deterministically generated)
  ├── _log.md          append-only operation log
  ├── concepts/        synthesized concept articles
  └── sources/         one summary per raw/ file

viz/          ← self-contained HTML visualizations
outputs/      ← Q&A reports, lint reports, one-offs
```

The LLM is the primary author of all files in `wiki/`, `viz/`, and `outputs/`. You never edit those directly — you direct the LLM. Deterministic engines handle structural tasks (indexing, linting, claim extraction) while the LLM handles synthesis and reasoning.

## Deterministic vs LLM Split

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

## Full Directory Reference

```
your-wiki/
├── CLAUDE.md            Claude Code operating instructions (auto-loaded)
├── AGENTS.md            Antigravity CLI operating instructions (auto-loaded)
├── README.md            Project overview
├── pyproject.toml       Python dependencies (managed by uv)
├── docs/                Framework documentation (this folder — tracked in git)
├── .claude/             Claude Code project config
│   └── skills/          Project-local skill symlinks → _vault/ (gitignored)
├── .agents/             Antigravity CLI project config
│   └── skills/          Project-local skill hard links → _vault/ (gitignored)
├── _vault/              Skill definitions & engines (tracked in git)
│   ├── VERSION          Framework version (3.0.0)
│   ├── install.sh       Run once after cloning
│   ├── migrate.py       Wiki migration runner
│   ├── migrations/      Migration specs (JSON)
│   ├── lib/             Deterministic Python engines
│   ├── vault-ingest/    Raw source → markdown converter
│   ├── vault-compile/   Wiki article builder
│   ├── vault-pipeline/  Full pipeline orchestrator
│   ├── vault-index/     Index & qmd rebuilder
│   ├── vault-qa/        Question answering (qmd + LLM)
│   ├── vault-verify/    Fact checker (deterministic + clean-context subagent)
│   ├── vault-lint/      Health checker (9 structural checks + LLM review)
│   ├── vault-digest/    Status briefing (fully deterministic)
│   ├── vault-migrate/   Framework migration handler
│   └── vault-visualize/ HTML visualization generator
├── _templates/          Obsidian article templates (tracked)
├── .obsidian/           Obsidian vault config (tracked)
├── raw/                 Source documents — gitignored, local only
├── wiki/                Compiled wiki — gitignored, local only
│   └── _index.base      Obsidian Bases view of the index (auto-populated)
├── viz/                 Visualizations — gitignored, local only
└── outputs/             Reports & outputs — gitignored, local only
```

## Dependencies

| Dependency | Purpose | Install |
|------------|---------|---------|
| **uv** | Python dependency management | `pip install uv` or via installer |
| **qmd** | BM25 + vector search index | `npm install -g @tobilu/qmd` |
| **pandoc** | Optional — PDF/DOCX conversion (via `pypandoc`) | Auto-installed by pypandoc, or `brew install pandoc` |

## See Also

- [Article Frontmatter](Article-Frontmatter.md)
- [LLM Frontends](LLM-Frontends.md)
- [Obsidian Setup](Obsidian-Setup.md)
- [Updating Your Vault](Updating-Your-Vault.md)

# Seed Vault

A portable, Claude-powered personal knowledge wiki framework. Use this repo as a **GitHub template** — each wiki is a fresh instance that lives entirely on your local machine. Your raw sources, compiled articles, and visualizations are never pushed to GitHub.

---

## Starting a New Wiki

### On GitHub
1. Click **"Use this template"** → **"Create a new repository"**
2. Name it after your topic (e.g. `genomics-wiki`, `stoic-philosophy-wiki`)
3. Set it to **Private** (recommended — your wiki content stays local anyway)
4. Clone it locally:

```bash
git clone https://github.com/you/your-wiki-name
cd your-wiki-name
```

### Local Setup
```bash
# Install Python dependencies (requires uv)
uv sync

# Install qmd for search indexing
npm install -g @tobilu/qmd

# Install the Claude skills (symlinks _vault/ skills into ~/.claude/skills/)
bash _vault/install.sh

# Reload skills in Claude Code
# /reload-plugins

# Open as an Obsidian vault
# Obsidian → File → Open Vault → select this folder
```

Then in Claude Code, open the folder and say:
> "Initialize this vault for [your topic]. I'll start adding sources."

---

## What Stays on GitHub vs. What Stays Local

| | GitHub (the template) | Your local wiki |
|--|----------------------|--------------------|
| `_vault/` skills & engines | ✅ tracked | ✅ tracked (symlinked) |
| `CLAUDE.md`, `_templates/`, `.obsidian/` | ✅ tracked | ✅ tracked |
| `pyproject.toml` | ✅ tracked | ✅ tracked |
| `raw/` source documents | ❌ gitignored | local only |
| `wiki/` compiled articles | ❌ gitignored | local only |
| `viz/` visualizations | ❌ gitignored | local only |
| `outputs/` reports | ❌ gitignored | local only |

**Wiki content is deliberately not tracked.** Your notes, source documents, and compiled articles can be large, private, or both. Keep them local (or back them up separately with your own approach — e.g. a private git repo, Obsidian Sync, or a local backup).

### Pulling Framework Updates

If the template adds new skills or improves existing ones:

```bash
# Add the template as an upstream remote (one-time)
git remote add upstream https://github.com/you/seed-vault

# Pull framework changes (skills, CLAUDE.md, templates)
git fetch upstream
git merge upstream/main --allow-unrelated-histories

# Re-sync dependencies and re-install skills
uv sync
bash _vault/install.sh
# /reload-plugins         # in Claude Code

# If the framework version changed, migrate existing articles
# Run vault-migrate in Claude Code
```

---

## How It Works

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

wiki/         ← Claude writes everything here
  ├── _index.md        master index (deterministically generated)
  ├── _log.md          append-only operation log
  ├── concepts/        synthesized concept articles
  ├── sources/         one summary per raw/ file
  └── topics/          topic hub pages (cluster nodes for graph view)

viz/          ← self-contained HTML visualizations
outputs/      ← Q&A reports, lint reports, one-offs
```

Claude is the primary author of all files in `wiki/`, `viz/`, and `outputs/`. You never edit those directly — you direct Claude. Deterministic engines handle structural tasks (indexing, linting, claim extraction), while Claude handles synthesis and reasoning.

---

## Skills

<!-- SKILLS:START -->
| Skill Name | Say this... | Claude will... |
|------------|-------------|----------------|
| `vault-ingest` | "Ingest raw/paper.pdf" / "import this URL" | Run convert.py for file conversion, then create source summary in wiki/sources/; supports YouTube transcripts and Wayback Machine fallback for dead URLs |
| `vault-compile` | "Compile the wiki" / "write an article about X" | Build interconnected concept articles and topic hub pages from raw sources, with Recommended Reading Order on hub pages |
| `vault-pipeline` | "Process everything" / "run the pipeline" | Run pipeline.py to detect changes, then orchestrate ingest → compile → index → verify (clean-context subagent) → lint |
| `vault-index` | "Reindex" / "rebuild index" | Run index.py to rebuild _index.md and qmd search index; fully deterministic |
| `vault-qa` | "What do we know about X?" / "research X" | Use qmd for retrieval, then synthesize an answer with citations and confidence rating |
| `vault-verify` | "Fact-check the X article" / "verify this" | Run verify.py for claim extraction, then launch clean-context subagent for unbiased semantic verification |
| `vault-lint` | "Check the wiki health" / "lint" | Run lint.py for 9 structural checks, then review complex issues and suggest fixes |
| `vault-visualize` | "Visualize X as a chart" / "map out X" | Generate self-contained HTML chart/diagram + Obsidian wrapper page |
| `vault-digest` | "Briefing" / "what's in the wiki?" | Run digest.py for fully deterministic vault status summary |
| `vault-migrate` | "Migrate my wiki" / "apply updates" | Run migrate.py for structural changes, handle LLM migration steps if needed |
<!-- SKILLS:END -->

---

## Obsidian Setup

This vault is pre-configured for Obsidian:
- **Graph view**: Concepts (blue), Sources (green), Topics (purple), Visualizations (orange)
- **Templates**: stored in `_templates/`
- **Backlinks** and **Properties**: enabled

Open as a vault: Obsidian → File → Open Vault → select this folder.

### Viewing Visualizations

HTML visualizations in `viz/` are embedded in wrapper `.md` pages via `<iframe>`. To view them in Obsidian:
1. Install the **HTML Reader** community plugin, OR
2. Open the `.html` file from Obsidian's file explorer (opens in browser)
3. Mermaid diagrams render natively — no plugin needed

---

## Directory Reference

```
your-wiki/
├── CLAUDE.md            Claude's operating instructions (auto-loaded)
├── README.md            This file
├── pyproject.toml       Python dependencies (managed by uv)
├── _vault/              Skill definitions & engines (tracked in git)
│   ├── VERSION          Framework version (2.0.0)
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
│   ├── vault-lint/      Health checker (9 deterministic checks + LLM review)
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

---

## Workflow

![Seed Vault Workflow](workflow.png)

> **Tip — Ingest from the web:** Use [Obsidian Web Clipper](https://obsidian.md/clipper) to save web pages directly into `raw/` as clean markdown. It pairs naturally with the `vault-ingest` skill and tags clipped pages with `#Clippings` automatically.

Each cycle enriches the wiki. Q&A answers can become new concept articles. Visualizations become graph nodes. Verification adds sourcing depth.

---

*Last updated: 2026-04-07 (v2.0: renamed seed-* → vault-*, added deterministic Python engines, qmd search integration, clean-context verification subagent, eliminated _catalog.md)*

Inspired by: https://x.com/karpathy/status/2039805659525644595

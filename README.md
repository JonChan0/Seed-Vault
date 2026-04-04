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
# Install the Claude skills (symlinks _seeds/ into ~/.claude/skills/)
bash _seeds/install.sh

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
| `_seeds/` skills | ✅ tracked | ✅ tracked (symlinked) |
| `CLAUDE.md`, `_templates/`, `.obsidian/` | ✅ tracked | ✅ tracked |
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
bash _seeds/install.sh   # re-run to pick up any new skills
# /reload-plugins         # in Claude Code
```

---

## How It Works

```
raw/          ← you drop source files here (PDFs, web clips, text)
  └── article.pdf, webpage.md, paper.pdf

wiki/         ← Claude writes everything here
  ├── _index.md        master index
  ├── _catalog.md      Claude's search index (2–3 sentences per article)
  ├── concepts/        synthesized concept articles
  ├── sources/         one summary per raw/ file
  └── topics/          topic hub pages (cluster nodes for graph view)

viz/          ← self-contained HTML visualizations
outputs/      ← Q&A reports, lint reports, one-offs
```

Claude is the primary author of all files in `wiki/`, `viz/`, and `outputs/`. You never edit those directly — you direct Claude.

---

## Skills

<!-- SKILLS:START -->
| Skill Name | Say this... | Claude will... |
|------------|-------------|----------------|
| `seed-ingest` | "Ingest raw/paper.pdf" / "import this URL" | Convert PDF/HTML/URL → structured markdown in raw/, create source summary in wiki/sources/; supports YouTube transcripts and Wayback Machine fallback for dead URLs |
| `seed-compile` | "Compile the wiki" / "write an article about X" | Build interconnected concept articles and topic hub pages from raw sources, with Recommended Reading Order on hub pages |
| `seed-pipeline` | "Process everything" / "run the pipeline" | Orchestrate a full ingest → compile → index → lint pass in one command; idempotent (skips already-processed sources) |
| `seed-index` | "Reindex" / "rebuild catalog" | Rebuild _index.md and _catalog.md; delta mode skips articles whose `updated:` date hasn't changed |
| `seed-qa` | "What do we know about X?" / "research X" | Research and synthesize an answer from wiki content, cite with wikilinks; includes a Confidence (HIGH/MEDIUM/LOW) rating |
| `seed-verify` | "Fact-check the X article" / "verify this" | Cross-reference claims against sources and web (Semantic Scholar, Wikipedia, CrossRef, PubMed, Wayback Machine); supports quick mode (internal-only) |
| `seed-lint` | "Check the wiki health" / "lint" | Find broken links, orphan pages, missing backlinks, inconsistencies, and unsummarized raw/ files |
| `seed-visualize` | "Visualize X as a chart" / "map out X" | Generate self-contained HTML chart/diagram (dark or light theme, including SVG) + Obsidian wrapper page |
| `seed-digest` | "Briefing" / "what's in the wiki?" | Generate a vault status summary: article counts, recent updates, hub nodes, knowledge gaps, and suggested next actions |
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
├── _seeds/              Skill definitions (tracked in git)
│   ├── install.sh       Run once after cloning
│   ├── seed-ingest/     Raw source → markdown converter
│   ├── seed-compile/    Wiki article builder
│   ├── seed-index/      Index & catalog rebuilder (maintains _index.md + _catalog.md)
│   ├── seed-qa/         Question answering from the wiki
│   ├── seed-verify/     Fact checker
│   ├── seed-lint/       Health checker
│   └── seed-visualize/  HTML visualization generator
├── _templates/          Obsidian article templates (tracked)
├── .obsidian/           Obsidian vault config (tracked)
├── raw/                 Source documents — gitignored, local only
├── wiki/                Compiled wiki — gitignored, local only
│   ├── _index.base      Obsidian Bases view of the index (auto-populated)
│   └── _catalog.base    Obsidian Bases view of the catalog (auto-populated)
├── viz/                 Visualizations — gitignored, local only
└── outputs/             Reports & outputs — gitignored, local only
```

---

## Workflow

![Seed Vault Workflow](workflow.png)

> **Tip — Ingest from the web:** Use [Obsidian Web Clipper](https://obsidian.md/clipper) to save web pages directly into `raw/` as clean markdown. It pairs naturally with the `seed-ingest` skill and tags clipped pages with `#Clippings` automatically.

Each cycle enriches the wiki. Q&A answers can become new concept articles. Visualizations become graph nodes. Verification adds sourcing depth.

---

*Last updated: 2026-04-04 (skills: added seed-pipeline, seed-digest; improved seed-ingest, seed-index, seed-lint, seed-verify, seed-qa, seed-visualize; added Obsidian Bases views)*

Inspired by: https://x.com/karpathy/status/2039805659525644595 

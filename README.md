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
| Say this... | Claude will... |
|-------------|----------------|
| "Ingest raw/paper.pdf" / "import this URL" | Convert PDF/HTML/URL → structured markdown in raw/, create source summary in wiki/sources/ |
| "Compile the wiki" / "write an article about X" | Build interconnected concept articles and topic hub pages from raw sources |
| "Reindex" / "rebuild catalog" | Rebuild _index.md and _catalog.md from all current wiki articles |
| "What do we know about X?" / "research X" | Research and synthesize an answer from wiki content, cite with wikilinks |
| "Fact-check the X article" / "verify this" | Cross-reference claims against sources and web search, flag contradictions |
| "Check the wiki health" / "lint" | Find broken links, orphan pages, missing backlinks, inconsistencies |
| "Visualize X as a chart" / "map out X" | Generate self-contained HTML chart/diagram + Obsidian wrapper page |
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
│   ├── seed-index/      Index & catalog rebuilder
│   ├── seed-qa/         Question answering from the wiki
│   ├── seed-verify/     Fact checker
│   ├── seed-lint/       Health checker
│   └── seed-visualize/  HTML visualization generator
├── _templates/          Obsidian article templates (tracked)
├── .obsidian/           Obsidian vault config (tracked)
├── raw/                 Source documents — gitignored, local only
├── wiki/                Compiled wiki — gitignored, local only
├── viz/                 Visualizations — gitignored, local only
└── outputs/             Reports & outputs — gitignored, local only
```

---

## Workflow

```
1. Ingest    →  raw/ + wiki/sources/
2. Compile   →  wiki/concepts/ + wiki/topics/
3. Q&A       →  answers from wiki content
4. Verify    →  fact-check against sources & web
5. Lint      →  fix broken links, add backlinks
6. Visualize →  viz/*.html + wiki wrapper pages
7. (repeat)  →  explorations file back into wiki, enriching it over time
```

Each cycle enriches the wiki. Q&A answers can become new concept articles. Visualizations become graph nodes. Verification adds sourcing depth.

---

*Last updated: 2026-04-03*

# Seed Vault

A portable, Claude-powered personal knowledge wiki framework. Clone this repo into any folder, drop in your sources, and let Claude build a richly interconnected Obsidian wiki from them.

---

## Quick Start

```bash
# 1. Clone into a new folder for your topic
git clone <repo-url> my-topic-wiki
cd my-topic-wiki

# 2. Install the skills (requires ~/.claude/skills/ to exist)
bash _seeds/install.sh

# 3. In Claude Code, reload skills
# /reload-plugins

# 4. Open the folder as an Obsidian vault
# File → Open Vault → select this folder

# 5. Start ingesting sources
# Drop PDFs or web articles into raw/
# Then ask Claude: "ingest raw/my-article.pdf"
```

---

## How It Works

```
raw/          ← you drop source files here
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

| Say this... | Claude will... |
|-------------|---------------|
| "Ingest raw/paper.pdf" | Convert PDF → markdown, create source summary |
| "Compile the wiki" | Build concept articles from all sources |
| "Write an article about X" | Create a concept page for X |
| "What do we know about X?" | Research and answer from the wiki |
| "Fact-check the X article" | Cross-reference claims against sources + web |
| "Check the wiki health" | Find broken links, orphans, inconsistencies |
| "Visualize X as a chart" | Generate HTML chart + Obsidian wrapper page |
| "Rebuild the index" | Regenerate _index.md and _catalog.md |

---

## Obsidian Setup

This vault is pre-configured for Obsidian:
- **Graph view**: Concepts (blue), Sources (green), Topics (purple), Visualizations (orange)
- **Templates**: stored in `_templates/`
- **Backlinks**: enabled
- **Properties**: enabled (for frontmatter viewing)

Open this folder as a vault: Obsidian → File → Open Vault → select this folder.

### Viewing Visualizations

HTML visualizations in `viz/` are embedded in their wrapper `.md` pages via `<iframe>`. To view them in Obsidian:
1. Install the **HTML Reader** community plugin, OR
2. Open the `.html` file directly from Obsidian's file explorer (opens in browser)
3. Flowcharts using Mermaid render natively without any plugin

---

## Directory Reference

```
Seed_Vault/
├── CLAUDE.md            Claude's operating instructions (auto-loaded)
├── README.md            This file
├── _seeds/              Skill definitions
│   ├── install.sh       Run once to install skills
│   ├── seed-ingest/     Raw source → markdown converter
│   ├── seed-compile/    Wiki article builder
│   ├── seed-index/      Index & catalog rebuilder
│   ├── seed-qa/         Question answering from the wiki
│   ├── seed-verify/     Fact checker
│   ├── seed-lint/       Health checker
│   └── seed-visualize/  HTML visualization generator
├── _templates/          Obsidian article templates
├── .obsidian/           Obsidian vault configuration
├── raw/                 Source documents (user-managed)
├── wiki/                Compiled wiki (Claude-managed)
├── viz/                 HTML visualizations (Claude-managed)
└── outputs/             Reports & Q&A outputs (Claude-managed)
```

---

## Workflow

```
1. Ingest  →  raw/ + wiki/sources/
2. Compile →  wiki/concepts/ + wiki/topics/
3. Q&A     →  answers from wiki content
4. Verify  →  fact-check against sources & web
5. Lint    →  fix broken links, add backlinks
6. Visualize → viz/*.html + wiki wrapper pages
7. (loop)  →  explorations file back into wiki
```

Each cycle enriches the wiki. Q&A answers can become new concept articles. Visualizations become graph nodes. Verification adds sourcing depth.

---

## Starting a New Wiki (from scratch)

```bash
git clone <repo-url> new-wiki
cd new-wiki
bash _seeds/install.sh
```

Then in Claude Code, open the folder and say:
> "Initialize this vault for [your topic]. I'll start adding sources."

Claude will set up the index with a vault description and guide you through ingesting your first sources.

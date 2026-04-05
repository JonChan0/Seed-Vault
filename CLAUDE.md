# Seed Vault — Claude Instructions

This is a **Seed Vault** wiki. Claude is the primary author of all wiki content. The user drops source material into `raw/` and directs Claude to build, maintain, and query the wiki. Do not wait for the user to manage wiki files — Claude owns that responsibility.

---

## Directory Conventions

| Directory | Purpose | Who writes |
|-----------|---------|------------|
| `raw/` | Source documents — articles, PDFs converted to .md, web clips | User (Claude never modifies) |
| `wiki/` | All compiled wiki articles | Claude only |
| `wiki/_index.md` | Master index of every article in the wiki | Claude (always keep current) |
| `wiki/_index.base` | Obsidian Bases view of the index (auto-populated from frontmatter) | Do not modify |
| `wiki/_catalog.md` | 2–3 sentence summary of every article (LLM search index) | Claude (always keep current) |
| `wiki/_catalog.base` | Obsidian Bases view of the catalog (auto-populated from frontmatter) | Do not modify |
| `wiki/_migration-log.md` | Record of applied framework migrations | Do not modify (managed by seed-migrate) |
| `wiki/concepts/` | Concept articles synthesized from multiple sources | Claude |
| `wiki/sources/` | One summary per file in `raw/` | Claude |
| `wiki/topics/` | Topic hub pages that cluster related concepts | Claude |
| `viz/` | Self-contained HTML visualizations | Claude |
| `outputs/` | Q&A reports, lint reports, one-off outputs (gitignored — ephemeral) | Claude |
| `_templates/` | Obsidian article templates | Do not modify |
| `_seeds/` | Skill definitions (installed via install.sh) | Do not modify |

---

## Article Frontmatter (REQUIRED on every wiki file)

Every file Claude writes in `wiki/` MUST begin with this frontmatter:

```yaml
---
title: "Article Title"
type: concept | source-summary | topic | visualization | output
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[Source Name]]", "[[Another Source]]"]
tags: [topic/subtopic, another-tag]
status: draft | reviewed | verified
framework_version: "1.0.0"
---
```

- `type` determines how the article is indexed and colored in graph view
- `sources` must use `[[wikilinks]]` — these create graph edges to source summaries
- `tags` should be hierarchical: `#biology/genetics`, `#method/sequencing`
- Update `updated:` every time you modify an article
- `framework_version` tracks which framework version wrote this article — read from `_seeds/VERSION` at write time

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

## The Catalog — Claude's Search Index

`wiki/_catalog.md` is how Claude searches the wiki without reading every file. It must be kept up to date.

**Format for each entry:**
```
### [[Article Title]]
Type: concept | source-summary | topic
Tags: tag1, tag2
Status: draft | reviewed | verified
Summary: 2–3 sentences describing what this article covers and its key claims.
```

**Rule:** After creating or updating ANY article, immediately update both:
1. `wiki/_index.md` — add/update the entry line
2. `wiki/_catalog.md` — add/update the summary block

---

## Index Format

`wiki/_index.md` is organized by type:

```markdown
# Wiki Index

## Concepts
- [[Concept Name]] — one-line description

## Source Summaries
- [[Summary: Source Title]] — one-line description

## Topics
- [[Topic: Topic Name]] — one-line description

## Visualizations
- [[Viz: Visualization Name]] — one-line description

---
*Last updated: YYYY-MM-DD | Total articles: N*
```

---

## Available Skills

Ten skills power this vault. Invoke them by describing what you want:

| Skill | When to use |
|-------|------------|
| `seed-ingest` | "Ingest this PDF/article/URL" — converts raw sources to structured markdown |
| `seed-compile` | "Compile the wiki" / "Write an article about X" — builds concept articles from raw |
| `seed-pipeline` | "Process everything" / "Run the pipeline" — full ingest→compile→index→lint in one pass |
| `seed-index` | "Reindex" / "Rebuild catalog" — regenerates _index.md and _catalog.md |
| `seed-qa` | "What does the wiki say about X?" — researches and answers from wiki content |
| `seed-verify` | "Fact-check this article" — cross-references claims against sources and web |
| `seed-lint` | "Check the wiki health" — finds broken links, orphans, inconsistencies |
| `seed-visualize` | "Visualize X" / "Chart Y" — generates HTML visualizations with wiki wrappers |
| `seed-digest` | "Briefing" / "What's in the wiki?" — generates a status summary of vault contents |
| `seed-migrate` | "Migrate my wiki" / "Apply framework updates" — updates existing articles after a framework version bump |

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

These MCP servers enhance vault capabilities when installed in Claude Code. None are required — all core skills work without them.

| MCP Server | Benefit | Install |
|------------|---------|---------|
| **Brave Search** or **Tavily** | Richer web search in `seed-verify` and `seed-qa` beyond the default WebSearch tool | `claude mcp add brave-search` |
| **Zotero** | Sync your academic reference library — auto-ingest tagged references via `seed-ingest` | Community MCP |
| **GitHub** | Ingest README/docs/wikis from public repos as sources | `claude mcp add github` |
| **Obsidian** | Direct vault read/write without the Claude Code CLI (useful for remote sessions) | Community MCP |
| **PubMed / Semantic Scholar** | Native academic paper lookup in `seed-verify` (free API also works without MCP — see skill) | Community MCP |

Even without MCP servers, `seed-verify` uses free public APIs (Semantic Scholar, CrossRef, Wayback Machine) for external verification. MCP servers add speed and depth.

---

## Initialization Checklist (new vault)

When starting a brand-new vault, before ingesting any sources:
1. Confirm `wiki/_index.md` and `wiki/_catalog.md` exist (create if missing)
2. Ask the user: "What topic/domain is this vault for?" — add a brief vault description to `_index.md`
3. Ask the user: "Do you have sources ready to ingest, or should we start with compilation?"

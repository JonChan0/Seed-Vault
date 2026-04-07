# Article Frontmatter

Every file the LLM writes in `wiki/` must begin with YAML frontmatter. This drives the Obsidian graph view, the search index, and the operation log.

## Required Schema

```yaml
---
title: "Article Title"
type: concept | source-summary | topic | visualization | output
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[Source Name]]", "[[Another Source]]"]
tags: [topic/subtopic, another-tag]
status: draft | reviewed | verified
llm_model: "claude-sonnet-4-6"
framework_version: "2.0.0"
---
```

## Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Human-readable article title (used in index and Obsidian) |
| `type` | Yes | Determines index section and graph node color |
| `created` | Yes | ISO date when the article was first written |
| `updated` | Yes | ISO date of last significant update — always refresh this |
| `sources` | Yes | Wikilinks to source summaries that informed this article |
| `tags` | Yes | Hierarchical tags: `topic/subtopic` (e.g. `biology/genetics`) |
| `status` | Yes | `draft` → `reviewed` → `verified` progression |
| `llm_model` | Yes | Model ID that wrote or last significantly updated this article |
| `framework_version` | Yes | Read from `_vault/VERSION` at write time |

## Type Values

| Type | Index Section | Graph Color | Used For |
|------|--------------|-------------|----------|
| `concept` | Concepts | Blue | Synthesized idea articles |
| `source-summary` | Source Summaries | Green | One summary per `raw/` file |
| `topic` | Topics | Purple | Cluster hub pages |
| `visualization` | Visualizations | Orange | Wrapper pages for HTML viz |
| `output` | Outputs | Gray | Q&A reports, one-offs |

## The `llm_model` Field

Records which model wrote or last significantly updated the article. Use the full model ID from your session context:

```yaml
llm_model: "claude-sonnet-4-6"    # Claude Code (Sonnet)
llm_model: "claude-opus-4-6"      # Claude Code (Opus)
llm_model: "gemini-2.5-pro"       # Gemini CLI (Pro)
llm_model: "gemini-2.5-flash"     # Gemini CLI (Flash)
```

This makes it easy to audit which model produced which content and to re-verify articles after switching models.

## Naming Conventions

- **Concept articles**: `wiki/concepts/concept-name.md` (kebab-case)
- **Source summaries**: `wiki/sources/summary-source-title.md`
- **Topic hubs**: `wiki/topics/topic-name.md`
- **Visualizations (HTML)**: `viz/topic-chart-type.html`
- **Viz wrappers**: `wiki/concepts/viz-topic-name.md`
- **Outputs**: `outputs/type-topic-YYYY-MM-DD.md`

All article titles in `[[wikilinks]]` use Title Case. File names use kebab-case.

## Linking Rules

1. **Always use `[[wikilinks]]`** for internal links — never bare markdown `[text](path)` links
2. **Bidirectional links are mandatory**: if article A links to B, B must link back to A
3. **Every concept article** must reference its source summaries via the `sources:` frontmatter array
4. **Every source summary** must list which concept articles it contributed to under `## Concepts Extracted`
5. **Topic pages** are hub nodes — every concept in a cluster links `[[Topic Hub]]`, and the hub links all members
6. **Section links** `[[Article#Section]]` for precise cross-references

## See Also

- [Architecture](Architecture.md)
- [Obsidian Setup](Obsidian-Setup.md)

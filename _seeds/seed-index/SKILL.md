---
name: seed-index
description: Rebuild or update the Seed Vault wiki index and catalog. Use this skill when the user says "reindex", "rebuild index", "update catalog", "rebuild catalog", "regenerate index", "the index is out of date", or when the wiki has been significantly modified and the index may be stale. Also use after bulk operations that touched many articles at once.
---

# seed-index — Index & Catalog Rebuilder

You are rebuilding the wiki's navigation and search infrastructure. The two key files are:
- `wiki/_index.md` — human-navigable master index organized by type
- `wiki/_catalog.md` — Claude's search index with per-article summaries

These files are how both the user and Claude navigate a large wiki without reading every file.

---

## Step 1: Scan All Wiki Files

```
Glob wiki/**/*.md
```

Collect every `.md` file in `wiki/` except `_index.md` and `_catalog.md` themselves.

For each file, read its frontmatter (the first ~20 lines are sufficient):
- `title`
- `type`
- `tags`
- `status`
- `updated`

Group files by `type`:
- `concept` → Concepts section
- `source-summary` → Source Summaries section
- `topic` → Topics section
- `visualization` → Visualizations section
- `output` → (exclude from index — outputs are ephemeral)
- anything else → Other section

---

## Step 2: For Each Article, Read the Overview

To write catalog summaries, read each article's `## Overview` or first substantive paragraph (skip frontmatter and headings to find the first real content). For source summaries, read `## Key Takeaways`.

You don't need to read the entire article — just enough to write a 2–3 sentence summary.

---

## Step 3: Rebuild _index.md

Write the complete new `wiki/_index.md`:

```markdown
---
title: "Wiki Index"
type: index
updated: {{today}}
---

# Wiki Index

> **Vault topic**: {{if there's a vault description, include it}}
> Total articles: {{N}} | Last rebuilt: {{today}}

## Concepts ({{count}})
{{sorted alphabetically}}
- [[Concept Name]] — {{one-line description from Overview}}
- [[Another Concept]] — {{one-line description}}

## Source Summaries ({{count}})
{{sorted alphabetically by source title}}
- [[Summary: Source Title]] — {{one-line description}}

## Topics ({{count}})
{{sorted alphabetically}}
- [[Topic: Topic Name]] — {{one-line description}}

## Visualizations ({{count}})
{{sorted alphabetically}}
- [[Viz: Visualization Name]] — {{one-line description}}

---
*Last updated: {{today}} | Total articles: {{N}}*
```

One-line descriptions should be tight — capture the core idea in under 15 words.

---

## Step 4: Rebuild _catalog.md

Write the complete new `wiki/_catalog.md`:

```markdown
---
title: "Wiki Catalog"
type: catalog
updated: {{today}}
---

# Wiki Catalog

> This file is Claude's search index. Read this first when answering questions.
> Total entries: {{N}} | Last rebuilt: {{today}}

---

{{for each article, sorted alphabetically within each type group}}

## Concepts

### [[Concept Name]]
Type: concept
Tags: tag1, tag2
Summary: {{2–3 sentences}}. Covers {{key aspect}}. Connected to [[Related Concept]] and [[Another]].

### [[Another Concept]]
...

## Source Summaries

### [[Summary: Source Title]]
Type: source-summary
Tags: tag1, tag2
Summary: {{2–3 sentences describing the source, its main claims, and what concepts it informs}}.

## Topics

### [[Topic: Topic Name]]
Type: topic
Tags: topic-tag
Summary: {{2–3 sentences describing the topic cluster and which concepts it groups}}.

## Visualizations

### [[Viz: Visualization Name]]
Type: visualization
Tags: visualization, topic
Summary: {{2–3 sentences describing what is visualized and what insight it provides}}.
```

Catalog summaries should include:
- What the article covers
- 1–2 key claims or findings
- Key connections (mention 1–2 `[[linked articles]]`)

---

## Step 5: Generate Statistics Report

After rebuilding, report:

```
Index rebuilt: {{today}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Concepts:           {{N}}
Source Summaries:   {{N}}
Topics:             {{N}}
Visualizations:     {{N}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total articles:     {{N}}

Most-linked articles (potential hub nodes):
  1. [[Article]] — linked from N articles
  2. [[Article]] — linked from N articles
  3. [[Article]] — linked from N articles

Articles with no incoming links (orphans):
  - [[Article]]
  - [[Article]]
  (Run seed-lint to add backlinks)

Suggested new topic hubs (3+ concepts share a tag):
  - "{{Tag Name}}" → {{N}} concepts
```

To find most-linked articles, use Grep to count occurrences of each `[[Title]]` across all wiki files.
To find orphans, check which titles from the index appear in no other file's body text.

---
name: vault-compile
description: Compile and build the wiki from raw sources. Use when the user says "compile", "build the wiki", "write an article about X", "create a concept page for X", "update the wiki", "rebuild", "generate articles", or asks to turn raw sources into wiki content. This is the core wiki-building skill — it reads raw sources and source summaries, extracts concepts, and writes interconnected Obsidian articles with backlinks.
---

# vault-compile — Wiki Compilation Engine

You are building or updating the Seed Vault wiki. Your job is to synthesize raw source material into interconnected, well-linked markdown articles that form a rich knowledge graph in Obsidian.

There are two modes:
- **Full compile**: Process all uncompiled sources and build/update all articles
- **Targeted compile**: Write or update a specific article the user named

---

## Pre-Compile: Assess the State

Before writing anything:

1. Read `_vault/VERSION` — note the version string for the `framework_version:` field
2. Read `wiki/_index.md` — see the current wiki structure
3. `Glob wiki/sources/*.md` — list all source summaries
4. `Glob raw/*` — list all raw sources
5. Use `qmd query "{{topic}}"` if available, or read source summaries directly to identify which concepts need articles
6. Identify which source summaries are missing concept articles (check "Concepts Extracted" sections)

Report what you found: "Found N source summaries. X concept articles exist. Y new concepts need articles: [list]"

---

## Article Writing: Concept Articles

For each concept that needs an article, or when the user names a specific concept:

### Structure

Write `wiki/concepts/{{concept-name}}.md`:

```markdown
---
title: "{{Concept Name}}"
type: concept
created: {{today}}
updated: {{today}}
sources: ["[[Summary: Source Title]]", "[[Summary: Another Source]]"]
tags: [{{topic/subtopic}}, {{another-tag}}]
status: draft
aliases: ["{{alternate name}}", "{{abbreviation}}"]
framework_version: "{{read from _vault/VERSION}}"
---

# {{Concept Name}}

## Overview
*(2–3 paragraph synthesis — what this concept is, why it matters, key defining characteristics)*

## Key Details

### {{Aspect 1}}
*(Detailed explanation with inline citations: "According to [[Summary: Source Title]], ...")*

### {{Aspect 2}}
...

## Current State / Recent Developments
*(What's the latest understanding? Any active debates?)*

## Connections

### Related Concepts
- [[Related Concept A]] — *(one-line relationship description)*
- [[Related Concept B]] — *(one-line relationship description)*

### Part of Topics
- [[Topic: Parent Topic]]

### See Also
- [[Another Concept]]

## Source Material
*(Sources that inform this article)*
- [[Summary: Source Title]] — *(what this source contributes)*
- [[Summary: Another Source]] — *(what this source contributes)*
```

### Linking Rules — Non-Negotiable

1. **`sources:` frontmatter** must list every source summary that contributed
2. **Inline `[[wikilinks]]`** throughout the text whenever another concept is mentioned
3. **"Related Concepts"** section must have at least 2 links (if the wiki has other concepts)
4. **"Part of Topics"** — link to the relevant topic hub page (create it if it doesn't exist)
5. After writing this article, update the corresponding source summaries to add this concept under `## Concepts Extracted`

---

## Article Writing: Topic Hub Pages

Topic hubs are cluster pages that connect groups of related concepts. Create them when you see 3+ concepts that belong to the same domain.

Write `wiki/topics/{{topic-name}}.md`:

```markdown
---
title: "Topic: {{Topic Name}}"
type: topic
created: {{today}}
updated: {{today}}
sources: []
tags: [{{topic}}]
status: draft
framework_version: "{{read from _vault/VERSION}}"
---

# Topic: {{Topic Name}}

## Overview
*(What is this topic area? What questions does it address?)*

## Key Concepts

### Core Concepts
- [[Concept A]] — *(one-line description)*
- [[Concept B]] — *(one-line description)*
- [[Concept C]] — *(one-line description)*

### Supporting Concepts
- [[Concept D]] — *(one-line description)*

## Recommended Reading Order
*(For someone new to this topic — list concepts from foundational to advanced)*
1. [[Foundational Concept A]] — start here
2. [[Concept B]] — builds on A
3. [[Advanced Concept C]] — requires A and B

## Key Sources
*(Primary sources in this topic area)*
- [[Summary: Source Title]]

## Open Questions
*(What's unknown, debated, or worth exploring further?)*
- {{At least one open question — never leave this empty}}

## See Also
- [[Topic: Related Topic]]
```

---

## Updating Existing Articles

When a new source is ingested that adds to an existing concept:

1. Read the existing article
2. Identify new information from the source summary
3. Use Edit to:
   - Add new information to the relevant sections
   - Add the new source to the `sources:` frontmatter
   - Add `[[Summary: New Source]]` to the "Source Material" section
   - Update `updated:` date
4. Update the source summary to backlink to this concept

---

## Backlink Maintenance

After writing or updating any article, perform backlink checks:

1. For every `[[Wikilink]]` added to the new article, check if that target article exists
2. If it exists: read it and add the reverse link if missing
3. If it doesn't exist yet: note it as an unresolved link (OK — will be created later)

---

## Update Index

After creating or updating articles, rebuild the index:

```bash
uv run python _vault/lib/index.py
```

Or manually update `wiki/_index.md` with entries in the correct section.

---

## Post-Compile Report

After compilation, report:
- Articles created: [list]
- Articles updated: [list]
- Unresolved links (concepts mentioned but no article yet): [list]
- Suggested topic hubs to create: [list]
- Suggested next action: "Run `vault-lint` to check for broken links and orphan pages."

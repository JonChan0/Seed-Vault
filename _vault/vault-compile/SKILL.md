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
5. Use `qmd query "{{concept}}"` if available, or read source summaries directly to identify which concepts need articles
6. Identify which source summaries are missing concept articles (check "Concepts Extracted" sections)

Report what you found: "Found N source summaries. X concept articles exist. Y new concepts need articles: [list]"

---

## Web Verification Step (NEW ARTICLES ONLY)

Before writing any **new** concept article, run 1–3 targeted WebSearches to independently ground the synthesis. This is mandatory — do not skip it.

### Search strategy
1. Search the concept name + domain (e.g. `"CRISPR base editing mechanism"`)
2. Search for any quantitative claims that appear in the raw sources (e.g. `"CRISPR efficiency rate 2024"`)
3. If the concept is contested or rapidly evolving, search for the current consensus (e.g. `"CRISPR off-target effects debate 2024"`)

### What to do with results
- Collect the URLs and titles of sources that corroborate, contradict, or extend what the raw sources say
- For each claim in the article that is **supported or qualified** by a web result: append an inline `[^web-N]` marker (numbered sequentially)
- Add a `## External References` section at the end of the article listing each footnote
- Populate the `web_sources:` frontmatter field with every URL consulted (even if it only confirmed the raw source was correct)
- If a web result **contradicts** a raw source claim, flag the sentence with `[^web-N]` and note the discrepancy in the footnote: `[^web-1]: Contradicted by [Title](URL) — ...`

### Flagging rules
- `[^web-N]` markers go **inline, immediately after the claim they support** — not at the end of paragraphs
- Every `[^web-N]` must have a matching entry in `## External References`
- If WebSearch returns no useful results for a concept, add `web_sources: []` and a note: `> **Note:** No independent web sources found for this concept — based solely on vault raw sources.`
- **Do not add `[^web-N]` to information that comes purely from the raw sources with no web corroboration** — that path is already covered by `[[wikilink]]` inline citations

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
sources: ["[[summary-source-title|Summary - Source Title]]", "[[summary-another-source|Summary - Another Source]]"]
tags: [{{concept/subconcept}}, {{another-tag}}]
status: draft
aliases: ["{{alternate name}}", "{{abbreviation}}"]
llm_model: "{{your model ID, e.g. claude-sonnet-4-6 or gemini-3-pro}}"
framework_version: "{{read from _vault/VERSION}}"
web_sources: ["{{url-1}}", "{{url-2}}"]
---

# {{Concept Name}}

## Overview
*(2–3 paragraph synthesis — what this concept is, why it matters, key defining characteristics)*

## Key Details

### {{Aspect 1}}
*(Detailed explanation with inline citations: "According to [[summary-source-title|Summary - Source Title]], ..." and web-verified claims marked [^web-N])*

### {{Aspect 2}}
...

## Current State / Recent Developments
*(What's the latest understanding? Any active debates?)*

## Connections

### Related Concepts
- [[related-concept-a|Related Concept A]] — *(one-line relationship description)*
- [[related-concept-b|Related Concept B]] — *(one-line relationship description)*

### See Also
- [[another-concept|Another Concept]]

## Source Material
*(Sources that inform this article)*
- [[summary-source-title|Summary - Source Title]] — *(what this source contributes)*
- [[summary-another-source|Summary - Another Source]] — *(what this source contributes)*

## External References
*(Web sources consulted during compilation — numbered to match [^web-N] inline markers)*
[^web-1]: [Title](URL) — *(what this source confirmed, extended, or contradicted)*
[^web-2]: [Title](URL) — *(what this source confirmed, extended, or contradicted)*
```

### Linking Rules — Non-Negotiable

1. **`sources:` frontmatter** must list every source summary that contributed
2. **Inline `[[wikilinks]]`** throughout the text whenever another concept is mentioned
3. **"Related Concepts"** section must have at least 2 links (if the wiki has other concepts)
4. After writing this article, update the corresponding source summaries to add this concept under `## Concepts Extracted`

---

## Updating Existing Articles

When a new source is ingested that adds to an existing concept:

1. Read the existing article
2. Identify new information from the source summary
3. Use Edit to:
   - Add new information to the relevant sections
   - Add the new source to the `sources:` frontmatter
   - Add `[[summary-new-source|Summary - New Source]]` to the "Source Material" section
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

This rewrites `wiki/_index.md` from scratch — do not edit the index manually.

---

## Post-Compile Report

After compilation, report:
- Articles created: [list]
- Articles updated: [list]
- Web sources consulted: [total count across all new articles]
- Claims flagged with `[^web-N]`: [total count] — note any contradictions found
- Articles with no web sources found: [list] — these are raw-source-only and should be treated as lower confidence
- Unresolved links (concepts mentioned but no article yet): [list]
- Suggested next action: "Run `vault-lint` to check for broken links and orphan pages."

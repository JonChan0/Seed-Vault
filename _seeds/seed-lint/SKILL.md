---
name: seed-lint
description: Run health checks on the Seed Vault wiki to find structural issues and opportunities. Use this skill when the user says "lint", "health check", "check the wiki", "find issues", "find broken links", "find orphan pages", "find inconsistencies", "suggest improvements", "what's missing", "audit the wiki", "clean up the wiki", or wants to improve wiki quality and connectivity. Can auto-fix simple issues or just report them.
---

# seed-lint — Wiki Health Checker

You are auditing the Seed Vault wiki for structural issues, broken connections, and enhancement opportunities. The goal is a well-connected graph with no dead ends, no isolated nodes, and no contradictions.

---

## Pre-Lint: Load the Wiki

1. Read `wiki/_index.md` — get the full list of all articles
2. Read `wiki/_catalog.md` — understand what each article covers
3. `Glob wiki/**/*.md` — get every file path

Build a mental map: all article titles, all file paths.

---

## Check 1: Broken Wikilinks

Find `[[wikilinks]]` that point to articles that don't exist.

Method:
```
Grep pattern="\[\[" path="wiki/" glob="*.md" output_mode="content"
```

For each `[[Link Target]]` found:
- Check if an article with that title exists in the wiki
- If not, mark as broken

**Auto-fix option**: Ask user — "Should I create stub articles for these unresolved links?" A stub article:
```markdown
---
title: "{{Title}}"
type: concept
created: {{today}}
updated: {{today}}
sources: []
tags: []
status: draft
---

# {{Title}}

*Stub — this article was created as a placeholder. Run seed-compile to fill it in.*
```

---

## Check 2: Orphan Pages

Find articles with no incoming links — isolated nodes in the graph.

**Single-pass method** (efficient for large wikis):
1. Run one Grep sweep across all wiki files to collect every `[[wikilink]]` mentioned:
   ```
   Grep pattern="\[\[([^\]]+)\]\]" path="wiki/" glob="*.md" output_mode="content"
   ```
2. Build a frequency map: count occurrences of every `[[Title]]` across all files
3. For each article title in the file list, check if its title appears 0 times in the frequency map → orphan

This is one grep instead of N greps.

**Auto-fix option**: For each orphan, identify which topic hub it should belong to based on its tags/content. Add it to the hub and add the hub backlink to the orphan.

---

## Check 3: Missing Backlinks

Find one-directional links that should be bidirectional.

**Reuse the frequency map from Check 2.** For each link `A → B` found in the sweep:
- Verify that B's file content contains `[[A]]` somewhere (frontmatter sources, body, See Also)
- If not, flag as missing backlink — do NOT re-grep per article; use the already-collected link data

**Auto-fix option**: Add missing backlinks. For concept→concept: add to "See Also" or "Related Concepts". For concept→source: add to source's "Concepts Extracted". Ask user before auto-fixing if there are >10 fixes.

---

## Check 4: Stale Articles

Find articles whose `updated:` date is older than their sources' `updated:` dates.

For each article:
- Read its `updated:` date from frontmatter
- Read `updated:` dates of all its linked source summaries
- If a source was updated more recently: flag as potentially stale

Report: "[[Article]] was last updated {{date}} but [[Summary: Source]] was updated {{later date}}."

---

## Check 5: Missing Concepts

Find concepts mentioned frequently in the wiki that don't have dedicated articles.

Method:
```
Grep pattern="\[\[(?!Summary:|Topic:|Viz:)" path="wiki/" glob="*.md"
```

Count occurrences of each `[[Link]]`. Links that appear 3+ times across multiple articles but have no article file are high-priority missing concepts.

---

## Check 6: Tag Hygiene

Find tag inconsistencies:

- Tags used only once (possibly a typo or over-specific)
- Tags that could be merged (e.g., `biology` and `bio`)
- Articles with no tags at all
- Articles with tags that don't follow the `topic/subtopic` hierarchy

Method: Read all frontmatter tags, compile a frequency table.

---

## Check 7: Catalog Sync

Verify that `_catalog.md` and `_index.md` are in sync with the actual wiki files:

- Articles that exist but are missing from `_index.md`
- Articles in `_index.md` that no longer have files
- Articles that exist but are missing from `_catalog.md`

**Auto-fix**: These are always safe to auto-fix — run seed-index to fully rebuild. Ask: "The index has {{N}} sync issues. Should I run seed-index to rebuild it?"

---

## Check 8: Topic Hub Coverage

Find concept articles not connected to any topic hub.

Method: Check each concept article's "Part of Topics" section and `[[Topic:` links. Concepts with no topic hub links are floating in the graph without a cluster.

Suggest: "These {{N}} concepts have no topic hub. Suggested groupings: [cluster by shared tags]"

---

## Check 9: Raw Source Coverage

Find files in `raw/` that have no corresponding source summary in `wiki/sources/`.

Method:
1. `Glob raw/*.md` — collect all raw file names (strip `raw/` prefix and `.md` suffix)
2. `Glob wiki/sources/*.md` — collect all summary file names (strip `summary-` prefix)
3. For each raw file name, check if a summary exists with matching base name
4. Flag any raw file with no matching summary as unsummarized

**Auto-fix**: Always auto-fixable — run `seed-ingest` on the flagged raw files to generate summaries.

---

## Lint Report

Save `outputs/lint-{{today}}.md`:

```markdown
---
title: "Lint Report: {{today}}"
type: output
created: {{today}}
tags: [output, lint]
---

# Wiki Lint Report — {{today}}

## Summary
| Check | Issues Found | Auto-fixable |
|-------|-------------|--------------|
| Broken wikilinks | {{N}} | Yes (create stubs) |
| Orphan pages | {{N}} | Yes (add to topic hubs) |
| Missing backlinks | {{N}} | Yes |
| Stale articles | {{N}} | No (needs content update) |
| Missing concept articles | {{N}} | Yes (create stubs) |
| Tag hygiene | {{N}} | No (needs review) |
| Catalog sync | {{N}} | Yes (run seed-index) |
| Unhubbed concepts | {{N}} | Yes |
| Unsummarized raw files | {{N}} | Yes (run seed-ingest) |

## Issues Detail

### 🔴 Broken Wikilinks
| Article | Broken Link |
|---------|------------|
| [[Article]] | [[Missing Target]] |

### 🟠 Orphan Pages (no incoming links)
- [[Article]] — tags: {{tags}}, suggested hub: {{Topic}}

### 🟡 Missing Backlinks
| Article A links to | Missing reverse link in |
|-------------------|------------------------|
| [[A]] → [[B]] | [[B]] needs → [[A]] |

### 🟡 Stale Articles
| Article | Last updated | Source updated |
|---------|-------------|----------------|
| [[Article]] | {{date}} | [[Source]] {{later date}} |

### 🟢 Missing Concept Articles (high-frequency links)
| Concept | Times referenced | Suggested sources |
|---------|-----------------|-------------------|
| [[Concept]] | {{N}} | [[Summary: Source]] |

### 🔵 Tag Issues
{{list}}

### 🔵 Unhubbed Concepts
{{list with suggested topic groupings}}

### 🟠 Unsummarized Raw Files (no wiki/sources/ entry)
- `raw/{{filename}}.md` — run seed-ingest to generate summary

## Recommended Actions
1. {{Most urgent fix}}
2. {{Second priority}}
3. {{Third priority}}
```

After generating the report, ask: "Should I auto-fix the {{N}} auto-fixable issues? (broken link stubs, missing backlinks, catalog sync)"

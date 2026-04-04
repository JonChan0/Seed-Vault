---
name: seed-digest
description: Generate a status briefing and summary of the Seed Vault wiki. Use this skill when the user says "briefing", "status report", "what's in the wiki", "what do we have", "wiki summary", "overview of the vault", "what have we collected", "what's been updated recently", "show me the state of the wiki", or wants a high-level orientation to the vault contents without asking a specific question.
---

# seed-digest — Wiki Status Briefing

You are generating an orientation briefing of the Seed Vault wiki. The goal is to give the user a clear picture of what the vault currently contains, what's been added recently, where the knowledge is strongest, and what gaps remain.

---

## Step 1: Frontmatter Scan (statistics, dates, tags)

All counts, statuses, dates, and tags live in frontmatter — read only the first ~15 lines of each article file rather than full content or the catalog.

```
Glob wiki/**/*.md
```

Exclude `_index.md`, `_catalog.md`, `_index.base`, `_catalog.base`.

For each file, read just the frontmatter block (lines 1–15 are sufficient for all YAML fields). Extract:
- `type` → count by type (concept, source-summary, topic, visualization)
- `status` → tally verified / reviewed / draft per type
- `tags` → collect all tags for domain mapping
- `updated` → collect all dates for recency and staleness
- `created` → collect for "recently added" detection

This replaces reading `_catalog.md` for everything statistical. The catalog is only needed for topic summaries (Step 4).

Build from this scan:
- Total articles by type
- Status distribution per type
- Tag frequency table (domains/topics covered)
- Sorted date lists for Steps 2 and 3

---

## Step 2: Find Recently Updated and Oldest Content

Using the `updated:` and `created:` dates collected in Step 1:

- **Recently updated (last 7 days)**: Articles where `updated:` ≥ today minus 7 days
- **Recently added (last 30 days)**: Articles where `created:` ≥ today minus 30 days
- **Oldest articles**: The 3 articles with the earliest `updated:` dates (staleness candidates)

No additional file reads needed — all data already collected in Step 1.

---

## Step 3: Find Hub Nodes

Hub nodes are the most-connected articles — they're the conceptual backbone of the wiki.

Run one Grep sweep across all wiki files to collect every `[[wikilink]]`:
```
Grep pattern="\[\[([^\]]+)\]\]" path="wiki/" glob="*.md" output_mode="content"
```

Build a frequency map: count occurrences of every `[[Title]]` across all files. The top 5 most-referenced titles are the hub nodes.

---

## Step 4: Identify Knowledge Gaps

1. **Unresolved links**: From the frequency map in Step 3, find titles that appear in `[[wikilinks]]` but have no corresponding file in the glob results from Step 1 — these are missing articles (red nodes in Obsidian graph)
2. **Draft-heavy areas**: From the Step 1 tag+status data, find tag clusters where most articles are `status: draft`
3. **Source-only zones**: Tag groups that have source-summary entries but no concept articles — suggest `seed-compile`
4. **Missing topic hubs**: Groups of 3+ concepts sharing a tag but no topic hub page

For the **Topics Covered** section of the briefing, read `wiki/_catalog.md` now — specifically to get the 2–3 sentence summaries that give meaningful domain context. This is the only part of the digest that needs catalog content.

---

## Step 5: Generate the Briefing

Output the briefing directly (no output file needed unless user asks to save it):

```
# Wiki Briefing — {{today}}

## Contents at a Glance
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Concept articles:      {{N}} ({{N}} verified, {{N}} reviewed, {{N}} draft)
Source summaries:      {{N}}
Topic hubs:            {{N}}
Visualizations:        {{N}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total:                 {{N}} articles

## Topics Covered
{{List of tags/domains in use, grouped — e.g., "biology/genetics (12 articles), method/sequencing (7), ...}}

## Recently Updated (last 7 days)
{{list, or "Nothing updated in the last week"}}

## Recently Added (last 30 days)
{{list of new articles, or "Nothing new in the last month"}}

## Hub Articles (most-referenced)
1. [[Article A]] — referenced by {{N}} other articles
2. [[Article B]] — referenced by {{N}} other articles
3. [[Article C]] — referenced by {{N}} other articles

## Knowledge Gaps
### Unresolved Links (concepts mentioned but no article)
{{list of [[wikilinks]] with no file, or "None — wiki is fully connected"}}

### Draft-heavy areas
{{tag clusters with mostly draft articles — suggest verification}}

### Source-only zones (no compiled concepts)
{{topics with sources but no concept articles — suggest seed-compile}}

## Oldest Articles (may need review)
- [[Article]] — last updated {{date}}
- [[Article]] — last updated {{date}}

## Suggested Next Actions
1. {{Most impactful action — e.g., "Compile {{N}} uncompiled sources in {{domain}}"}}
2. {{Second suggestion — e.g., "Verify {{N}} draft articles in {{domain}}"}}
3. {{Third suggestion — e.g., "Run seed-lint for a full health check"}}
```

---

## Step 6: Save if Requested

If the user wants to save the briefing:

Save to `outputs/digest-{{today}}.md` with frontmatter:
```yaml
---
title: "Wiki Digest: {{today}}"
type: output
created: {{today}}
tags: [output, digest]
---
```

Otherwise, deliver the briefing inline as a response — no file needed.

---

## Notes

- **Fast**: Statistics come from a lightweight frontmatter scan (first ~15 lines per file) + one Grep sweep. The full catalog is only read for topic summary context — and skipped entirely if the user just wants counts/dates.
- **No dependency on catalog currency**: The frontmatter scan reads source-of-truth data directly from article files, so the digest is accurate even if `_catalog.md` is stale. If the catalog is missing or outdated, note it and suggest running `seed-index`.
- **Tone**: Informative and actionable — each gap identified should come with a suggested skill to address it.

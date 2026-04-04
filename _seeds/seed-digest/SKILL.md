---
name: seed-digest
description: Generate a status briefing and summary of the Seed Vault wiki. Use this skill when the user says "briefing", "status report", "what's in the wiki", "what do we have", "wiki summary", "overview of the vault", "what have we collected", "what's been updated recently", "show me the state of the wiki", or wants a high-level orientation to the vault contents without asking a specific question.
---

# seed-digest — Wiki Status Briefing

You are generating an orientation briefing of the Seed Vault wiki. The goal is to give the user a clear picture of what the vault currently contains, what's been added recently, where the knowledge is strongest, and what gaps remain.

---

## Step 1: Load the Index and Catalog

1. Read `wiki/_index.md` in full — get article counts and lists by type
2. Read `wiki/_catalog.md` in full — get summaries and status of every article

Build a mental inventory:
- Total articles by type (concepts, sources, topics, visualizations)
- Status distribution: how many are `verified`, `reviewed`, `draft`
- Tags in use (from catalog entries) — what domains/topics are covered

---

## Step 2: Find Recently Updated Content

From the catalog, read the `updated:` dates of all articles. Identify:
- **Last 7 days**: Articles updated within the past week
- **Last 30 days**: Articles updated within the past month
- **Oldest articles**: The 3 articles with the oldest `updated:` dates (candidates for review)

If `updated:` dates are unavailable in the catalog, use `Glob wiki/**/*.md` and note that date tracking requires articles to maintain their frontmatter.

---

## Step 3: Find Hub Nodes

Hub nodes are the most-connected articles — they're the conceptual backbone of the wiki.

Method: Use the frequency map approach — scan `wiki/_catalog.md` for `[[wikilinks]]` referenced in summaries, or do a quick Grep:
```
Grep pattern="\[\[([^\]]+)\]\]" path="wiki/" glob="*.md" output_mode="content"
```

Identify the top 5 most-referenced articles (titles appearing most often in other articles' link sections).

---

## Step 4: Identify Knowledge Gaps

From the catalog and index:
1. **Unresolved links**: Grep for `[[wikilinks]]` that appear in articles but have no corresponding file (these show as red nodes in Obsidian graph)
2. **Draft-heavy areas**: Tag clusters where most articles are `status: draft`
3. **Source-only zones**: Topics with source summaries but no concept articles compiled yet
4. **Missing topic hubs**: Groups of 3+ concepts sharing a tag but no topic hub page

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

- **Fast**: This skill reads only `_index.md` and `_catalog.md` plus one optional Grep — it doesn't read individual articles
- **Honest about gaps**: If the catalog is sparse or outdated, say so and suggest running `seed-index` first
- **Tone**: Informative and actionable — each gap identified should come with a suggested skill to address it

---
name: seed-verify
description: Fact-check and verify wiki articles in the Seed Vault. Use this skill when the user says "verify", "fact check", "check facts in", "validate", "is this accurate", "cross-reference", "check for errors", "verify the wiki", or when they ask whether a specific claim in an article is correct. Can verify a single article, a set of articles, or all draft articles.
---

# seed-verify — Fact Checking & Verification

You are verifying claims in Seed Vault wiki articles. Your job is to cross-reference facts against primary sources (in `raw/` and `wiki/sources/`), flag contradictions, and use web search for external validation where needed.

---

## Step 1: Identify What to Verify

**Single article**: User named it — read it directly
**Multiple articles**: User listed them — read each
**All drafts**: `Glob wiki/**/*.md`, read frontmatter, collect all with `status: draft`
**Whole wiki**: All articles regardless of status

If verifying many articles, ask: "There are {{N}} articles to verify. This may take a while. Should I proceed, or focus on a specific topic?"

---

## Step 2: For Each Article — Extract Verifiable Claims

Read the article and identify:

**Hard claims** (specific, falsifiable):
- Statistics, percentages, measurements
- Dates, timelines, sequences of events
- Attribution ("X said Y", "X discovered Y")
- Causal claims ("X causes Y")
- Comparative claims ("X is larger/faster/more effective than Y")

**Soft claims** (contextual, harder to verify):
- Characterizations ("X is widely used")
- Consensus statements ("most researchers believe")
- Trend claims ("X has been increasing")

List each claim with the sentence it appears in.

---

## Step 3: Cross-Reference Against Wiki Sources

For each hard claim:

1. Check which sources are listed in the article's `sources:` frontmatter
2. Read those source summaries in `wiki/sources/`
3. Read the corresponding raw files if needed for specific quotes/data
4. Mark each claim:
   - ✅ **Supported**: Claim matches source
   - ⚠️ **Partially supported**: Source mentions topic but doesn't confirm exact claim
   - ❌ **Contradicted**: Source says something different
   - ❓ **Unsourced**: No source in the wiki covers this claim

---

## Step 4: External Verification (for ❓ and ❌ claims)

**Prioritization order**: Always resolve ❌ contradictions first, then ❓ unsourced claims. Stop external lookups when only ⚠️ weak-support flags remain, or after 10 external lookups — whichever comes first.

**Skip already-verified claims**: If the article's frontmatter has a `verified_claims:` list, skip those claims and only process new or changed ones.

For **scientific/academic claims**, use Semantic Scholar (free, no API key needed):
```
WebFetch https://api.semanticscholar.org/graph/v1/paper/search?query={{url-encoded claim keywords}}&fields=title,abstract,year,citationCount&limit=3
```
Parse the JSON: look for papers with high citation counts that support or contradict the claim. Note evidence strength (single study vs. meta-analysis).

For **factual/historical claims**, try Wikipedia first:
```
WebFetch https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&titles={{url-encoded topic}}&format=json
```

For **general web verification**, use WebSearch:
```
WebSearch: "{{claim keywords}}" {{context}}
```

If a source URL is dead (404/timeout), try the Wayback Machine before marking it unavailable:
```
WebFetch https://web.archive.org/web/2*/{{dead-url}}
```

If MCP PubMed, Consensus, or Brave Search is installed, prefer those over WebSearch for scientific claims — they return structured results.

---

## Step 5: Write Verification Notes

Add a `## Verification` section to the article (or update if it exists):

```markdown
## Verification
*Last verified: {{today}} by seed-verify*

### ✅ Supported Claims
- "{{claim}}" — confirmed by [[Summary: Source]] and external search

### ⚠️ Weakly Supported
- "{{claim}}" — [[Summary: Source]] mentions this topic but doesn't confirm the specific figure. Consider finding a primary source.

### ❌ Contradictions Found
- "{{claim}}" — [[Summary: Source]] actually states {{what the source says}}. **Needs correction.**

### ❓ Unsourced Claims
- "{{claim}}" — No wiki source covers this. External search suggests {{finding}}. Consider ingesting a supporting source.

### Notes
{{Any broader observations about the article's accuracy}}
```

Update the article's `status:` frontmatter:
- All claims supported → `status: verified`
- Any ❌ or ❓ → `status: draft` (leave for user to resolve)
- Only ⚠️ warnings → `status: reviewed`

---

## Step 6: Generate Verification Report

Save `outputs/verification-{{today}}.md`:

```markdown
---
title: "Verification Report: {{today}}"
type: output
created: {{today}}
tags: [output, verification]
---

# Verification Report — {{today}}

## Summary
- Articles verified: {{N}}
- Fully verified: {{N}}
- Needs attention: {{N}}
- Contradictions found: {{N}}

## Issues Requiring Action

### ❌ Contradictions
| Article | Claim | Issue |
|---------|-------|-------|
| [[Article]] | "{{claim}}" | Contradicts [[Source]] which says... |

### ❓ Unsourced Claims
| Article | Claim | Suggested action |
|---------|-------|-----------------|
| [[Article]] | "{{claim}}" | Ingest {{type of source}} |

## Verified Articles
{{list of articles now marked verified}}

## Recommended Sources to Ingest
*(To resolve unsourced claims)*
- {{Source type/topic}} — would resolve claims in [[Article A]], [[Article B]]
```

---

## Verification Scope Notes

- **Trust raw/ sources**: Content in `raw/` is treated as authoritative primary source material
- **Prioritize contradictions**: ❌ flags are most urgent — they indicate a wiki error
- **Don't over-verify**: Soft claims like "widely used" don't need a citation if the domain context supports them
- **Scientific claims**: Flag anything from single studies as ⚠️ unless multiple sources agree
- **Quick mode**: If the user says "quick verify" or "internal only", skip Step 4 entirely — only do internal source cross-reference (Steps 2–3). Useful for checking consistency without burning web lookups.
- **Track verified claims**: After a successful verification run, add `verified_claims: [{{list of verified claim fingerprints}}]` to the article frontmatter so repeat runs skip them.

---

## MCP Integrations for Verification

The following free APIs work without any MCP server (use WebFetch):

| Source | URL pattern | Best for |
|--------|-------------|----------|
| **Semantic Scholar** | `https://api.semanticscholar.org/graph/v1/paper/search?query={{query}}&fields=title,abstract,year,citationCount&limit=3` | Academic/scientific claims |
| **CrossRef DOI** | `https://api.crossref.org/works/{{doi}}` | Validating specific paper metadata |
| **Wikipedia API** | `https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&titles={{topic}}&format=json` | Factual/historical claims |
| **Wayback Machine** | `https://web.archive.org/web/2*/{{url}}` | Recovering dead source URLs |
| **PubMed E-utils** | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={{query}}&retmode=json` | Medical/biology claims |

If MCP servers are installed:
- **Brave Search / Tavily MCP**: More reliable than WebSearch for current events
- **PubMed MCP**: Structured access to MEDLINE database
- **Consensus MCP**: AI-synthesized scientific consensus on a claim

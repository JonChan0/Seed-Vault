---
name: vault-verify
description: Fact-check and verify wiki articles. Use when the user says "verify", "fact check", "check facts in", "validate", "is this accurate", "cross-reference", "check for errors", "verify the wiki", or when they ask whether a specific claim is correct. Can verify a single article, a set of articles, or all draft articles. Uses a clean-context subagent to prevent confirmation bias.
---

# vault-verify — Fact Checking & Verification

You are verifying claims in Seed Vault wiki articles. This skill uses a **deterministic-first** approach: extract claims and match against sources programmatically, then use an LLM subagent with no prior context for semantic verification.

---

## Step 1: Identify What to Verify

**Single article**: User named it — note the path
**Multiple articles**: User listed them — note all paths
**All drafts**: `Glob wiki/**/*.md`, read frontmatter, collect all with `status: draft`
**Whole wiki**: All articles regardless of status

If verifying many articles, ask: "There are {{N}} articles to verify. This may take a while. Should I proceed?"

---

## Step 2: Run Deterministic Claim Extraction

For each article, run the verification engine:

```bash
uv run python _vault/lib/verify.py "{{article_path}}" --json
```

This:
1. Extracts verifiable claims (percentages, years, measurements, dollar amounts, named numbers)
2. Resolves source files from frontmatter `sources:` field
3. Matches claims against raw source text (exact and fuzzy matching)
4. Reports: `{claim_text, value, type, source_file, match_type, matched_text, score}`

Read the JSON output. Note claims with `match_type: "none"` — these are unsourced.

---

## Step 3: Launch Clean-Context Verification Subagent

**Critical**: Do NOT verify claims yourself in this conversation. Instead, launch a subagent with empty context to prevent confirmation bias.

Use `Agent(subagent_type="general-purpose")` with this prompt structure:

```
You are a fact-checker. You have NO prior context about this wiki or its creation.
You must evaluate claims purely based on the evidence provided.

ARTICLE TO VERIFY:
[paste full article content]

AUTOMATED SOURCE MATCH REPORT:
[paste verify.py JSON output]

RAW SOURCE FILES:
[paste content of each referenced raw/ file]

TASKS:
1. For each claim flagged as "none" (no source match), assess whether the raw sources
   actually support it through context or implication — the automated matcher may miss
   semantic matches
2. For each claim flagged as "partial", assess if the match is strong enough to consider supported
3. Flag any claims that CONTRADICT the raw sources as CONTRADICTED
4. Flag truly unsupported claims as UNSUPPORTED
5. Check for claims the automated tool missed (qualitative claims, causal statements, attributions)
6. Rate overall article confidence: HIGH / MEDIUM / LOW
7. Output a structured verification report
```

---

## Step 4: Process Verification Results

Read the subagent's report. For each article:

### Update the article with verification notes

Add or update a `## Verification` section:

```markdown
## Verification
*Last verified: {{today}} by vault-verify*

### ✅ Supported Claims
- "{{claim}}" — confirmed by [[Summary - Source]] and source matching

### ⚠️ Weakly Supported
- "{{claim}}" — source mentions topic but doesn't confirm specific figure

### ❌ Contradictions Found
- "{{claim}}" — source actually states {{what source says}}. **Needs correction.**

### ❓ Unsourced Claims
- "{{claim}}" — no wiki source covers this. Consider ingesting a supporting source.
```

### Update article status

- All claims supported → `status: verified`
- Any ❌ or ❓ → `status: draft`
- Only ⚠️ warnings → `status: reviewed`

---

## Step 5: External Verification (for ❓ and ❌ claims, if requested)

If the user wants external verification (not just internal source checking):

**Prioritize**: ❌ contradictions first, then ❓ unsourced. Stop after 10 external lookups.

For **scientific/academic claims**:
```
WebFetch https://api.semanticscholar.org/graph/v1/paper/search?query={{url-encoded keywords}}&fields=title,abstract,year,citationCount&limit=3
```

For **factual/historical claims**:
```
WebFetch https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&titles={{keywords}}&format=json
```

For **general web verification**: use WebSearch

If a source URL is dead, try: `WebFetch https://web.archive.org/web/2*/{{dead-url}}`

**Quick mode**: If the user says "quick verify" or "internal only", skip external verification entirely — only do Steps 2–4.

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
| [[Article]] | "{{claim}}" | Contradicts source which says... |

### ❓ Unsourced Claims
| Article | Claim | Suggested action |
|---------|-------|-----------------|
| [[Article]] | "{{claim}}" | Ingest supporting source |

## Verified Articles
{{list of articles now marked verified}}

## Recommended Sources to Ingest
- {{Source content type}} — would resolve claims in [[Article A]], [[Article B]]
```

---

## Step 7: Log Operation

Append to `wiki/_log.md`:
```
[{{today}} verify] Verified {{N}} articles: {{N}} verified, {{N}} reviewed, {{N}} need attention
```

---

## Notes

- **Clean-context subagent**: The verification LLM receives ONLY the article, source match report, and raw sources — no wiki context, no compilation history. This prevents the LLM from rubber-stamping its own work.
- **Trust raw/ sources**: Content in `raw/` is treated as authoritative primary source material
- **Prioritize contradictions**: ❌ flags are most urgent — they indicate a wiki error
- **Don't over-verify**: Soft claims like "widely used" don't need a citation if domain context supports them

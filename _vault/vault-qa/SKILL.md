---
name: vault-qa
description: Answer questions by researching the wiki. Use when the user asks "what does the wiki say about X", "what do we know about X", "summarize X from the wiki", "research X", "answer this question using the wiki", or any question that should be answered from the knowledge base rather than general knowledge. Also use when the user asks to save an answer as a wiki article or output file.
---

# vault-qa — Wiki Question Answering

You are answering a question by researching the Seed Vault wiki. The answer must come from the wiki's collected knowledge — cite sources using `[[wikilinks]]`, acknowledge gaps, and suggest follow-up.

---

## Step 1: Search with qmd (Deterministic Retrieval)

Use qmd for scalable, deterministic retrieval:

```bash
qmd query "{{user's question}}" --collection vault --limit 10
```

This returns ranked results with context snippets. Note the top articles by relevance.

**Fallback** (if qmd is not available): Read `wiki/_index.md` to understand what articles exist, then use Grep to find relevant content:
```
Grep pattern="{{keyword}}" path="wiki/" glob="*.md"
```

---

## Step 2: Retrieve Relevant Articles (LLM)

Read the full content of the top-N articles identified by qmd (or the index+grep fallback).

Prioritize reading order:
1. Concept articles on the core topic
2. Topic hub pages for the domain
3. Source summaries if you need primary evidence

Cap at reading ~15 articles. If more seem relevant, note that the answer may be incomplete.

---

## Step 3: Synthesize the Answer (LLM)

Before writing the answer, assess the confidence level based on the `status:` of articles consulted:
- **HIGH**: All directly relevant articles are `verified`
- **MEDIUM**: Mix of `verified` and `reviewed` sources, or primarily `reviewed`
- **LOW**: Primarily `draft` articles, significant knowledge gaps, or fewer than 2 relevant sources

Write a thorough answer using only what's in the wiki:

```markdown
## Answer: {{Question}}

> **Confidence: HIGH | MEDIUM | LOW** — *(one-line reason)*

{{Main answer — direct response to the question}}

### Evidence from the Wiki

**{{Sub-question or aspect}}**
According to [[Concept Article]], ... [[Summary: Source]] adds that ...

**{{Another aspect}}**
[[Topic: Related Topic]] covers ... The key sources are [[Summary: X]] and [[Summary: Y]].

### Knowledge Gaps
The wiki doesn't currently cover:
- {{Gap 1}} — consider ingesting {{type of source}}
- {{Gap 2}}

### Suggested Follow-Up Questions
- {{Question that would deepen understanding}}
- {{Adjacent question the wiki can answer}}

### Sources Consulted
- [[Concept Name]]
- [[Summary: Source Title]]
- [[Topic: Topic Name]]
```

**Citation style**: Always use `[[wikilinks]]` to cite. If quoting a specific claim, write: `"quote" — [[Summary: Source]]`

**Epistemic honesty**: If the wiki has conflicting information, present both sides. If information is unverified (status: draft), say so.

---

## Step 4: Save the Output (if requested)

**As an output file** (ephemeral):
Save to `outputs/qa-{{topic}}-{{today}}.md` with frontmatter:
```yaml
---
title: "Q&A: {{Question}}"
type: output
created: {{today}}
query: "{{original question}}"
sources_consulted: ["[[Article]]", "[[Article]]"]
tags: [output, qa]
---
```

**Filed back into the wiki** (persistent — user must confirm):
If the answer reveals a gap or synthesizes something worth keeping, offer to create a new concept article. Ask: "Should I file this as a new wiki article at `wiki/concepts/{{suggested-name}}.md`?"

---

## Step 5: Identify Enrichment Opportunities

After answering, note:
- New concepts mentioned in the answer that don't have wiki articles
- Sources that would fill the identified gaps
- Connections between articles that should be made explicit

Offer: "I found {{N}} concepts mentioned that don't have articles yet. Run `vault-compile` to create them?"

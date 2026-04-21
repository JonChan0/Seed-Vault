---
name: vault-index
description: Rebuild the wiki index and search infrastructure. Use when the user says "reindex", "rebuild index", "regenerate index", "the index is out of date", or after bulk operations that touched many articles. Fully deterministic — no LLM reasoning needed.
---

# vault-index — Index Rebuilder

You are rebuilding the wiki's navigation and search infrastructure. This skill is **fully deterministic** — it runs the Python engine and qmd, then reports results.

---

## Step 1: Run the Index Engine

```bash
uv run python _vault/lib/index.py --rebuild-qmd
```

This:
1. Scans all `wiki/**/*.md` files
2. Parses frontmatter (title, type, tags, status)
3. Groups by type, sorts alphabetically
4. Generates `wiki/_index.md` with one-line entries per article
5. Rebuilds the qmd search index (`qmd collection add wiki/ --name vault && qmd embed`)
6. Reports stats: counts by type, delta vs previous index

---

## Step 2: Report Results

Read and present the engine's output to the user:

```
Index rebuilt: {{today}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Concepts:           {{N}}
Source Summaries:   {{N}}
Visualizations:     {{N}}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total articles:     {{N}}
Delta:              +{{N}} new, -{{N}} removed
qmd:                {{N}} documents indexed
```

---

## Step 3: Log Operation

Append to `wiki/_log.md`:
```
[{{today}} index] Rebuilt: {{N}} concepts, {{N}} sources (qmd: {{N}} docs indexed)
```

---

## Notes

- **No catalog**: The old `_catalog.md` has been eliminated. qmd handles all search/retrieval. The single `_index.md` is the human-navigable table of contents.
- **qmd not installed**: If qmd is not available, the engine warns but still generates `_index.md`. Suggest installing: `npm install -g @tobilu/qmd`
- **Force rebuild**: Running this skill always does a full rebuild — there is no delta mode since it's fast enough.

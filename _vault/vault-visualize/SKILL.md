---
name: vault-visualize
description: Create HTML visualizations from wiki data. Use when the user says "visualize", "chart", "diagram", "graph", "create a visualization", "show me a chart of", "map out", "timeline", "plot", "network graph", "show connections between", or asks for any visual representation of wiki data. Creates self-contained HTML files in viz/ and Obsidian wrapper pages in wiki/.
---

# vault-visualize — HTML Visualization Generator

You are creating a data visualization from the Seed Vault wiki. The output is:
1. A self-contained HTML file in `viz/` (opens in any browser)
2. An Obsidian wrapper `.md` in `wiki/` that embeds the viz and links it to the graph

This skill is **fully LLM** — no deterministic engine. You design and write the visualization.

---

## Step 1: Understand What to Visualize

Determine the visualization type from the user's request:

| Request type | Best chart type |
|-------------|-----------------|
| Quantities, comparisons | Bar chart (Chart.js) |
| Trends over time | Line chart (Chart.js) |
| Proportions, parts of whole | Pie / donut (Chart.js) |
| Two-variable relationships | Scatter plot (Chart.js) |
| Simple static chart | SVG (inline, no library) |
| Concept relationships, network | Force-directed graph (D3.js) |
| Hierarchy, taxonomy | Tree / sunburst (D3.js) |
| Chronology, events | Timeline (vanilla HTML/CSS) |
| Process, flow | Mermaid flowchart (in markdown) |
| Geographic | Leaflet.js choropleth |

If unclear, ask. **Theme**: Ask or infer — default to dark.

---

## Step 2: Extract the Data

Read the relevant wiki articles and source summaries. Pull out the data points needed:
- **Charts**: numerical data, categories, time series
- **Networks**: entity names and relationships
- **Timelines**: dates and events
- **Hierarchies**: parent-child relationships

If data is implicit (e.g., "visualize connections between concepts"), derive it programmatically: read all wiki files, extract `[[wikilinks]]`, build an adjacency list.

---

## Step 3: Generate the HTML

Create `viz/{{name}}.html` as a fully self-contained file. Use CDN links for libraries:
- Chart.js: `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js`
- D3.js: `https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js`

**Dark theme** colors (default): background `#1e1e2e`, text `#cdd6f4`, accent `#89b4fa`
**Light theme** colors: background `#ffffff`, text `#1a1a2e`, accent `#2563eb`

For **Mermaid diagrams** (flowcharts, simple diagrams): use Obsidian's native Mermaid support directly in the wrapper `.md` file instead of a separate HTML file.

---

## Step 4: Create the Obsidian Wrapper Page

Write `wiki/concepts/viz-{{name}}.md`:

```markdown
---
title: "Viz - {{Title}}"
type: visualization
created: {{today}}
updated: {{today}}
sources: [{{wikilinks to source articles}}]
tags: [visualization, {{concept-tags}}]
status: draft
viz_file: "viz/{{name}}.html"
framework_version: "{{read from _vault/VERSION}}"
---

# {{Title}}

## Visualization

<iframe src="../../viz/{{name}}.html" width="100%" height="550px" frameborder="0" style="border-radius:8px;"></iframe>

> **Can't see the visualization?** Open `viz/{{name}}.html` in a browser, or install the Obsidian HTML Reader community plugin.

## What This Shows
{{1–2 paragraph explanation}}

## Key Insights
- {{Insight 1}}
- {{Insight 2}}
- {{Insight 3}}

## Data Sources
- [[concept-name|Concept Name]]
- [[summary-source-title|Summary - Source Title]]

## See Also
- [[related-concept|Related Concept]]
```

---

## Step 5: Update Index

Run the index engine:
```bash
uv run python _vault/lib/index.py
```

Or manually add to `wiki/_index.md` under `## Visualizations`:
```
- [[viz-{{name}}|Viz - {{Title}}]] — {{one-line description}}
```

---

## Naming Conventions

- `viz/concept-bar-chart.html`
- `viz/wiki-network-graph.html`
- `viz/concept-timeline.html`
- `wiki/concepts/viz-concept-bar-chart.md` (wrapper)

---

## Notes on Obsidian HTML Rendering

Obsidian doesn't show `<iframe>` by default. Options:
1. **Community plugin**: "HTML Reader" or "Webpage Export"
2. **Open externally**: Click the viz file in Obsidian's file explorer
3. **Mermaid**: For diagrams that don't need custom data — renders natively

Always include the fallback note in the wrapper page.

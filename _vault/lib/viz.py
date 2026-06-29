"""
viz.py — Deterministic visualization generator for the Seed Vault wiki.

Currently supports one fully deterministic visualization: a force-directed
network graph of the wiki's `[[wikilink]]` structure. No LLM involvement — the
adjacency is mechanical, so it is built and rendered in Python. Bespoke charts
remain the LLM's job via the vault-visualize skill.

Usage:
    uv run python _vault/lib/viz.py --network [--out viz/wiki-network-graph.html]
    uv run python _vault/lib/viz.py --network --json   # print adjacency, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root and directory constants
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
CONCEPTS_DIR = WIKI_DIR / "concepts"
VIZ_DIR = VAULT_ROOT / "viz"
VERSION_FILE = VAULT_ROOT / "_vault" / "VERSION"

sys.path.append(str(VAULT_ROOT))

from _vault.lib.vault_frontmatter import (  # noqa: E402
    build_vault_map,
    extract_wikilinks,
    is_meta_file,
    parse_file,
    resolve_link,
)


def _framework_version() -> str:
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


# ---------------------------------------------------------------------------
# Adjacency construction (deterministic)
# ---------------------------------------------------------------------------

def build_network() -> dict:
    """Build a node/link graph from every `[[wikilink]]` between content files.

    Returns ``{"nodes": [{"id", "title", "type"}], "links": [{"source", "target"}]}``.
    Links are undirected (deduped by unordered pair) and only connect resolvable
    content articles — meta/index files are excluded.
    """
    if not WIKI_DIR.exists():
        return {"nodes": [], "links": []}

    files = [f for f in WIKI_DIR.rglob("*.md") if not is_meta_file(f)]
    vault_map = build_vault_map(WIKI_DIR)

    nodes: dict[str, dict] = {}
    for f in files:
        fm = parse_file(f)
        nodes[f.stem] = {
            "id": f.stem,
            "title": fm.get("title") or f.stem.replace("-", " ").title(),
            "type": fm.get("type") or "unknown",
        }

    seen: set[frozenset] = set()
    links: list[dict] = []
    for f in files:
        body = f.read_text(encoding="utf-8")
        for target in extract_wikilinks(body):
            resolved = resolve_link(target, vault_map)
            if not resolved or resolved == f or is_meta_file(resolved):
                continue
            if resolved.stem not in nodes:
                continue
            pair = frozenset((f.stem, resolved.stem))
            if pair in seen:
                continue
            seen.add(pair)
            links.append({"source": f.stem, "target": resolved.stem})

    return {"nodes": sorted(nodes.values(), key=lambda n: n["id"]), "links": links}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Wiki Network Graph</title>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<style>
  body {{ margin: 0; background: #1e1e2e; color: #cdd6f4; font-family: sans-serif; }}
  svg {{ width: 100vw; height: 100vh; }}
  .link {{ stroke: #45475a; stroke-width: 1px; }}
  .node circle {{ fill: #89b4fa; stroke: #1e1e2e; stroke-width: 1.5px; }}
  .node text {{ fill: #cdd6f4; font-size: 10px; }}
</style>
</head>
<body>
<svg></svg>
<script>
const graph = {data};
const svg = d3.select("svg");
const width = window.innerWidth, height = window.innerHeight;
const sim = d3.forceSimulation(graph.nodes)
  .force("link", d3.forceLink(graph.links).id(d => d.id).distance(80))
  .force("charge", d3.forceManyBody().strength(-200))
  .force("center", d3.forceCenter(width / 2, height / 2));
const link = svg.append("g").selectAll("line")
  .data(graph.links).join("line").attr("class", "link");
const node = svg.append("g").selectAll("g")
  .data(graph.nodes).join("g").attr("class", "node")
  .call(d3.drag()
    .on("start", (e, d) => {{ if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
    .on("drag", (e, d) => {{ d.fx = e.x; d.fy = e.y; }})
    .on("end", (e, d) => {{ if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }}));
node.append("circle").attr("r", 6);
node.append("text").attr("x", 9).attr("y", 3).text(d => d.title);
sim.on("tick", () => {{
  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
}});
</script>
</body>
</html>
"""


def render_html(graph: dict) -> str:
    return _HTML_TEMPLATE.format(data=json.dumps(graph))


def render_wrapper(html_rel: str, node_count: int, link_count: int) -> str:
    today = date.today().isoformat()
    version = _framework_version()
    name = Path(html_rel).stem
    return (
        "---\n"
        'title: "Viz - Wiki Network Graph"\n'
        "type: visualization\n"
        f"created: {today}\n"
        f"updated: {today}\n"
        "sources: []\n"
        "tags: [visualization, wiki/structure]\n"
        "status: draft\n"
        f'viz_file: "{html_rel}"\n'
        f'framework_version: "{version}"\n'
        "---\n\n"
        "# Wiki Network Graph\n\n"
        "## Visualization\n\n"
        f'<iframe src="../../{html_rel}" width="100%" height="550px" '
        'frameborder="0" style="border-radius:8px;"></iframe>\n\n'
        "> **Can't see it?** Open the HTML file in a browser, or install the "
        "Obsidian HTML Reader plugin.\n\n"
        "## What This Shows\n\n"
        f"Deterministically generated from every `[[wikilink]]` in the wiki: "
        f"{node_count} articles, {link_count} connections.\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed Vault deterministic visualization generator (no LLM)."
    )
    parser.add_argument(
        "--network",
        action="store_true",
        help="Generate the wiki wikilink network graph.",
    )
    parser.add_argument(
        "--out",
        default="viz/wiki-network-graph.html",
        help="Output HTML path (relative to vault root).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the adjacency graph as JSON and write no files.",
    )
    args = parser.parse_args(argv)

    if not args.network:
        parser.error("no visualization selected (use --network)")

    graph = build_network()

    if args.json_output:
        print(json.dumps(graph, indent=2))
        return 0

    html_rel = args.out
    html_path = VAULT_ROOT / html_rel
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_html(graph), encoding="utf-8")

    wrapper_path = CONCEPTS_DIR / f"viz-{Path(html_rel).stem}.md"
    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(
        render_wrapper(html_rel, len(graph["nodes"]), len(graph["links"])),
        encoding="utf-8",
    )

    print(
        f"Network graph written: {html_rel} "
        f"({len(graph['nodes'])} nodes, {len(graph['links'])} links)\n"
        f"Wrapper: {wrapper_path.relative_to(VAULT_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for _vault/lib/viz.py — deterministic network-graph generator (no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VAULT_ROOT))

from conftest import engine_json, run_engine  # noqa: E402


class TestNetworkAdjacency:
    def test_json_has_nodes_and_links(self, subprocess_vault):
        result = run_engine(subprocess_vault, "viz", "--network", "--json")
        assert result.returncode == 0, result.stderr
        graph = engine_json(result)
        assert set(graph.keys()) >= {"nodes", "links"}
        ids = {n["id"] for n in graph["nodes"]}
        assert "dummy-gene-editing" in ids
        assert "dummy-human-genome" in ids

    def test_edge_between_linked_concepts(self, subprocess_vault):
        result = run_engine(subprocess_vault, "viz", "--network", "--json")
        graph = engine_json(result)
        pairs = {frozenset((e["source"], e["target"])) for e in graph["links"]}
        assert frozenset(("dummy-gene-editing", "dummy-human-genome")) in pairs


class TestNetworkHTML:
    def test_writes_self_contained_html(self, subprocess_vault):
        result = run_engine(subprocess_vault, "viz", "--network")
        assert result.returncode == 0, result.stderr
        html_path = subprocess_vault / "viz" / "wiki-network-graph.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        # Self-contained: data embedded inline, library via CDN, no external data file.
        assert "d3" in html.lower()
        assert '"nodes"' in html
        assert "dummy-gene-editing" in html

    def test_writes_wrapper_with_valid_frontmatter(self, subprocess_vault):
        run_engine(subprocess_vault, "viz", "--network")
        wrapper = subprocess_vault / "wiki" / "concepts" / "viz-wiki-network-graph.md"
        assert wrapper.exists()
        text = wrapper.read_text(encoding="utf-8")
        assert "type: visualization" in text
        assert 'framework_version: "3.0.0"' in text
        assert "viz/wiki-network-graph.html" in text

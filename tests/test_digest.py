"""Unit tests for _vault/lib/digest.py (in-process via point_engine)."""
from __future__ import annotations


from _vault.lib import digest

from conftest import point_engine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_stats(monkeypatch, vault):
    """Point the digest engine at *vault* and call build_stats()."""
    point_engine(monkeypatch, digest, vault)
    return digest.build_stats()


# ---------------------------------------------------------------------------
# Empty vault
# ---------------------------------------------------------------------------


class TestEmptyVault:
    def test_total_zero(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["total"] == 0

    def test_orphans_empty(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["orphans"] == []

    def test_hub_nodes_empty(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["hub_nodes"] == []

    def test_type_counts_empty(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["type_counts"] == {}

    def test_unresolved_links_empty(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["unresolved_links"] == []

    def test_gaps_zero(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        assert stats["gaps"]["raw_without_summary"] == 0
        assert stats["gaps"]["singleton_tags"] == 0


# ---------------------------------------------------------------------------
# Clean fixture (dummy_vault with 4 articles)
# ---------------------------------------------------------------------------


class TestCleanFixture:
    def test_total_four(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["total"] == 4

    def test_type_counts(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["type_counts"] == {"concept": 2, "source-summary": 2}

    def test_no_orphans(self, monkeypatch, dummy_vault):
        """No articles should be flagged as orphans — the alias-map fix must hold."""
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["orphans"] == []

    def test_hub_nodes_count(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        assert len(stats["hub_nodes"]) == 4

    def test_hub_nodes_all_have_incoming_two(self, monkeypatch, dummy_vault):
        """Every article in the clean fixture receives exactly 2 incoming links."""
        stats = _get_stats(monkeypatch, dummy_vault)
        for node in stats["hub_nodes"]:
            assert node["incoming"] == 2, (
                f"Expected 2 incoming links for '{node['title']}', "
                f"got {node['incoming']}"
            )

    def test_hub_node_titles_are_real_titles(self, monkeypatch, dummy_vault):
        """Hub node titles come from frontmatter, not file stems."""
        stats = _get_stats(monkeypatch, dummy_vault)
        hub_titles = {n["title"] for n in stats["hub_nodes"]}
        expected = {
            "Dummy Human Genome",
            "Dummy Gene Editing",
            "Summary - Dummy Genome Project",
            "Summary - Dummy CRISPR Notes",
        }
        assert hub_titles == expected

    def test_singleton_tags_zero(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["gaps"]["singleton_tags"] == 0

    def test_raw_without_summary_zero(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["gaps"]["raw_without_summary"] == 0

    def test_unresolved_links_empty(self, monkeypatch, dummy_vault):
        """No unresolved links — raw/ links are excluded, all others resolve."""
        stats = _get_stats(monkeypatch, dummy_vault)
        assert stats["unresolved_links"] == []

    def test_tag_distribution_has_dummy_genomics(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        tag_dict = dict(stats["tag_distribution"])
        assert "dummy/genomics" in tag_dict
        assert tag_dict["dummy/genomics"] == 4

    def test_tag_distribution_method_sequencing(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        tag_dict = dict(stats["tag_distribution"])
        assert tag_dict.get("method/sequencing") == 2

    def test_tag_distribution_method_editing(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        tag_dict = dict(stats["tag_distribution"])
        assert tag_dict.get("method/editing") == 2


# ---------------------------------------------------------------------------
# format_markdown
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    def test_returns_string(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        result = digest.format_markdown(stats)
        assert isinstance(result, str)

    def test_contains_total_articles(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        result = digest.format_markdown(stats)
        assert "Total articles:" in result

    def test_contains_total_count(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        result = digest.format_markdown(stats)
        assert "4" in result

    def test_empty_vault_format_markdown(self, monkeypatch, empty_vault):
        stats = _get_stats(monkeypatch, empty_vault)
        result = digest.format_markdown(stats)
        assert isinstance(result, str)
        assert "Total articles:" in result


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_returns_string(self, monkeypatch, dummy_vault):
        stats = _get_stats(monkeypatch, dummy_vault)
        result = digest.format_json(stats)
        assert isinstance(result, str)

    def test_is_valid_json(self, monkeypatch, dummy_vault):
        import json

        stats = _get_stats(monkeypatch, dummy_vault)
        result = digest.format_json(stats)
        parsed = json.loads(result)
        assert parsed["total"] == 4

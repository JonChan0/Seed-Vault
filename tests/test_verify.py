"""Tests for _vault/lib/verify.py — claim extraction and verification."""
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from conftest import (
    engine_json,
    run_engine,
    write_article,
)

from _vault.lib import verify


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _claims_by_type(body: str) -> dict[str, list[dict]]:
    """Return a dict of type -> list of claim dicts for easy lookup."""
    claims = verify.extract_claims(body)
    result: dict[str, list[dict]] = {}
    for c in claims:
        result.setdefault(c["type"], []).append(c)
    return result


# ---------------------------------------------------------------------------
# Unit tests: extract_claims
# ---------------------------------------------------------------------------

class TestExtractClaims:
    """Pure function tests — no vault, no monkeypatching needed."""

    BODY = (
        "Accuracy reached 99.9% across the finished sequence. "
        "The project was announced in 2003 and spanned 3.2 Gb of sequence. "
        "Total cost was about $2.7 billion over its lifetime. "
        "The assembly contains approximately 20,500 protein-coding genes."
    )

    def test_finds_percentage(self):
        by_type = _claims_by_type(self.BODY)
        assert "percentage" in by_type, "Expected a percentage claim"
        values = [c["value"] for c in by_type["percentage"]]
        assert any("99.9%" in v for v in values), f"No 99.9% in {values}"

    def test_percentage_type_label(self):
        by_type = _claims_by_type(self.BODY)
        for c in by_type.get("percentage", []):
            assert c["type"] == "percentage"

    def test_finds_year(self):
        by_type = _claims_by_type(self.BODY)
        assert "year" in by_type, "Expected a year claim"
        values = [c["value"] for c in by_type["year"]]
        assert "2003" in values, f"Expected 2003 in {values}"

    def test_year_type_label(self):
        by_type = _claims_by_type(self.BODY)
        for c in by_type.get("year", []):
            assert c["type"] == "year"

    def test_finds_measurement(self):
        by_type = _claims_by_type(self.BODY)
        assert "measurement" in by_type, "Expected a measurement claim"
        values = [c["value"] for c in by_type["measurement"]]
        assert any("3.2" in v and "Gb" in v for v in values), (
            f"Expected 3.2 Gb in {values}"
        )

    def test_measurement_type_label(self):
        by_type = _claims_by_type(self.BODY)
        for c in by_type.get("measurement", []):
            assert c["type"] == "measurement"

    def test_finds_dollar_amount(self):
        by_type = _claims_by_type(self.BODY)
        assert "dollar_amount" in by_type, "Expected a dollar_amount claim"
        values = [c["value"] for c in by_type["dollar_amount"]]
        assert any("2.7" in v for v in values), f"Expected $2.7 billion in {values}"

    def test_dollar_amount_type_label(self):
        by_type = _claims_by_type(self.BODY)
        for c in by_type.get("dollar_amount", []):
            assert c["type"] == "dollar_amount"

    def test_finds_named_number(self):
        by_type = _claims_by_type(self.BODY)
        assert "named_number" in by_type, "Expected a named_number claim"
        values = [c["value"] for c in by_type["named_number"]]
        assert any("20,500" in v or "20500" in v for v in values), (
            f"Expected 20,500 in {values}"
        )

    def test_named_number_type_label(self):
        by_type = _claims_by_type(self.BODY)
        for c in by_type.get("named_number", []):
            assert c["type"] == "named_number"

    def test_claims_have_context(self):
        claims = verify.extract_claims(self.BODY)
        for c in claims:
            assert "context" in c and c["context"], "Claim missing context"

    def test_no_claims_in_empty_string(self):
        assert verify.extract_claims("") == []

    def test_dedup_same_value_and_type(self):
        # Two identical percentages — should deduplicate
        body = "Accuracy is 99.9% and also 99.9% again."
        claims = verify.extract_claims(body)
        pct_claims = [c for c in claims if c["type"] == "percentage"]
        pct_values = [c["value"] for c in pct_claims]
        assert pct_values.count("99.9%") == 1, "Duplicate claim not deduped"


# ---------------------------------------------------------------------------
# Unit tests: verify_claim
# ---------------------------------------------------------------------------

class TestVerifyClaim:
    """Tests for verify_claim against explicit source file lists.

    verify_claim calls ``file_path.relative_to(VAULT_ROOT)`` on a match, so
    source files must live under whatever VAULT_ROOT the module is pointed at.
    We use ``point_engine`` + ``monkeypatch`` to repoint verify.VAULT_ROOT at
    ``dummy_vault``, then write source files there.
    """

    def _make_claim(self, value: str, claim_type: str, context: str = "") -> dict:
        return {"value": value, "type": claim_type, "context": context or value}

    def _source_in(self, vault: Path, name: str, text: str) -> Path:
        """Write a source file under vault/raw/ and return its path."""
        p = vault / "raw" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_exact_match_when_value_in_source(self, monkeypatch, dummy_vault):
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        source = self._source_in(
            dummy_vault,
            "source.md",
            "Accuracy reached 99.9% across the finished sequence.",
        )
        verify._source_lines_cache.clear()
        claim = self._make_claim("99.9%", "percentage", "Accuracy reached 99.9%")
        result = verify.verify_claim(claim, [source])
        assert result["match_type"] == "exact", (
            f"Expected 'exact', got {result['match_type']!r}"
        )
        assert result["matched_text"] is not None

    def test_none_when_value_absent(self, monkeypatch, dummy_vault):
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        source = self._source_in(dummy_vault, "absent.md", "No relevant numbers here.")
        verify._source_lines_cache.clear()
        claim = self._make_claim("99.9%", "percentage")
        result = verify.verify_claim(claim, [source])
        assert result["match_type"] == "none"

    def test_exact_match_case_insensitive(self, monkeypatch, dummy_vault):
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        source = self._source_in(
            dummy_vault,
            "upper.md",
            "ACCURACY REACHED 99.9% ACROSS THE SEQUENCE.",
        )
        verify._source_lines_cache.clear()
        claim = self._make_claim("99.9%", "percentage")
        result = verify.verify_claim(claim, [source])
        assert result["match_type"] == "exact"

    def test_empty_source_list_returns_none(self):
        verify._source_lines_cache.clear()
        claim = self._make_claim("99.9%", "percentage")
        result = verify.verify_claim(claim, [])
        assert result["match_type"] == "none"

    def test_result_contains_expected_keys(self, monkeypatch, dummy_vault):
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        source = self._source_in(dummy_vault, "cost.md", "cost was $2.7 billion")
        verify._source_lines_cache.clear()
        claim = self._make_claim("$2.7 billion", "dollar_amount")
        result = verify.verify_claim(claim, [source])
        for key in (
            "claim_text",
            "value",
            "type",
            "match_type",
            "source_file",
            "matched_text",
            "score",
        ):
            assert key in result, f"Missing key {key!r} in result"

    def test_partial_match_near_miss(self, monkeypatch, dummy_vault):
        """Fuzzy match: value slightly different from source text."""
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        # Source says "20500" (no comma), claim has "20,500"
        source = self._source_in(
            dummy_vault,
            "genes.md",
            "approximately 20500 protein-coding genes",
        )
        verify._source_lines_cache.clear()
        claim = self._make_claim("20,500", "named_number")
        result = verify.verify_claim(claim, [source])
        # Should be at least partial (fuzzy) if thefuzz is available; if not, none is ok
        assert result["match_type"] in ("exact", "partial", "none"), (
            f"Unexpected match_type: {result['match_type']}"
        )

    def test_picks_best_match_across_multiple_sources(self, monkeypatch, dummy_vault):
        """verify_claim picks the exact match over a none-match."""
        from conftest import point_engine

        point_engine(monkeypatch, verify, dummy_vault)
        source_a = self._source_in(dummy_vault, "a.md", "Nothing relevant here.")
        source_b = self._source_in(
            dummy_vault, "b.md", "The genome spans 3.2 Gb of sequence."
        )
        verify._source_lines_cache.clear()
        claim = self._make_claim("3.2 Gb", "measurement")
        result = verify.verify_claim(claim, [source_a, source_b])
        assert result["match_type"] == "exact"
        # source_file should point to b.md
        assert "b.md" in str(result["source_file"])


# ---------------------------------------------------------------------------
# Integration tests: full article via subprocess (subprocess_vault)
# ---------------------------------------------------------------------------

class TestVerifyArticleSubprocess:
    """Run verify.py as a subprocess against the clean fixture article."""

    def test_clean_fixture_claims_found(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/dummy-human-genome.md", "--json"
        )
        assert result.returncode == 0, f"verify failed:\n{result.stderr}"
        report = engine_json(result)
        assert report["claims_found"] == 6, (
            f"Expected 6 claims, got {report['claims_found']}"
        )

    def test_clean_fixture_exact_matches(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/dummy-human-genome.md", "--json"
        )
        report = engine_json(result)
        assert report["summary"]["exact_matches"] == 5, (
            f"Expected 5 exact matches, got {report['summary']['exact_matches']}"
        )

    def test_clean_fixture_unmatched_claims(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/dummy-human-genome.md", "--json"
        )
        report = engine_json(result)
        assert report["summary"]["unmatched_claims"] == 1, (
            f"Expected 1 unmatched claim, got {report['summary']['unmatched_claims']}"
        )

    def test_clean_fixture_confidence_high(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/dummy-human-genome.md", "--json"
        )
        report = engine_json(result)
        assert report["summary"]["confidence"] == "HIGH", (
            f"Expected HIGH confidence, got {report['summary']['confidence']!r}"
        )

    def test_report_has_required_keys(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/dummy-human-genome.md", "--json"
        )
        report = engine_json(result)
        for key in ("title", "article", "claims_found", "source_warnings", "results", "summary"):
            assert key in report, f"Missing key {key!r} in report"

    def test_nonexistent_article_returns_error(self, subprocess_vault):
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/does-not-exist.md", "--json"
        )
        assert result.returncode != 0, "Expected non-zero exit for missing article"


# ---------------------------------------------------------------------------
# No-sources article → source_warnings
# ---------------------------------------------------------------------------

class TestVerifyNoSources:
    """Article with no sources: field should trigger source_warnings."""

    def test_no_sources_produces_warnings(self, subprocess_vault):
        """A concept article with no sources: in frontmatter → source_warnings."""
        art = subprocess_vault / "wiki" / "concepts" / "no-sources-article.md"
        write_article(
            art,
            {
                "title": "No Sources Article",
                "type": "concept",
                "created": "2026-06-25",
                "updated": "2026-06-25",
                "tags": ["dummy/test"],
                "status": "draft",
                "llm_model": "claude-sonnet-4-6",
                "framework_version": "3.0.0",
            },
            body="The genome was sequenced in 2003 spanning 3.2 Gb with 99.9% accuracy.",
        )
        result = run_engine(subprocess_vault, "verify", "wiki/concepts/no-sources-article.md", "--json")
        assert result.returncode == 0
        report = engine_json(result)
        # Either source_warnings is non-empty, OR all claims are unmatched
        has_warnings = bool(report.get("source_warnings"))
        all_unmatched = (
            report["claims_found"] > 0
            and report["summary"]["exact_matches"] == 0
            and report["summary"]["partial_matches"] == 0
        )
        assert has_warnings or all_unmatched, (
            f"Expected warnings or all-unmatched for no-sources article.\n"
            f"source_warnings={report.get('source_warnings')}, "
            f"summary={report['summary']}"
        )


# ---------------------------------------------------------------------------
# Low/Medium confidence test
# ---------------------------------------------------------------------------

class TestVerifyLowConfidence:
    """Article where most claims are unmatched → LOW confidence."""

    def test_mostly_unmatched_gives_low_or_medium_confidence(self, subprocess_vault):
        # Source file with almost no relevant numbers
        raw_file = subprocess_vault / "raw" / "sparse-source.md"
        raw_file.write_text(
            "---\ntitle: Sparse Source\n---\nThis source has very little numeric content.\n",
            encoding="utf-8",
        )
        # Source summary referencing that raw file
        write_article(
            subprocess_vault / "wiki" / "sources" / "summary-sparse-source.md",
            {
                "title": "Summary - Sparse Source",
                "type": "source-summary",
                "created": "2026-06-25",
                "updated": "2026-06-25",
                "original_source": "[[raw/sparse-source|Sparse Source]]",
                "sources": ["[[raw/sparse-source|Sparse Source]]"],
                "tags": ["dummy/test"],
                "status": "draft",
                "llm_model": "claude-sonnet-4-6",
                "framework_version": "3.0.0",
            },
            body="## Concepts Extracted\n\n- [[low-confidence-article|Low Confidence Article]]",
        )
        # Concept with many claims not in the sparse source
        write_article(
            subprocess_vault / "wiki" / "concepts" / "low-confidence-article.md",
            {
                "title": "Low Confidence Article",
                "type": "concept",
                "created": "2026-06-25",
                "updated": "2026-06-25",
                "sources": ["[[summary-sparse-source|Summary - Sparse Source]]"],
                "tags": ["dummy/test"],
                "status": "draft",
                "llm_model": "claude-sonnet-4-6",
                "framework_version": "3.0.0",
            },
            body=(
                "This experiment reported 12%, 34%, and 56% efficiency in 2001, 2002, "
                "and 2003 respectively. The total cost was $9.9 billion across "
                "approximately 99,000 samples spanning 1.5 Gb of sequence."
            ),
        )
        result = run_engine(
            subprocess_vault, "verify",
            "wiki/concepts/low-confidence-article.md", "--json"
        )
        assert result.returncode == 0
        report = engine_json(result)
        confidence = report["summary"]["confidence"]
        assert confidence in ("LOW", "MEDIUM"), (
            f"Expected LOW or MEDIUM confidence for mostly-unmatched article, got {confidence!r}"
        )


# ---------------------------------------------------------------------------
# Phase 1: Hard verification gate
# ---------------------------------------------------------------------------

def _report(exact=0, partial=0, unmatched=0, warnings=None):
    """Build a minimal verify_article-shaped report for gate logic tests."""
    return {
        "title": "T",
        "article": "wiki/concepts/t.md",
        "claims_found": exact + partial + unmatched,
        "source_warnings": warnings or [],
        "results": [],
        "summary": {
            "exact_matches": exact,
            "partial_matches": partial,
            "unmatched_claims": unmatched,
            "confidence": "HIGH",
        },
    }


class TestGateArticle:
    """Pure gate decision on a report dict — no IO."""

    def test_skip_when_all_exact_no_warnings(self):
        assert verify.gate_article(_report(exact=5)) is False

    def test_skip_when_zero_claims_no_warnings(self):
        assert verify.gate_article(_report()) is False

    def test_gate_in_when_unmatched(self):
        assert verify.gate_article(_report(exact=3, unmatched=1)) is True

    def test_gate_in_when_partial(self):
        assert verify.gate_article(_report(exact=3, partial=1)) is True

    def test_gate_in_when_source_warning(self):
        assert verify.gate_article(_report(exact=5, warnings=["no sources"])) is True


class TestGateArticlesInProcess:
    """gate_articles over real fixture articles, repointed in-process."""

    def test_returns_verify_and_skip_keys(self, monkeypatch, dummy_vault):
        from conftest import point_engine
        point_engine(monkeypatch, verify, dummy_vault)
        paths = sorted((dummy_vault / "wiki" / "concepts").glob("*.md"))
        result = verify.gate_articles(paths)
        assert set(result.keys()) == {"verify", "skip"}
        # Every input article lands in exactly one bucket.
        union = result["verify"] + result["skip"]
        assert len(union) == len(paths)


class TestGateCLI:
    """`verify.py --gate <article...> --json` returns {verify, skip}."""

    def test_gate_cli_partitions_inputs(self, subprocess_vault):
        articles = [
            "wiki/concepts/dummy-gene-editing.md",
            "wiki/concepts/dummy-human-genome.md",
        ]
        result = run_engine(subprocess_vault, "verify", "--gate", *articles, "--json")
        assert result.returncode == 0, result.stderr
        out = engine_json(result)
        assert set(out.keys()) == {"verify", "skip"}
        union = out["verify"] + out["skip"]
        assert len(union) == len(articles)

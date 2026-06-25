"""
verify.py — Claim verification engine for the Seed Vault wiki.

Extracts verifiable claims (numbers, dates, measurements, dollar amounts)
from a wiki article and matches them against raw source files using exact
and fuzzy string matching.

Usage:
    uv run python _vault/lib/verify.py <article_path> [--json]

Default output is human-readable. --json outputs JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Vault root: this file lives at <vault>/_vault/lib/verify.py
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"

# ---------------------------------------------------------------------------
# Fuzzy matching — graceful degradation if thefuzz is not installed
# ---------------------------------------------------------------------------

try:
    from thefuzz import fuzz as _fuzz  # type: ignore

    _FUZZY_AVAILABLE = True
except ImportError:
    _FUZZY_AVAILABLE = False
    _fuzz = None  # type: ignore

FUZZY_THRESHOLD = 75

# Per-run cache of source file line lists, populated on first access in
# verify_claim. Cleared at the start of each verify_article call.
_source_lines_cache: dict[Path, list[str]] = {}

# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

# Add vault root to sys.path so this script runs both as `uv run python ...`
# and as a direct module import.
sys.path.append(str(VAULT_ROOT))

from _vault.lib.frontmatter import parse_file  # noqa: E402


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _strip_frontmatter(text: str) -> str:
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if m:
        return text[m.end():]
    return text


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

# Sentence boundary splitter — splits on . ! ? followed by whitespace/EOL
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _get_context(text: str, match: re.Match) -> str:
    """Return the sentence (or ±120-char window) that contains the match."""
    start = match.start()
    end = match.end()
    # Walk back to start of sentence
    left = text.rfind("\n", 0, start)
    left = left + 1 if left != -1 else max(0, start - 120)
    # Walk forward to end of sentence
    right_nl = text.find("\n", end)
    right = right_nl if right_nl != -1 else min(len(text), end + 120)
    sentence = text[left:right].strip()
    # Trim to nearest sentence boundary if too long
    if len(sentence) > 250:
        sentence = sentence[:250].rstrip() + "…"
    return sentence


# Patterns: (type_name, compiled_regex, value_group_index)
_CLAIM_PATTERNS: list[tuple[str, re.Pattern, int]] = [
    # Percentages: 45%, 3.7 %
    (
        "percentage",
        re.compile(r"(\d+\.?\d*\s*%)"),
        1,
    ),
    # Years: 1800–2099
    (
        "year",
        re.compile(r"\b(1[89]\d{2}|2[01]\d{2})\b"),
        1,
    ),
    # Measurements with units
    (
        "measurement",
        re.compile(
            r"(\d+\.?\d*\s*"
            r"(?:kg|mg|g|km|m|cm|mm|ml|L|bp|kb|Mb|Gb|kDa|nm|μm))"
            r"\b"
        ),
        1,
    ),
    # Dollar amounts
    (
        "dollar_amount",
        re.compile(r"(\$[\d,.]+\s*(?:billion|million|trillion)?)"),
        1,
    ),
    # Named numbers — digits near approximation keywords
    (
        "named_number",
        re.compile(
            r"(?:approximately|about|estimated|total|roughly)\s+"
            r"([\d][\d,]*\.?\d*)",
            re.IGNORECASE,
        ),
        1,
    ),
]


def extract_claims(body: str) -> list[dict[str, str]]:
    """Return a list of claim dicts with keys: value, type, context."""
    claims: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()  # (value, type) dedup

    for claim_type, pattern, group_idx in _CLAIM_PATTERNS:
        for m in pattern.finditer(body):
            value = m.group(group_idx).strip()
            key = (value, claim_type)
            if key in seen:
                continue
            seen.add(key)
            context = _get_context(body, m)
            claims.append(
                {
                    "value": value,
                    "type": claim_type,
                    "context": context,
                }
            )

    return claims


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------

def _strip_wikilink_brackets(wikilink: str) -> str:
    """Strip [[ ]], aliased | suffix, and # section anchor from a wikilink."""
    inner = re.sub(r"^\[\[|\]\]$", "", wikilink).strip()
    inner = inner.split("|", 1)[0].split("#", 1)[0]
    return inner.strip()


def _wikilink_to_source_path(wikilink: str) -> Path | None:
    """
    Convert a wikilink like '[[summary-foo-bar|Summary - Foo Bar]]' to the
    expected path wiki/sources/summary-foo-bar.md, and return it if it exists.
    """
    title = _strip_wikilink_brackets(wikilink)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    candidate = WIKI_DIR / "sources" / f"{slug}.md"
    return candidate if candidate.exists() else None


def _find_raw_file_for_source(source_path: Path) -> Path | None:
    """
    Read a source summary's frontmatter to discover which raw file it covers.

    Resolution order:
      1. original_source — the field vault-ingest actually writes (e.g. "[[raw/name]]")
      2. raw_file / source_file — legacy explicit fields
      3. sources — if any entry looks like a raw/ path
      4. Stem-based match — summary-foo → raw/foo.*
    """
    fm = parse_file(source_path)

    # 1. original_source — written by vault-ingest as "[[raw/name]]"
    orig = fm.get("original_source")
    if orig:
        orig_str = _strip_wikilink_brackets(str(orig))
        for suffix in ("", ".md"):
            for base in (VAULT_ROOT, RAW_DIR):
                candidate = base / f"{orig_str}{suffix}"
                if candidate.exists():
                    return candidate

    # 2. Explicit raw_file or source_file field
    for field in ("raw_file", "source_file"):
        val = fm.get(field)
        if val:
            candidate = VAULT_ROOT / str(val)
            if candidate.exists():
                return candidate
            candidate2 = RAW_DIR / str(val)
            if candidate2.exists():
                return candidate2

    # 3. sources field may point to a raw file path
    src_list = fm.get("sources", []) or []
    if isinstance(src_list, str):
        src_list = [src_list]
    for src in src_list:
        src_str = _strip_wikilink_brackets(str(src))
        if "." in Path(src_str).suffix:
            for base in (VAULT_ROOT, RAW_DIR):
                candidate = base / src_str
                if candidate.exists():
                    return candidate

    # 4. Stem-based match in raw/: source summary is summary-foo → look for foo.*
    stem = source_path.stem  # e.g. "summary-climate-change"
    raw_stem = re.sub(r"^summary-", "", stem)
    if RAW_DIR.exists():
        for raw_file in RAW_DIR.rglob("*"):
            if raw_file.is_file() and raw_file.stem.lower() == raw_stem.lower():
                return raw_file

    return None


def resolve_sources(article_fm: dict) -> tuple[list[Path], list[str]]:
    """
    Given an article's frontmatter, resolve all source wikilinks to raw file
    paths. Only ever returns files under raw/ — never wiki articles.

    Returns:
        (raw_paths, warnings)
        warnings: list of human-readable strings for unresolvable sources.
                  An empty raw_paths with non-empty warnings means the caller
                  should direct the user to run lint.py to fix source coverage.
    """
    raw_paths: list[Path] = []
    warnings: list[str] = []
    sources = article_fm.get("sources", []) or []
    if isinstance(sources, str):
        sources = [sources]

    if not sources:
        warnings.append(
            "article has no sources: field in frontmatter — "
            "run lint to check raw coverage (check: raw_coverage)"
        )
        return raw_paths, warnings

    for src in sources:
        src_str = str(src).strip()

        # Resolve wikilink to source summary, then follow it to the raw file
        summary_path = _wikilink_to_source_path(src_str)
        if summary_path:
            raw = _find_raw_file_for_source(summary_path)
            if raw and raw not in raw_paths:
                raw_paths.append(raw)
            else:
                warnings.append(
                    f"source {src_str!r} resolved to {summary_path.name} "
                    f"but no raw file could be found — "
                    f"run lint to check raw coverage (check: raw_coverage)"
                )
        else:
            # Wikilink didn't resolve to a summary — try raw/ stem match directly
            title = _strip_wikilink_brackets(src_str)
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            found = False
            if RAW_DIR.exists():
                for raw_file in RAW_DIR.rglob("*"):
                    if raw_file.is_file():
                        file_slug = re.sub(
                            r"[^a-z0-9]+", "-", raw_file.stem.lower()
                        ).strip("-")
                        if file_slug == slug or raw_file.stem.lower() == slug:
                            if raw_file not in raw_paths:
                                raw_paths.append(raw_file)
                            found = True
            if not found:
                warnings.append(
                    f"source {src_str!r} could not be resolved to any raw file — "
                    f"run lint to check broken wikilinks (check: broken_wikilinks)"
                )

    return raw_paths, warnings


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------

def _split_lines(text: str) -> list[str]:
    return text.splitlines()


def _search_in_lines(
    value: str, lines: list[str]
) -> tuple[str, str | None, int | None]:
    """Search pre-split *lines* for *value*.

    Returns:
        (match_type, matched_text, score)
        match_type: "exact" | "partial" | "none"
    """
    if not lines:
        return "none", None, None

    # --- Exact match (substring search, case-sensitive first, then case-insensitive)
    for line in lines:
        if value in line:
            return "exact", line.strip(), 100

    # Case-insensitive exact
    value_lower = value.lower()
    for line in lines:
        if value_lower in line.lower():
            return "exact", line.strip(), 100

    # --- Fuzzy match
    if not _FUZZY_AVAILABLE:
        return "none", None, None

    best_score = 0
    best_line: str | None = None

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        score = _fuzz.partial_ratio(value, line_stripped)
        if score > best_score:
            best_score = score
            best_line = line_stripped

    if best_score >= FUZZY_THRESHOLD:
        return "partial", best_line, best_score

    return "none", None, best_score if best_score else None


def verify_claim(
    claim: dict[str, str], source_files: list[Path]
) -> dict[str, Any]:
    """
    Attempt to verify a single claim against the list of source files.

    Returns a result dict matching the report schema.
    """
    value = claim["value"]
    claim_text = claim["context"]

    best_result: dict[str, Any] = {
        "claim_text": claim_text,
        "value": value,
        "type": claim["type"],
        "source_file": None,
        "match_type": "none",
        "matched_text": None,
        "score": None,
    }

    for file_path in source_files:
        lines = _source_lines_cache.get(file_path)
        if lines is None:
            lines = _split_lines(_read_text(file_path))
            _source_lines_cache[file_path] = lines
        match_type, matched_text, score = _search_in_lines(value, lines)
        if match_type == "exact":
            return {
                "claim_text": claim_text,
                "value": value,
                "type": claim["type"],
                "source_file": str(file_path.relative_to(VAULT_ROOT)),
                "match_type": "exact",
                "matched_text": matched_text,
                "score": 100,
            }
        if match_type == "partial":
            # Keep best partial so far
            if best_result["match_type"] == "none" or (
                score is not None
                and best_result["score"] is not None
                and score > best_result["score"]
            ):
                best_result = {
                    "claim_text": claim_text,
                    "value": value,
                    "type": claim["type"],
                    "source_file": str(file_path.relative_to(VAULT_ROOT)),
                    "match_type": "partial",
                    "matched_text": matched_text,
                    "score": score,
                }

    return best_result


# ---------------------------------------------------------------------------
# Main verification routine
# ---------------------------------------------------------------------------

def verify_article(article_path: Path) -> dict[str, Any]:
    """
    Full verification pass on a wiki article.

    Returns a dict with keys:
        title, article, claims_found, results, summary
    """
    _source_lines_cache.clear()
    article_path = article_path.resolve()
    text = _read_text(article_path)
    fm = parse_file(article_path)
    title = fm.get("title") or article_path.stem.replace("-", " ").title()

    body = _strip_frontmatter(text)
    claims = extract_claims(body)

    source_files, source_warnings = resolve_sources(fm)

    results: list[dict[str, Any]] = []
    for claim in claims:
        result = verify_claim(claim, source_files)
        results.append(result)

    # Summary statistics
    exact = sum(1 for r in results if r["match_type"] == "exact")
    partial = sum(1 for r in results if r["match_type"] == "partial")
    unmatched = sum(1 for r in results if r["match_type"] == "none")
    total = len(results)

    if total == 0:
        confidence = "HIGH"
    elif total > 0 and exact / total > 0.8:
        confidence = "HIGH"
    elif total > 0 and (exact + partial) / total > 0.5:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "title": title,
        "article": str(article_path.relative_to(VAULT_ROOT)),
        "claims_found": total,
        "source_warnings": source_warnings,
        "results": results,
        "summary": {
            "exact_matches": exact,
            "partial_matches": partial,
            "unmatched_claims": unmatched,
            "confidence": confidence,
        },
    }


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------

_MATCH_SYMBOLS = {
    "exact": "✓ EXACT  ",
    "partial": "~ PARTIAL",
    "none": "✗ NONE   ",
}


def _human_output(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Verification Report: {report['title']}")
    lines.append("")

    source_warnings = report.get("source_warnings", [])
    if source_warnings:
        lines.append("## Source Resolution Warnings")
        for w in source_warnings:
            lines.append(f"  ! {w}")
        lines.append(
            "  → Fix source coverage first: "
            "uv run python _vault/lib/lint.py"
        )
        lines.append("")

    lines.append(f"## Claims Found: {report['claims_found']}")
    lines.append("")

    if not report["results"]:
        lines.append("No verifiable claims detected in this article.")
    else:
        for r in report["results"]:
            symbol = _MATCH_SYMBOLS.get(r["match_type"], "? UNKNOWN")
            claim_snippet = r["claim_text"]
            # Truncate long context for readability
            if len(claim_snippet) > 80:
                claim_snippet = claim_snippet[:80].rstrip() + "…"

            if r["match_type"] == "exact":
                matched_snippet = r["matched_text"] or ""
                if len(matched_snippet) > 60:
                    matched_snippet = matched_snippet[:60].rstrip() + "…"
                lines.append(
                    f'{symbol}  "{claim_snippet}" — matched in '
                    f'{r["source_file"]} (line: "{matched_snippet}")'
                )
            elif r["match_type"] == "partial":
                lines.append(
                    f'{symbol}  "{claim_snippet}" — partial match in '
                    f'{r["source_file"]} (score: {r["score"]})'
                )
            else:
                lines.append(
                    f'{symbol}  "{claim_snippet}" — no source match found'
                )

    lines.append("")
    lines.append("## Summary")
    s = report["summary"]
    lines.append(f"- Exact matches:    {s['exact_matches']}")
    lines.append(f"- Partial matches:  {s['partial_matches']}")
    lines.append(f"- Unmatched claims: {s['unmatched_claims']}")
    lines.append(f"- Confidence:       {s['confidence']}")

    if not _FUZZY_AVAILABLE:
        lines.append("")
        lines.append(
            "Note: thefuzz is not installed — only exact matching was performed. "
            "Install with: pip install thefuzz"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed Vault claim verification engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Extracts verifiable claims (numbers, dates, measurements) from a\n"
            "wiki article and matches them against raw source files."
        ),
    )
    parser.add_argument(
        "article_path",
        type=Path,
        help="Path to the wiki article to verify.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON.",
    )
    args = parser.parse_args(argv)

    article_path = args.article_path
    if not article_path.is_absolute():
        article_path = Path.cwd() / article_path
    article_path = article_path.resolve()

    if not article_path.exists():
        print(f"Error: article not found: {article_path}", file=sys.stderr)
        return 1

    if not article_path.is_file():
        print(f"Error: not a file: {article_path}", file=sys.stderr)
        return 1

    report = verify_article(article_path)

    if args.json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_human_output(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())

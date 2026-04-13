"""
lint.py — Structural lint checker for the Seed Vault wiki.

Performs 9 deterministic checks with NO LLM involvement.

Usage:
    python -m _vault.lib.lint [--json] [--fix-backlinks]
    python _vault/lib/lint.py [--json] [--fix-backlinks]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Vault root detection
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"
INDEX_FILE = WIKI_DIR / "_index.md"

# ---------------------------------------------------------------------------
# Frontmatter helpers — prefer the shared module, fall back to regex
# ---------------------------------------------------------------------------

try:
    from _vault.lib.frontmatter import parse_file as _fm_parse_file, scan_directory as _fm_scan_directory

    def parse_file(path: Path) -> dict:
        return _fm_parse_file(path)

    def scan_directory(dirpath: Path, fields=None) -> list[dict]:
        return _fm_scan_directory(dirpath, fields)

except ImportError:
    import yaml  # type: ignore

    _FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    def _parse_frontmatter_str(text: str) -> dict:
        m = _FM_RE.match(text)
        if not m:
            return {}
        try:
            result = yaml.safe_load(m.group(1))
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    def parse_file(path: Path) -> dict:  # type: ignore[misc]
        try:
            text = path.read_text(encoding="utf-8")
            return _parse_frontmatter_str(text)
        except (OSError, UnicodeDecodeError):
            return {}

    def scan_directory(dirpath: Path, fields=None) -> list[dict]:  # type: ignore[misc]
        results = []
        root = Path(dirpath)
        for md_file in sorted(root.rglob("*.md")):
            metadata = parse_file(md_file)
            if fields is not None:
                metadata = {k: metadata[k] for k in fields if k in metadata}
            results.append({"path": str(md_file), "metadata": metadata})
        return results


# ---------------------------------------------------------------------------
# Shared data-loading helpers
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _strip_frontmatter(text: str) -> str:
    """Return the body of a markdown file with frontmatter removed."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if m:
        return text[m.end():]
    return text


def _wiki_files(exclude_meta: bool = True) -> list[Path]:
    """All .md files under wiki/. Optionally exclude _index and _catalog."""
    if not WIKI_DIR.exists():
        return []
    files = list(WIKI_DIR.rglob("*.md"))
    if exclude_meta:
        files = [
            f for f in files
            if not any(part.startswith("_") for part in f.relative_to(WIKI_DIR).parts[:-1])
            or f.name.startswith("_")
            # actually keep files whose *name* starts with _ but exclude none of the content files
        ]
        # Simpler: just drop the two meta files from orphan checks etc.
        # For wikilink scanning we want ALL files.
    return files


def _all_wiki_files() -> list[Path]:
    if not WIKI_DIR.exists():
        return []
    return list(WIKI_DIR.rglob("*.md"))


def _content_wiki_files() -> list[Path]:
    """Wiki files that are not meta/index files."""
    skip_names = {"_index.md", "_catalog.md", "_index.base", "_catalog.base", "_migration-log.md", "_log.md"}
    return [f for f in _all_wiki_files() if f.name not in skip_names]


# Build a mapping: normalised title → Path, for wikilink resolution.
def _build_title_map() -> dict[str, Path]:
    """
    Returns dict: lower(title) → Path.
    Falls back to stem-to-title-case if no frontmatter title.
    """
    title_map: dict[str, Path] = {}
    for f in _all_wiki_files():
        fm = parse_file(f)
        title = fm.get("title", "")
        if title:
            title_map[title.lower()] = f
        # Also index by stem converted to Title Case (space-separated)
        stem_title = f.stem.replace("-", " ").replace("_", " ").title()
        title_map.setdefault(stem_title.lower(), f)
    return title_map


def _extract_wikilinks(text: str) -> list[str]:
    """Extract wikilink targets from markdown content (body only, not frontmatter)."""
    # [[Target]], [[Target|Alias]], [[Target#Section]], [[Target#Section|Alias]]
    return re.findall(r"\[\[([^\]#|]+)", text)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Check 1: Broken wikilinks
# ---------------------------------------------------------------------------

def check_broken_wikilinks() -> dict:
    title_map = _build_title_map()
    issues: list[str] = []

    for f in _all_wiki_files():
        text = _read_text(f)
        body = _strip_frontmatter(text)
        links = _extract_wikilinks(body)
        rel = f.relative_to(VAULT_ROOT)
        for target in links:
            target_clean = target.strip()
            if target_clean.lower() not in title_map:
                issues.append(f"{rel}: broken wikilink [[{target_clean}]]")

    return {
        "check": "broken_wikilinks",
        "severity": "error",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 2: Orphan pages
# ---------------------------------------------------------------------------

def check_orphan_pages() -> dict:
    skip_names = {"_index.md", "_catalog.md", "_migration-log.md", "_log.md"}
    all_files = _all_wiki_files()
    content_files = [f for f in all_files if f.name not in skip_names]

    # Count incoming links per file path
    title_map = _build_title_map()
    # Reverse map: path → set of normalised titles that resolve to it
    path_to_titles: dict[Path, set[str]] = defaultdict(set)
    for norm_title, path in title_map.items():
        path_to_titles[path].add(norm_title)

    incoming: dict[Path, int] = {f: 0 for f in content_files}

    for f in all_files:
        text = _read_text(f)
        body = _strip_frontmatter(text)
        links = _extract_wikilinks(body)
        for target in links:
            target_lower = target.strip().lower()
            resolved = title_map.get(target_lower)
            if resolved and resolved in incoming and resolved != f:
                incoming[resolved] += 1

    # Also count frontmatter sources: links from sources: field
    for f in all_files:
        fm = parse_file(f)
        for src in fm.get("sources", []) or []:
            # sources entries look like [[Source Name]]
            m = re.match(r"\[\[([^\]#|]+)", str(src))
            if m:
                target_lower = m.group(1).strip().lower()
                resolved = title_map.get(target_lower)
                if resolved and resolved in incoming and resolved != f:
                    incoming[resolved] += 1

    issues = []
    for f, count in incoming.items():
        if count == 0:
            issues.append(str(f.relative_to(VAULT_ROOT)))

    return {
        "check": "orphan_pages",
        "severity": "warning",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 3: Missing backlinks
# ---------------------------------------------------------------------------

def check_missing_backlinks() -> dict:
    """For each link A→B found in content, check if B→A also exists."""
    title_map = _build_title_map()

    # Build a mapping: path → set of paths it links to (body only)
    outgoing: dict[Path, set[Path]] = {}
    for f in _all_wiki_files():
        text = _read_text(f)
        body = _strip_frontmatter(text)
        links = _extract_wikilinks(body)
        targets: set[Path] = set()
        for target in links:
            resolved = title_map.get(target.strip().lower())
            if resolved and resolved != f:
                targets.add(resolved)
        outgoing[f] = targets

    issues: list[str] = []
    checked: set[tuple[Path, Path]] = set()

    for a, targets in outgoing.items():
        for b in targets:
            if (a, b) in checked or (b, a) in checked:
                continue
            checked.add((a, b))
            # Check if b links back to a
            b_targets = outgoing.get(b, set())
            if a not in b_targets:
                a_rel = a.relative_to(VAULT_ROOT)
                b_rel = b.relative_to(VAULT_ROOT)
                a_title = parse_file(a).get("title") or a.stem.replace("-", " ").title()
                b_title = parse_file(b).get("title") or b.stem.replace("-", " ").title()
                issues.append(
                    f"{b_rel}: missing backlink to [[{a_title}]] (linked from {a_rel})"
                )

    return {
        "check": "missing_backlinks",
        "severity": "warning",
        "issues": issues,
        "auto_fixable": True,
    }


# ---------------------------------------------------------------------------
# Check 4: Stale articles
# ---------------------------------------------------------------------------

def check_stale_articles() -> dict:
    """Article is stale if any source summary's updated: date is newer."""
    title_map = _build_title_map()
    issues: list[str] = []

    for f in _content_wiki_files():
        fm = parse_file(f)
        article_updated = _parse_date(fm.get("updated"))
        if article_updated is None:
            continue

        sources = fm.get("sources", []) or []
        for src in sources:
            m = re.match(r"\[\[([^\]#|]+)", str(src))
            if not m:
                continue
            target_lower = m.group(1).strip().lower()
            src_path = title_map.get(target_lower)
            if src_path is None:
                continue
            src_fm = parse_file(src_path)
            src_updated = _parse_date(src_fm.get("updated"))
            if src_updated is not None and src_updated > article_updated:
                issues.append(
                    f"{f.relative_to(VAULT_ROOT)}: stale — source "
                    f"[[{m.group(1).strip()}]] updated {src_updated} "
                    f"> article updated {article_updated}"
                )
                break  # one report per article is enough

    return {
        "check": "stale_articles",
        "severity": "info",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 5: Index sync
# ---------------------------------------------------------------------------

def check_index_sync() -> dict:
    """Diff wiki article files against entries in _index.md."""
    issues: list[str] = []

    if not INDEX_FILE.exists():
        return {
            "check": "index_sync",
            "severity": "warning",
            "issues": ["_index.md does not exist"],
            "auto_fixable": False,
        }

    index_text = _read_text(INDEX_FILE)
    # Extract all wikilinks from the index body
    index_links_raw = _extract_wikilinks(_strip_frontmatter(index_text))
    index_titles_lower: set[str] = {t.strip().lower() for t in index_links_raw}

    title_map = _build_title_map()
    # Reverse: path → canonical title
    path_to_canonical: dict[Path, str] = {}
    for f in _content_wiki_files():
        fm = parse_file(f)
        title = fm.get("title") or f.stem.replace("-", " ").title()
        path_to_canonical[f] = title

    # Articles missing from index
    for f, title in path_to_canonical.items():
        if title.lower() not in index_titles_lower:
            issues.append(
                f"article not in _index.md: [[{title}]] ({f.relative_to(VAULT_ROOT)})"
            )

    # Index entries with no corresponding file
    for raw_title in index_links_raw:
        t = raw_title.strip()
        if t.lower() not in title_map:
            issues.append(f"_index.md entry has no file: [[{t}]]")

    return {
        "check": "index_sync",
        "severity": "warning",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 6: Raw coverage
# ---------------------------------------------------------------------------

def check_raw_coverage() -> dict:
    """Every file in raw/ should have a source summary that references it via original_source:."""
    issues: list[str] = []

    if not RAW_DIR.exists():
        return {
            "check": "raw_coverage",
            "severity": "info",
            "issues": [],
            "auto_fixable": False,
        }

    # Build the set of raw file paths referenced by any summary's original_source field.
    # Summaries record: original_source: "[[raw/kebab-name]]"
    # We normalise to just the stem for matching.
    covered_stems: set[str] = set()
    sources_dir = WIKI_DIR / "sources"
    if sources_dir.exists():
        for summary in sources_dir.rglob("*.md"):
            fm = parse_file(summary)
            orig = str(fm.get("original_source", "") or "")
            # Extract the path part from [[raw/some-name]] or [[raw/some-name.md]]
            m = re.search(r"\[\[raw/([^\]#|]+)", orig)
            if m:
                covered_stems.add(Path(m.group(1)).stem.lower())

    for raw_file in sorted(RAW_DIR.rglob("*.md")):
        if raw_file.stem.lower() not in covered_stems:
            issues.append(
                f"raw/{raw_file.relative_to(RAW_DIR)}: no source summary references this file"
            )

    return {
        "check": "raw_coverage",
        "severity": "info",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 7: Tag frequency (singleton tags)
# ---------------------------------------------------------------------------

def check_tag_frequency() -> dict:
    """Flag tags used only once across the wiki."""
    tag_counts: dict[str, int] = defaultdict(int)
    tag_files: dict[str, list[str]] = defaultdict(list)

    for f in _content_wiki_files():
        fm = parse_file(f)
        tags = fm.get("tags", []) or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]
        for tag in tags:
            tag_str = str(tag).strip()
            if tag_str:
                tag_counts[tag_str] += 1
                tag_files[tag_str].append(str(f.relative_to(VAULT_ROOT)))

    issues: list[str] = []
    for tag, count in sorted(tag_counts.items()):
        if count == 1:
            issues.append(
                f"singleton tag '{tag}' used only in: {tag_files[tag][0]}"
            )

    return {
        "check": "tag_frequency",
        "severity": "info",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 8: Missing topic hubs
# ---------------------------------------------------------------------------

def check_missing_topic_hubs() -> dict:
    """Tags shared by 3+ concepts with no wiki/topics/ hub page."""
    concepts_dir = WIKI_DIR / "concepts"
    topics_dir = WIKI_DIR / "topics"

    tag_concept_count: dict[str, int] = defaultdict(int)

    if concepts_dir.exists():
        for f in concepts_dir.rglob("*.md"):
            fm = parse_file(f)
            tags = fm.get("tags", []) or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",")]
            for tag in tags:
                tag_str = str(tag).strip()
                if tag_str:
                    tag_concept_count[tag_str] += 1

    # Build set of existing hub slugs from topics dir
    existing_hub_slugs: set[str] = set()
    if topics_dir.exists():
        for f in topics_dir.rglob("*.md"):
            existing_hub_slugs.add(f.stem.lower().replace("-", " "))
            fm = parse_file(f)
            title = fm.get("title", "")
            if title:
                # Strip "Topic - " prefix if present
                hub_name = re.sub(r"^topic\s*-\s*", "", title, flags=re.IGNORECASE).lower()
                existing_hub_slugs.add(hub_name)
                existing_hub_slugs.add(title.lower())

    issues: list[str] = []
    for tag, count in sorted(tag_concept_count.items()):
        if count >= 3:
            # Check if a hub exists for this tag
            # Normalise: strip hierarchy prefix (e.g. "biology/genetics" → also check "genetics")
            parts = tag.lower().replace("/", " ").replace("-", " ").split()
            tag_variants = {tag.lower(), " ".join(parts), parts[-1] if parts else tag.lower()}
            if not tag_variants.intersection(existing_hub_slugs):
                issues.append(
                    f"tag '{tag}' used by {count} concepts but no topics/ hub page found"
                )

    return {
        "check": "missing_topic_hubs",
        "severity": "info",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 9: Unhubbed concepts
# ---------------------------------------------------------------------------

def check_unhubbed_concepts() -> dict:
    """Concepts with no [[Topic - ...]] wikilink reference in their content."""
    concepts_dir = WIKI_DIR / "concepts"
    if not concepts_dir.exists():
        return {
            "check": "unhubbed_concepts",
            "severity": "warning",
            "issues": [],
            "auto_fixable": False,
        }

    topic_link_re = re.compile(r"\[\[Topic\s*-", re.IGNORECASE)
    issues: list[str] = []

    for f in sorted(concepts_dir.rglob("*.md")):
        text = _read_text(f)
        body = _strip_frontmatter(text)
        if not topic_link_re.search(body):
            issues.append(
                f"{f.relative_to(VAULT_ROOT)}: concept has no [[Topic - ...]] wikilink"
            )

    return {
        "check": "unhubbed_concepts",
        "severity": "warning",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Auto-fix: backlinks
# ---------------------------------------------------------------------------

def _fix_backlinks(missing_backlinks_issues: list[str]) -> int:
    """
    Auto-fix missing backlinks by appending to ## See Also section.

    Each issue string has the form:
        "wiki/path/to/b.md: missing backlink to [[Title A]] (linked from wiki/path/to/a.md)"

    Returns number of files modified.
    """
    # Re-run collection to get structured data
    title_map = _build_title_map()

    outgoing: dict[Path, set[Path]] = {}
    for f in _all_wiki_files():
        text = _read_text(f)
        body = _strip_frontmatter(text)
        links = _extract_wikilinks(body)
        targets: set[Path] = set()
        for target in links:
            resolved = title_map.get(target.strip().lower())
            if resolved and resolved != f:
                targets.add(resolved)
        outgoing[f] = targets

    # Collect backlinks to add: target_path → set of title strings to add
    to_add: dict[Path, set[str]] = defaultdict(set)
    checked: set[tuple[Path, Path]] = set()

    for a, targets in outgoing.items():
        for b in targets:
            if (a, b) in checked or (b, a) in checked:
                continue
            checked.add((a, b))
            b_targets = outgoing.get(b, set())
            if a not in b_targets:
                a_title = parse_file(a).get("title") or a.stem.replace("-", " ").title()
                to_add[b].add(a_title)

    modified = 0
    for file_path, titles in to_add.items():
        text = file_path.read_text(encoding="utf-8")
        see_also_re = re.compile(r"(^## See Also\s*\n)", re.MULTILINE | re.IGNORECASE)
        new_links = "\n".join(f"- [[{t}]]" for t in sorted(titles))

        if see_also_re.search(text):
            # Append after the heading
            text = see_also_re.sub(r"\1" + new_links + "\n", text, count=1)
        else:
            # Append a new See Also section at the end
            text = text.rstrip("\n") + f"\n\n## See Also\n{new_links}\n"

        file_path.write_text(text, encoding="utf-8")
        modified += 1

    return modified


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_broken_wikilinks,
    check_orphan_pages,
    check_missing_backlinks,
    check_stale_articles,
    check_index_sync,
    check_raw_coverage,
    check_tag_frequency,
    check_missing_topic_hubs,
    check_unhubbed_concepts,
]


def run_all_checks() -> list[dict]:
    return [check() for check in ALL_CHECKS]


# ---------------------------------------------------------------------------
# Human-readable output
# ---------------------------------------------------------------------------

_SEVERITY_EMOJI = {
    "error": "ERROR  ",
    "warning": "WARNING",
    "info": "INFO   ",
}

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _human_output(results: list[dict]) -> str:
    lines: list[str] = []
    total_errors = sum(len(r["issues"]) for r in results if r["severity"] == "error")
    total_warnings = sum(len(r["issues"]) for r in results if r["severity"] == "warning")
    total_info = sum(len(r["issues"]) for r in results if r["severity"] == "info")

    for result in results:
        check = result["check"]
        severity = result["severity"]
        issues = result["issues"]
        fixable = result.get("auto_fixable", False)
        label = _SEVERITY_EMOJI.get(severity, severity.upper())
        fix_note = " [auto-fixable with --fix-backlinks]" if fixable else ""
        lines.append(f"\n[{label}] {check}{fix_note}")
        if issues:
            for issue in issues:
                lines.append(f"  - {issue}")
        else:
            lines.append("  (no issues)")

    lines.append(
        f"\nSummary: {total_errors} error(s), {total_warnings} warning(s), {total_info} info(s)"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed Vault structural lint checker (no LLM).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--fix-backlinks",
        action="store_true",
        help="Auto-fix missing backlinks by appending to ## See Also sections.",
    )
    args = parser.parse_args(argv)

    results = run_all_checks()

    if args.fix_backlinks:
        backlink_result = next(
            (r for r in results if r["check"] == "missing_backlinks"), None
        )
        issues = backlink_result["issues"] if backlink_result else []
        n = _fix_backlinks(issues)
        if not args.json_output:
            print(f"Fixed backlinks in {n} file(s). Re-running checks...")
        # Re-run after fix
        results = run_all_checks()

    if args.json_output:
        print(json.dumps(results, indent=2, default=str))
    else:
        print(_human_output(results))

    # Exit code: 1 if any errors, 0 otherwise
    has_errors = any(r["severity"] == "error" and r["issues"] for r in results)
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())

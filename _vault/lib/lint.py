"""
lint.py — Structural lint checker for the Seed Vault wiki.

Performs 9 deterministic checks with NO LLM involvement.
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

# Add vault root to path to allow relative imports of _vault.lib
sys.path.append(str(VAULT_ROOT))

from _vault.lib.frontmatter import (
    parse_file, 
    scan_directory, 
    slugify, 
    build_vault_map, 
    resolve_link
)

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


def _all_wiki_files() -> list[Path]:
    if not WIKI_DIR.exists():
        return []
    return list(WIKI_DIR.rglob("*.md"))


def _content_wiki_files() -> list[Path]:
    """Wiki files that are not meta/index files."""
    skip_names = {"_index.md", "_catalog.md", "_index.base", "_catalog.base", "_migration-log.md", "_log.md"}
    return [f for f in _all_wiki_files() if f.name not in skip_names]


def _build_title_map() -> dict[str, Path]:
    """Uses the centralized build_vault_map logic."""
    return build_vault_map(WIKI_DIR)


def _extract_wikilinks(text: str) -> list[str]:
    """
    Extract wikilink targets from markdown content (body only, not frontmatter).
    Returns only the target part (before | or #).
    """
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
    vault_map = _build_title_map()
    issues: list[str] = []

    for f in _all_wiki_files():
        text = _read_text(f)
        fm = parse_file(f)
        body = _strip_frontmatter(text)
        rel = f.relative_to(VAULT_ROOT)

        # 1. Check body wikilinks
        links = _extract_wikilinks(body)
        for target in links:
            if not resolve_link(target, vault_map):
                issues.append(f"{rel}: broken wikilink [[{target}]]")

        # 2. Check frontmatter wikilinks
        for field in ("sources", "original_source"):
            val = fm.get(field)
            if not val:
                continue
            
            candidates = val if isinstance(val, list) else [val]
            for cand in candidates:
                m = re.search(r"\[\[([^\]#|]+)", str(cand))
                if m:
                    target = m.group(1).strip()
                    if not resolve_link(target, vault_map):
                        issues.append(f"{rel}: broken wikilink in frontmatter field '{field}': [[{m.group(1).strip()}]]")

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

    vault_map = build_vault_map(WIKI_DIR)
    incoming: dict[Path, int] = {f: 0 for f in content_files}

    for f in all_files:
        text = _read_text(f)
        fm = parse_file(f)
        body = _strip_frontmatter(text)
        
        links = _extract_wikilinks(body)
        for target in links:
            resolved = resolve_link(target, vault_map)
            if resolved and resolved in incoming and resolved != f:
                incoming[resolved] += 1

        for src in fm.get("sources", []) or []:
            m = re.search(r"\[\[([^\]#|]+)", str(src))
            if m:
                resolved = resolve_link(m.group(1).strip(), vault_map)
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
    vault_map = build_vault_map(WIKI_DIR)

    outgoing: dict[Path, set[Path]] = {}
    for f in _all_wiki_files():
        text = _read_text(f)
        body = _strip_frontmatter(text)
        links = _extract_wikilinks(body)
        targets: set[Path] = set()
        for target in links:
            resolved = resolve_link(target, vault_map)
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
            b_targets = outgoing.get(b, set())
            if a not in b_targets:
                a_rel = a.relative_to(VAULT_ROOT)
                b_rel = b.relative_to(VAULT_ROOT)
                a_title = parse_file(a).get("title") or a.stem.replace("-", " ").title()
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
    vault_map = build_vault_map(WIKI_DIR)
    issues: list[str] = []

    for f in _content_wiki_files():
        fm = parse_file(f)
        article_updated = _parse_date(fm.get("updated"))
        if article_updated is None:
            continue

        sources = fm.get("sources", []) or []
        for src in sources:
            m = re.search(r"\[\[([^\]#|]+)", str(src))
            if not m:
                continue
            
            src_path = resolve_link(m.group(1).strip(), vault_map)
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
                break

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
    issues: list[str] = []

    if not INDEX_FILE.exists():
        return {
            "check": "index_sync",
            "severity": "warning",
            "issues": ["_index.md does not exist"],
            "auto_fixable": False,
        }

    index_text = _read_text(INDEX_FILE)
    index_targets_raw = _extract_wikilinks(_strip_frontmatter(index_text))
    
    vault_map = build_vault_map(WIKI_DIR)
    
    for f in _content_wiki_files():
        fm = parse_file(f)
        title = fm.get("title", f.stem)
        
        found = False
        for target in index_targets_raw:
            if resolve_link(target, vault_map) == f:
                found = True
                break
        
        if not found:
            issues.append(
                f"article not in _index.md: [[{title}]] ({f.relative_to(VAULT_ROOT)})"
            )

    for target in index_targets_raw:
        if not resolve_link(target, vault_map):
            issues.append(f"_index.md entry has no file: [[{target}]]")

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
    issues: list[str] = []

    if not RAW_DIR.exists():
        return {
            "check": "raw_coverage",
            "severity": "info",
            "issues": [],
            "auto_fixable": False,
        }

    covered_stems: set[str] = set()
    sources_dir = WIKI_DIR / "sources"
    if sources_dir.exists():
        for summary in sources_dir.rglob("*.md"):
            fm = parse_file(summary)
            orig = str(fm.get("original_source", "") or "")
            sources = fm.get("sources", []) or []
            if isinstance(sources, str):
                sources = [sources]
            
            candidates = [orig] + [str(s) for s in sources]
            for candidate in candidates:
                m = re.search(r"\[\[raw/([^\]#|]+)", candidate)
                if m:
                    covered_stems.add(slugify(Path(m.group(1)).stem))

    for raw_file in sorted(RAW_DIR.rglob("*.md")):
        if slugify(raw_file.stem) not in covered_stems:
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
# Check 7: Tag frequency
# ---------------------------------------------------------------------------

def check_tag_frequency() -> dict:
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


ALL_CHECKS = [
    check_broken_wikilinks,
    check_orphan_pages,
    check_missing_backlinks,
    check_stale_articles,
    check_index_sync,
    check_raw_coverage,
    check_tag_frequency,
]

def run_all_checks() -> list[dict]:
    return [check() for check in ALL_CHECKS]

_SEVERITY_ORDER = ("error", "warning", "info")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Vault structural lint checker (no LLM).")
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")
    args = parser.parse_args()

    results = run_all_checks()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for res in results:
            if not res["issues"]:
                continue
            severity = res["severity"].upper().ljust(7)
            print(f"[{severity}] {res['check']}")
            for issue in res["issues"]:
                print(f"  - {issue}")
            print()

        counts = {sev: 0 for sev in _SEVERITY_ORDER}
        for res in results:
            counts[res["severity"]] = counts.get(res["severity"], 0) + len(res["issues"])

        summary = ", ".join(f"{counts[sev]} {sev}(s)" for sev in _SEVERITY_ORDER)
        print(f"Summary: {summary}")

    has_errors = any(r["severity"] == "error" and r["issues"] for r in results)
    return 1 if has_errors else 0

if __name__ == "__main__":
    sys.exit(main())

"""
lint.py — Structural lint checker for the Seed Vault wiki.

Performs 8 deterministic checks with NO LLM involvement.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root detection
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"
INDEX_FILE = WIKI_DIR / "_index.md"

# Add vault root to path to allow relative imports of _vault.lib
sys.path.append(str(VAULT_ROOT))

from _vault.lib.vault_frontmatter import (  # noqa: E402
    build_vault_map,
    extract_frontmatter_links,
    extract_wikilinks,
    is_meta_file,
    parse_date,
    parse_file,
    resolve_link,
    slugify,
)

# ---------------------------------------------------------------------------
# Shared data-loading helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


@lru_cache(maxsize=None)
def _cached_parse_file(path: Path) -> dict:
    return parse_file(path)


def _strip_frontmatter(text: str) -> str:
    """Return the body of a markdown file with frontmatter removed."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    if m:
        return text[m.end():]
    return text


@lru_cache(maxsize=1)
def _all_wiki_files() -> tuple[Path, ...]:
    if not WIKI_DIR.exists():
        return ()
    return tuple(WIKI_DIR.rglob("*.md"))


def _content_wiki_files() -> list[Path]:
    """Wiki files that are not meta/index files."""
    return [f for f in _all_wiki_files() if not is_meta_file(f)]


@lru_cache(maxsize=1)
def _cached_vault_map() -> dict[str, Path]:
    return build_vault_map(WIKI_DIR)


def _raw_target_exists(raw_rel: str) -> bool:
    """Return True if a raw/ wikilink target resolves to a file under raw/.

    Matches on slugified stem so '[[raw/foo-bar]]' finds raw/foo-bar.md (or any
    raw file whose stem slugifies the same way).
    """
    if not RAW_DIR.exists():
        return False
    wanted = slugify(Path(raw_rel).stem)
    return any(
        p.is_file() and slugify(p.stem) == wanted
        for p in RAW_DIR.rglob("*")
    )


# ---------------------------------------------------------------------------
# Check 1: Broken wikilinks
# ---------------------------------------------------------------------------

def check_broken_wikilinks() -> dict:
    vault_map = _cached_vault_map()
    issues: list[str] = []

    for f in _all_wiki_files():
        text = _read_text(f)
        fm = _cached_parse_file(f)
        body = _strip_frontmatter(text)
        rel = f.relative_to(VAULT_ROOT)

        for target in extract_wikilinks(body):
            if not resolve_link(target, vault_map):
                issues.append(f"{rel}: broken wikilink [[{target}]]")

        for field in ("sources", "original_source"):
            for target in extract_frontmatter_links(fm, field):
                # raw/ links point at raw source files, which are not wiki
                # articles and so never appear in the wiki vault_map. Validate
                # them against the raw/ directory instead of flagging as broken.
                if target.startswith("raw/"):
                    if not _raw_target_exists(target[len("raw/"):]):
                        issues.append(
                            f"{rel}: broken wikilink in frontmatter field '{field}': [[{target}]]"
                        )
                    continue
                if not resolve_link(target, vault_map):
                    issues.append(
                        f"{rel}: broken wikilink in frontmatter field '{field}': [[{target}]]"
                    )

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
    # Iterate content files only — _index.md mechanically links every article,
    # so counting it as a backlink source would mask true orphans.
    content_files = _content_wiki_files()

    vault_map = _cached_vault_map()
    incoming: dict[Path, int] = {f: 0 for f in content_files}

    def bump(target: str, source: Path) -> None:
        resolved = resolve_link(target, vault_map)
        if resolved and resolved in incoming and resolved != source:
            incoming[resolved] += 1

    for f in content_files:
        text = _read_text(f)
        fm = _cached_parse_file(f)
        body = _strip_frontmatter(text)

        for target in extract_wikilinks(body):
            bump(target, f)
        for target in extract_frontmatter_links(fm, "sources"):
            bump(target, f)

    issues = [
        str(f.relative_to(VAULT_ROOT))
        for f, count in incoming.items()
        if count == 0
    ]

    return {
        "check": "orphan_pages",
        "severity": "warning",
        "issues": issues,
        "auto_fixable": False,
    }


# ---------------------------------------------------------------------------
# Check 3: Missing backlinks
# ---------------------------------------------------------------------------

def _outgoing_map() -> dict[Path, set[Path]]:
    """Map each content wiki file to the set of content files it links to.

    Content files only — _index.md mechanically links every article, so
    treating it as a link source would flag every article as "missing a
    backlink to the index" (same reasoning as check_orphan_pages).
    """
    vault_map = _cached_vault_map()
    outgoing: dict[Path, set[Path]] = {}
    for f in _content_wiki_files():
        body = _strip_frontmatter(_read_text(f))
        targets: set[Path] = set()
        for target in extract_wikilinks(body):
            resolved = resolve_link(target, vault_map)
            if resolved and resolved != f:
                targets.add(resolved)
        outgoing[f] = targets
    return outgoing


def _missing_backlink_pairs() -> list[tuple[Path, Path]]:
    """Return (a, b) pairs where a links b but b has no backlink to a.

    The fix for each pair is to add a link to ``a`` into ``b``.
    """
    outgoing = _outgoing_map()
    pairs: list[tuple[Path, Path]] = []
    checked: set[tuple[Path, Path]] = set()
    for a, targets in outgoing.items():
        for b in targets:
            if (a, b) in checked or (b, a) in checked:
                continue
            checked.add((a, b))
            if a not in outgoing.get(b, set()):
                pairs.append((a, b))
    return pairs


def check_missing_backlinks() -> dict:
    issues: list[str] = []
    for a, b in _missing_backlink_pairs():
        a_rel = a.relative_to(VAULT_ROOT)
        b_rel = b.relative_to(VAULT_ROOT)
        a_title = _cached_parse_file(a).get("title") or a.stem.replace("-", " ").title()
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
# Auto-fix: insert reciprocal backlinks (deterministic — no LLM)
# ---------------------------------------------------------------------------

def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_block_incl_delims, body). Empty fm if none."""
    m = re.match(r"^(---\s*\n.*?\n---\s*\n)", text, re.DOTALL)
    if m:
        return m.group(1), text[m.end():]
    return "", text


def _bump_updated(frontmatter_block: str, today: str) -> str:
    """Set the frontmatter `updated:` line to today, preserving everything else."""
    if not frontmatter_block:
        return frontmatter_block
    new_block, _n = re.subn(
        r"(?m)^updated:.*$", f"updated: {today}", frontmatter_block
    )
    return new_block


def _insert_see_also_link(body: str, link: str) -> str:
    """Add ``- {link}`` under a ``## See Also`` section, creating it if absent."""
    bullet = f"- {link}"
    heading = re.search(r"(?m)^##\s+See Also[ \t]*$", body)
    if heading:
        start = heading.end()
        next_h2 = re.search(r"(?m)^##\s+", body[start:])
        section_end = start + next_h2.start() if next_h2 else len(body)
        section = body[start:section_end].rstrip("\n")
        new_section = f"{section}\n{bullet}\n"
        if next_h2:
            new_section += "\n"
        return body[:start] + new_section + body[section_end:]
    return body.rstrip("\n") + f"\n\n## See Also\n\n{bullet}\n"


def fix_missing_backlinks() -> dict:
    """Insert each missing reciprocal backlink and bump the target's `updated:`.

    Idempotent: a target already linking the source is skipped. Meta/index
    files are never modified. Returns a report listing the edits made.
    """
    from datetime import date

    today = date.today().isoformat()
    fixed: list[str] = []

    for a, b in _missing_backlink_pairs():
        if is_meta_file(b):
            continue
        a_stem = a.stem
        a_title = _cached_parse_file(a).get("title") or a_stem.replace("-", " ").title()
        text = _read_text(b)
        fm, body = _split_frontmatter(text)
        # Idempotency: skip if the target already references the source stem.
        if re.search(r"\[\[" + re.escape(a_stem) + r"[\]|#]", body):
            continue
        link = f"[[{a_stem}|{a_title}]]"
        new_body = _insert_see_also_link(body, link)
        new_fm = _bump_updated(fm, today)
        b.write_text(new_fm + new_body, encoding="utf-8")
        fixed.append(f"{b.relative_to(VAULT_ROOT)}: added {link}")

    # Disk changed — invalidate cached reads so later checks see fresh content.
    _read_text.cache_clear()
    _cached_parse_file.cache_clear()
    _all_wiki_files.cache_clear()
    _cached_vault_map.cache_clear()

    return {
        "check": "missing_backlinks_fixed",
        "severity": "info",
        "fixed": fixed,
        "auto_fixable": True,
    }


# ---------------------------------------------------------------------------
# Check 4: Stale articles
# ---------------------------------------------------------------------------

def check_stale_articles() -> dict:
    vault_map = _cached_vault_map()
    issues: list[str] = []

    for f in _content_wiki_files():
        fm = _cached_parse_file(f)
        article_updated = parse_date(fm.get("updated"))
        if article_updated is None:
            continue

        for target in extract_frontmatter_links(fm, "sources"):
            src_path = resolve_link(target, vault_map)
            if src_path is None:
                continue

            src_fm = _cached_parse_file(src_path)
            src_updated = parse_date(src_fm.get("updated"))
            if src_updated is not None and src_updated > article_updated:
                issues.append(
                    f"{f.relative_to(VAULT_ROOT)}: stale — source "
                    f"[[{target}]] updated {src_updated} "
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
    index_targets_raw = extract_wikilinks(_strip_frontmatter(index_text))
    
    vault_map = _cached_vault_map()
    
    for f in _content_wiki_files():
        fm = _cached_parse_file(f)
        title = fm.get("title", f.stem)

        if not any(resolve_link(t, vault_map) == f for t in index_targets_raw):
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
            fm = _cached_parse_file(summary)
            for field in ("original_source", "sources"):
                for raw_path in extract_frontmatter_links(fm, field, prefix="raw/"):
                    covered_stems.add(slugify(Path(raw_path).stem))

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
        fm = _cached_parse_file(f)
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
# Check 8: Frontmatter schema validation
# ---------------------------------------------------------------------------

VERSION_FILE = VAULT_ROOT / "_vault" / "VERSION"

_VALID_TYPES = {"concept", "source-summary", "visualization", "output"}
_VALID_STATUS = {"draft", "reviewed", "verified"}

# Required frontmatter keys per article type. Kept deliberately conservative:
# visualization wrappers carry no llm_model, output/meta files are minimal.
_BASE_REQUIRED = {"title", "type", "created", "updated", "status", "tags", "framework_version"}
_REQUIRED_BY_TYPE = {
    "concept": _BASE_REQUIRED | {"sources", "llm_model"},
    "source-summary": _BASE_REQUIRED | {"sources", "llm_model"},
    "visualization": _BASE_REQUIRED | {"sources"},
    "output": {"title", "type", "created", "updated", "tags"},
}


def _current_framework_version() -> str:
    """Read the framework version from _vault/VERSION ('' if unavailable)."""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def check_frontmatter_schema() -> dict:
    """Validate required keys, enum values, and version stamping per article.

    Deterministic replacement for trusting the LLM to stamp frontmatter
    correctly: catches missing required keys, invalid type/status enums, a
    stale framework_version, and an empty llm_model.
    """
    issues: list[str] = []
    current_version = _current_framework_version()

    for f in _content_wiki_files():
        fm = _cached_parse_file(f)
        rel = f.relative_to(VAULT_ROOT)
        art_type = fm.get("type")

        # type enum (also selects the required-key set)
        if art_type not in _VALID_TYPES:
            issues.append(f"{rel}: invalid or missing type: {art_type!r}")
            continue

        for key in sorted(_REQUIRED_BY_TYPE[art_type]):
            if key not in fm or fm.get(key) in (None, ""):
                issues.append(f"{rel}: missing required key '{key}' for type {art_type}")

        status = fm.get("status")
        if status is not None and status not in _VALID_STATUS:
            issues.append(f"{rel}: invalid status: {status!r}")

        fw = fm.get("framework_version")
        if current_version and fw is not None and str(fw) != current_version:
            issues.append(
                f"{rel}: stale framework_version {fw!r} (current is {current_version!r})"
            )

        if "llm_model" in _REQUIRED_BY_TYPE[art_type]:
            model = fm.get("llm_model")
            if model is not None and str(model).strip() == "":
                issues.append(f"{rel}: empty llm_model")

    return {
        "check": "frontmatter_schema",
        "severity": "warning",
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
    check_frontmatter_schema,
]

def run_all_checks() -> list[dict]:
    return [check() for check in ALL_CHECKS]

_SEVERITY_ORDER = ("error", "warning", "info")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Vault structural lint checker (no LLM).")
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")
    parser.add_argument(
        "--fix-backlinks",
        action="store_true",
        dest="fix_backlinks",
        help="Insert missing reciprocal backlinks (deterministic), then exit.",
    )
    args = parser.parse_args()

    if args.fix_backlinks:
        report = fix_missing_backlinks()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            fixed = report["fixed"]
            if fixed:
                print(f"Fixed {len(fixed)} missing backlink(s):")
                for line in fixed:
                    print(f"  + {line}")
            else:
                print("No missing backlinks to fix.")
        return 0

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

"""
index.py — Index generator for the Seed Vault wiki.

Scans wiki/**/*.md, groups articles by type, and writes wiki/_index.md.
Optionally rebuilds the qmd collection index.
Also detects and removes orphaned source summaries (whose raw/ file was deleted),
cascading to concept and topic articles that become empty as a result.

Usage:
    uv run python _vault/lib/index.py [--rebuild-qmd] [--dry-run] [--no-cleanup]
    python -m _vault.lib.index [--rebuild-qmd] [--dry-run] [--no-cleanup]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root detection
# ---------------------------------------------------------------------------

VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
INDEX_FILE = WIKI_DIR / "_index.md"
RAW_DIR = VAULT_ROOT / "raw"
SOURCES_DIR = WIKI_DIR / "sources"
CONCEPTS_DIR = WIKI_DIR / "concepts"
LOG_FILE = WIKI_DIR / "_log.md"

# Files to exclude from scanning
EXCLUDED_NAMES = {"_index.md", "_log.md", "_migration-log.md", "_catalog.md"}
EXCLUDED_SUFFIXES = {".base"}

# ---------------------------------------------------------------------------
# Frontmatter helpers — prefer shared module, fall back to regex
# ---------------------------------------------------------------------------

# Try to import the python-frontmatter library directly for write operations.
try:
    import frontmatter as _frontmatter_lib
    _HAS_FM_LIB = True
except ImportError:
    _HAS_FM_LIB = False

# Add vault root to path to allow relative imports of _vault.lib
sys.path.append(str(VAULT_ROOT))

try:
    from _vault.lib.frontmatter import (
        parse_file, 
        scan_directory,
        slugify,
        resolve_link
    )
except ImportError as e:
    print(f"ERROR: Could not import _vault.lib.frontmatter: {e}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_excluded(path: Path) -> bool:
    """Return True if this file should be skipped."""
    return path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES


def tags_str(tags) -> str:
    """Render a tags value (list or str) as a comma-separated string."""
    if not tags:
        return ""
    if isinstance(tags, list):
        return ", ".join(str(t) for t in tags)
    return str(tags)


def count_previous_entries(index_path: Path) -> int:
    """Count the number of article list lines in an existing _index.md."""
    if not index_path.exists():
        return 0
    text = index_path.read_text(encoding="utf-8")
    # Each article entry is a bullet line starting with "- [["
    return len(re.findall(r"^\s*- \[\[", text, re.MULTILINE))


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

# Display order and labels for each article type
TYPE_ORDER = [
    ("concept",        "Concepts"),
    ("source-summary", "Source Summaries"),
    ("visualization",  "Visualizations"),
    ("output",         "Outputs"),
]

PLACEHOLDER = {
    "concept":        "*(No concepts yet — ingest sources and use vault-compile)*",
    "source-summary": "*(No sources yet — drop files into `raw/` and use vault-ingest)*",
    "visualization":  "*(No visualizations yet — use vault-visualize)*",
    "output":         "*(No outputs yet)*",
}


def collect_articles(wiki_dir: Path) -> dict[str, list[dict]]:
    """Scan wiki_dir and return articles grouped by type, sorted by title."""
    if not wiki_dir.exists():
        return defaultdict(list)

    raw = scan_directory(Path(wiki_dir), fields=["title", "type", "tags", "status"])

    groups: dict[str, list[dict]] = defaultdict(list)

    for entry in raw:
        path = Path(entry["path"])
        if is_excluded(path):
            continue

        meta = entry["metadata"]
        article_type = str(meta.get("type", "")).strip().lower()

        # Check if type is one of our valid article types
        valid_types = {t[0] for t in TYPE_ORDER}
        if article_type not in valid_types:
            # Maybe the type is "source-summary" but was written as "source summary"
            normalized_type = article_type.replace(" ", "-")
            if normalized_type in valid_types:
                article_type = normalized_type
            else:
                # Guess from path if type is missing or invalid
                if "concepts/" in str(path):
                    article_type = "concept"
                elif "sources/" in str(path):
                    article_type = "source-summary"
                else:
                    continue

        title = str(meta.get("title", path.stem)).strip()
        tags = meta.get("tags", [])
        status = str(meta.get("status", "")).strip()

        groups[article_type].append({
            "title": title,
            "stem": path.stem,
            "tags": tags,
            "status": status,
        })

    # Sort alphabetically by title within each group
    for key in groups:
        groups[key].sort(key=lambda a: a["title"].lower())

    return groups


def build_index_text(groups: dict[str, list[dict]], today: str) -> str:
    """Render the full _index.md content."""
    total = sum(len(v) for v in groups.values())

    lines: list[str] = []

    # Frontmatter (required by CLAUDE.md; _index.base filters on type:index)
    lines += [
        "---",
        'title: "Wiki Index"',
        "type: index",
        f"updated: {today}",
        "---",
        "",
    ]

    # Heading
    lines += ["# Wiki Index", ""]

    # Sections
    for type_key, label in TYPE_ORDER:
        lines.append(f"## {label}")
        articles = groups.get(type_key, [])
        if articles:
            for art in articles:
                tag_part = f" — tags: {tags_str(art['tags'])}" if art["tags"] else ""
                # Use aliased link: [[stem|Title]]
                link = f"[[{art['stem']}|{art['title']}]]"
                lines.append(f"- {link}{tag_part}")
        else:
            lines.append(PLACEHOLDER.get(type_key, "*(none)*"))
        lines.append("")

    # Footer
    lines += [
        "---",
        f"*Last updated: {today} | Total articles: {total}*",
    ]

    return "\n".join(lines) + "\n"


def run_qmd_rebuild(wiki_dir: Path) -> None:
    """Run qmd collection add and qmd embed."""
    print("Rebuilding qmd collection index…")
    try:
        subprocess.run(
            ["qmd", "collection", "add", str(wiki_dir), "--name", "vault"],
            check=True,
        )
        subprocess.run(["qmd", "embed"], check=True)
        print("qmd rebuild complete.")
    except FileNotFoundError:
        print("WARNING: qmd not found — skipping qmd rebuild.", file=sys.stderr)
    except subprocess.CalledProcessError as exc:
        print(f"WARNING: qmd command failed (exit {exc.returncode}) — continuing.", file=sys.stderr)


def print_stats(groups: dict[str, list[dict]], previous_count: int) -> None:
    """Print counts by type and delta vs previous index."""
    total = sum(len(v) for v in groups.values())
    delta = total - previous_count

    print("\n--- Index Stats ---")
    for type_key, label in TYPE_ORDER:
        count = len(groups.get(type_key, []))
        if count:
            print(f"  {label}: {count}")
    print(f"  Total: {total}")

    if delta > 0:
        print(f"  Delta: +{delta} vs previous index")
    elif delta < 0:
        print(f"  Delta: {delta} vs previous index")
    else:
        print("  Delta: no change vs previous index")
    print()


# ---------------------------------------------------------------------------
# Orphaned-source cleanup
# ---------------------------------------------------------------------------

def find_orphaned_summaries() -> list[Path]:
    """Return wiki/sources/summary-*.md files whose raw/ counterpart no longer exists."""
    if not SOURCES_DIR.exists():
        return []
    
    # Get active raw stems (slugified for consistency)
    active_raw_slugs = {slugify(p.stem) for p in RAW_DIR.iterdir() if p.is_file()}
    orphans = []
    
    for summary in sorted(SOURCES_DIR.glob("summary-*.md")):
        # 1. Check normalized filename convention: summary-foo.md ↔ raw/foo.*
        summary_stem = summary.stem[len("summary-"):]
        if slugify(summary_stem) in active_raw_slugs:
            continue
            
        # 2. Robust check: parse frontmatter and look for [[raw/filename]] in sources
        fm = parse_file(summary)
        sources = fm.get("sources", []) or []
        found_active_source = False
        for src in sources:
            # Match [[raw/filename.ext]] or [[raw/filename]]
            m = re.search(r"\[\[raw/([^\]#|]+)", str(src))
            if m:
                src_stem = Path(m.group(1).strip()).stem
                if slugify(src_stem) in active_raw_slugs:
                    found_active_source = True
                    break
        
        if not found_active_source:
            orphans.append(summary)
            
    return orphans


def _get_title(path: Path) -> str:
    """Return the frontmatter title of an article, falling back to stem-based guess."""
    fm = parse_file(path)
    return str(fm.get("title", path.stem.replace("-", " ").title())).strip()


def _get_sources_list(path: Path) -> list[str]:
    """Return the titles listed in the sources: frontmatter field of path."""
    fm = parse_file(path)
    sources = fm.get("sources", []) or []
    result = []
    for src in sources:
        m = re.match(r"\[\[([^\]#|]+)", str(src))
        if m:
            result.append(m.group(1).strip())
    return result


def _get_body_wikilinks(path: Path) -> list[str]:
    """Return all [[wikilink]] targets from path's body (frontmatter excluded)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    fm_match = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    body = text[fm_match.end():] if fm_match else text
    return re.findall(r"\[\[([^\]#|]+)", body)


def _find_concepts_referencing_source(source_title: str) -> list[Path]:
    """Return concept files that list source_title in their sources: frontmatter."""
    if not CONCEPTS_DIR.exists():
        return []
    title_lower = source_title.lower()
    return [
        f for f in sorted(CONCEPTS_DIR.rglob("*.md"))
        if any(s.lower() == title_lower for s in _get_sources_list(f))
    ]


def _concept_title_set() -> dict[str, str]:
    """Return a mapping of lowercase title → canonical title for all concept files."""
    if not CONCEPTS_DIR.exists():
        return {}
    mapping: dict[str, str] = {}
    for f in CONCEPTS_DIR.rglob("*.md"):
        title = _get_title(f)
        mapping[title.lower()] = title
        mapping.setdefault(f.stem.replace("-", " ").lower(), title)
    return mapping


def _remove_source_from_frontmatter(path: Path, title: str) -> None:
    """Remove a wikilink entry matching title from the sources: frontmatter list."""
    escaped = re.escape(title)
    wikilink_pat = re.compile(r"\[\[" + escaped + r"(?:[#|][^\]]+)?\]\]")

    if _HAS_FM_LIB:
        try:
            with open(path, encoding="utf-8") as fh:
                post = _frontmatter_lib.load(fh)
            sources = list(post.get("sources", []) or [])
            post["sources"] = [s for s in sources if not wikilink_pat.search(str(s))]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(_frontmatter_lib.dumps(post))
            return
        except Exception:
            pass  # fall through to regex approach

    # Regex fallback: remove the entry from the inline or block YAML list.
    text = path.read_text(encoding="utf-8")
    # Block-style: "  - "[[Title]]"\n" or "  - '[[Title]]'\n"
    text = re.sub(
        r"^[ \t]*-[ \t]+['\"]?\[\[" + escaped + r"(?:[#|][^\]]+)?\]\]['\"]?[ \t]*\n",
        "",
        text,
        flags=re.MULTILINE,
    )
    # Inline-style inside [...]: remove the entry plus surrounding comma/space
    text = re.sub(
        r",\s*['\"]?\[\[" + escaped + r"(?:[#|][^\]]+)?\]\]['\"]?",
        "",
        text,
    )
    text = re.sub(
        r"['\"]?\[\[" + escaped + r"(?:[#|][^\]]+)?\]\]['\"]?\s*,",
        "",
        text,
    )
    # Lone entry: [[Title]] with no comma neighbours
    text = re.sub(
        r"['\"]?\[\[" + escaped + r"(?:[#|][^\]]+)?\]\]['\"]?",
        "",
        text,
    )
    path.write_text(text, encoding="utf-8")


def _remove_wikilink_from_body(path: Path, title: str) -> None:
    """
    Remove [[title]] references from path's body (below frontmatter).

    - Bullet list items whose only content is the wikilink are deleted entirely.
    - Inline wikilinks are replaced with their display text (alias if present,
      otherwise the title itself).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return

    # Split into frontmatter block + body
    fm_match = re.match(r"^(---\s*\n.*?\n---\s*\n)", text, re.DOTALL)
    if fm_match:
        header = fm_match.group(1)
        body = text[fm_match.end():]
    else:
        header = ""
        body = text

    escaped = re.escape(title)

    # 1. Remove bullet list items that consist solely of this wikilink
    #    Handles: "- [[Title]]\n", "  * [[Title|alias]]\n", etc.
    body = re.sub(
        r"^[ \t]*[-*][ \t]+\[\[" + escaped + r"(?:[#|][^\]]+)?\]\][ \t]*\n",
        "",
        body,
        flags=re.MULTILINE,
    )

    # 2. Replace remaining inline wikilinks with display text
    #    [[Title]] → Title
    #    [[Title|alias]] → alias
    #    [[Title#section]] → Title
    body = re.sub(
        r"\[\[" + escaped + r"(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda m: m.group(1) if m.group(1) else title,
        body,
    )

    path.write_text(header + body, encoding="utf-8")


def _append_cleanup_log(message: str) -> None:
    """Append a timestamped cleanup entry to wiki/_log.md."""
    if not LOG_FILE.parent.exists():
        return
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"[{ts} cleanup] {message}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def cleanup_orphaned_sources(dry_run: bool = False) -> dict:
    """
    Detect and remove wiki artifacts whose raw/ source file was deleted.

    Algorithm:
    1. Find wiki/sources/summary-X.md files with no raw/X.* counterpart.
    2. For each orphaned summary find referencing concept articles:
       - If the concept's sources: list is entirely orphaned → mark for deletion.
       - Otherwise → mark the orphaned source for removal from the concept.
    3. Apply modifications (remove references) then deletions.
    4. Log every action to wiki/_log.md.

    Args:
        dry_run: If True, return a preview dict without modifying any files.

    Returns:
        dict with keys:
          orphaned_summaries  – list of summary paths detected as orphaned
          deleted             – list of paths deleted  (empty when dry_run)
          modified            – list of paths modified (empty when dry_run)
          would_delete        – list of paths that would be deleted (dry_run only)
          would_modify        – list of paths that would be modified (dry_run only)
    """
    orphaned_summaries = find_orphaned_summaries()
    if not orphaned_summaries:
        return {
            "orphaned_summaries": [],
            "deleted": [],
            "modified": [],
        }

    orphan_titles: set[str] = {_get_title(p) for p in orphaned_summaries}

    # --- Pass 1: decide which concepts to delete vs modify ---
    concepts_to_delete: set[Path] = set()
    # concept path → list of source titles to strip
    concepts_to_modify: dict[Path, list[str]] = defaultdict(list)

    for summary_path in orphaned_summaries:
        summary_title = _get_title(summary_path)
        for concept_path in _find_concepts_referencing_source(summary_title):
            all_sources = _get_sources_list(concept_path)
            remaining = [s for s in all_sources if s not in orphan_titles]
            if not remaining:
                concepts_to_delete.add(concept_path)
            else:
                concepts_to_modify[concept_path].append(summary_title)

    # --- Dry-run: return preview without touching files ---
    if dry_run:
        return {
            "orphaned_summaries": [str(p.relative_to(VAULT_ROOT)) for p in orphaned_summaries],
            "deleted": [],
            "modified": [],
            "would_delete": sorted(
                str(p.relative_to(VAULT_ROOT))
                for p in list(orphaned_summaries) + list(concepts_to_delete)
            ),
            "would_modify": sorted(
                str(p.relative_to(VAULT_ROOT))
                for p in concepts_to_modify.keys()
            ),
        }

    deleted: list[str] = []
    modified: list[str] = []

    # --- Modify concepts (strip orphaned source references) ---
    for concept_path, source_titles in concepts_to_modify.items():
        if concept_path in concepts_to_delete:
            continue
        for title in source_titles:
            _remove_source_from_frontmatter(concept_path, title)
            _remove_wikilink_from_body(concept_path, title)
        rel = str(concept_path.relative_to(VAULT_ROOT))
        modified.append(rel)
        _append_cleanup_log(f"Removed source ref(s) {source_titles} from {rel}")

    # --- Delete concepts ---
    for concept_path in concepts_to_delete:
        rel = str(concept_path.relative_to(VAULT_ROOT))
        concept_path.unlink()
        deleted.append(rel)
        _append_cleanup_log(f"Deleted concept {rel} (only source was orphaned)")

    # --- Delete orphaned source summaries ---
    for summary_path in orphaned_summaries:
        rel = str(summary_path.relative_to(VAULT_ROOT))
        summary_path.unlink()
        deleted.append(rel)
        _append_cleanup_log(f"Deleted orphaned summary {rel} (raw file removed)")

    return {
        "orphaned_summaries": [str(p.relative_to(VAULT_ROOT)) for p in orphaned_summaries],
        "deleted": deleted,
        "modified": modified,
    }


def print_cleanup_report(report: dict, dry_run: bool = False) -> None:
    """Print a human-readable cleanup report to stdout."""
    orphans = report.get("orphaned_summaries", [])
    if not orphans:
        print("Cleanup: no orphaned source summaries detected.")
        return

    print(f"\n--- Orphaned Source Cleanup {'(dry run) ' if dry_run else ''}---")
    print(f"  Orphaned summaries detected: {len(orphans)}")
    for p in orphans:
        print(f"    - {p}")

    if dry_run:
        would_delete = report.get("would_delete", [])
        would_modify = report.get("would_modify", [])
        if would_delete:
            print(f"  Would delete ({len(would_delete)}):")
            for p in would_delete:
                print(f"    - {p}")
        if would_modify:
            print(f"  Would modify ({len(would_modify)}):")
            for p in would_modify:
                print(f"    - {p}")
    else:
        deleted = report.get("deleted", [])
        modified = report.get("modified", [])
        if deleted:
            print(f"  Deleted ({len(deleted)}):")
            for p in deleted:
                print(f"    - {p}")
        if modified:
            print(f"  Modified ({len(modified)}):")
            for p in modified:
                print(f"    - {p}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate wiki/_index.md for the Seed Vault."
    )
    parser.add_argument(
        "--rebuild-qmd",
        action="store_true",
        help="Also run 'qmd collection add wiki/ --name vault && qmd embed' after writing the index.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview orphaned-source cleanup without modifying any files.",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip orphaned-source detection and cleanup.",
    )
    args = parser.parse_args()

    today = date.today().isoformat()

    # --- Orphaned-source cleanup (runs before index rebuild) ---
    if not args.no_cleanup:
        cleanup_report = cleanup_orphaned_sources(dry_run=args.dry_run)
        print_cleanup_report(cleanup_report, dry_run=args.dry_run)
        if args.dry_run:
            # In dry-run mode stop here; don't write the index.
            return

    # Count entries in the existing index before overwriting
    previous_count = count_previous_entries(INDEX_FILE)

    # Collect and group articles
    if not WIKI_DIR.exists():
        print(f"WARNING: wiki directory not found at {WIKI_DIR} — writing empty index.", file=sys.stderr)
        groups: dict[str, list[dict]] = {}
    else:
        groups = collect_articles(WIKI_DIR)

    # Generate index text
    index_text = build_index_text(groups, today)

    # Write _index.md
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(index_text, encoding="utf-8")
    print(f"Written: {INDEX_FILE}")

    # Stats
    print_stats(groups, previous_count)

    # Optional qmd rebuild
    if args.rebuild_qmd:
        run_qmd_rebuild(WIKI_DIR)


if __name__ == "__main__":
    main()

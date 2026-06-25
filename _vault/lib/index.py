"""
index.py — Index generator for the Seed Vault wiki.

Scans wiki/**/*.md, groups articles by type, and writes wiki/_index.md.
Optionally rebuilds the qmd collection index.
Also detects and removes orphaned source summaries (whose raw/ file was deleted),
cascading to concept articles that become empty as a result.

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
from functools import lru_cache
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
# Frontmatter helpers
# ---------------------------------------------------------------------------

import frontmatter as _frontmatter_lib  # noqa: E402

# Add vault root to path so we can import _vault.lib.vault_frontmatter
sys.path.append(str(VAULT_ROOT))

from _vault.lib.vault_frontmatter import (  # noqa: E402
    parse_file,
    scan_directory,
    slugify,
)


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
    """Register the wiki dir as the 'vault' qmd collection and (re)embed.

    Idempotent: ``qmd collection add`` errors out if the ``vault`` collection
    already exists (e.g. on every bootstrap.sh update after the first), so we
    treat an "already exists" failure as benign and proceed straight to
    ``qmd embed``, which refreshes embeddings for the existing collection.
    """
    print("Rebuilding qmd collection index…")
    try:
        add = subprocess.run(
            ["qmd", "collection", "add", str(wiki_dir), "--name", "vault"],
            capture_output=True,
            text=True,
        )
        if add.returncode != 0:
            combined = (add.stdout + add.stderr).lower()
            if "already exists" in combined:
                print("qmd collection 'vault' already exists — refreshing embeddings.")
            else:
                if add.stdout:
                    sys.stderr.write(add.stdout)
                if add.stderr:
                    sys.stderr.write(add.stderr)
                print(
                    f"WARNING: qmd collection add failed (exit {add.returncode}) — continuing.",
                    file=sys.stderr,
                )
                return
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

def _raw_link_slugs(source_value) -> list[str]:
    """Slugified raw/* stems found inside a frontmatter sources entry."""
    m = re.search(r"\[\[raw/([^\]#|]+)", str(source_value))
    return [slugify(Path(m.group(1).strip()).stem)] if m else []


def find_orphaned_summaries() -> list[Path]:
    """Return wiki/sources/summary-*.md files whose raw/ counterpart no longer exists."""
    if not SOURCES_DIR.exists():
        return []

    active_raw_slugs = (
        {slugify(p.stem) for p in RAW_DIR.iterdir() if p.is_file()}
        if RAW_DIR.exists()
        else set()
    )
    orphans = []

    for summary in sorted(SOURCES_DIR.glob("summary-*.md")):
        # 1. Check normalized filename convention: summary-foo.md ↔ raw/foo.*
        summary_stem = summary.stem[len("summary-"):]
        if slugify(summary_stem) in active_raw_slugs:
            continue

        # 2. Robust check: parse frontmatter and look for [[raw/filename]] in sources
        sources = _cached_parse_file(summary).get("sources", []) or []
        has_active = any(
            slug in active_raw_slugs
            for src in sources
            for slug in _raw_link_slugs(src)
        )
        if not has_active:
            orphans.append(summary)

    return orphans


@lru_cache(maxsize=None)
def _cached_parse_file(path: Path) -> dict:
    return parse_file(path)


def _get_title(path: Path) -> str:
    """Return the frontmatter title of an article, falling back to stem-based guess."""
    fm = _cached_parse_file(path)
    return str(fm.get("title", path.stem.replace("-", " ").title())).strip()


def _get_sources_list(path: Path) -> list[str]:
    """Return the titles listed in the sources: frontmatter field of path."""
    fm = _cached_parse_file(path)
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

    with open(path, encoding="utf-8") as fh:
        post = _frontmatter_lib.load(fh)
    sources = list(post.get("sources", []) or [])
    post["sources"] = [s for s in sources if not wikilink_pat.search(str(s))]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(_frontmatter_lib.dumps(post))


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


def _print_path_section(label: str, paths: list[str]) -> None:
    if not paths:
        return
    print(f"  {label} ({len(paths)}):")
    for p in paths:
        print(f"    - {p}")


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
        _print_path_section("Would delete", report.get("would_delete", []))
        _print_path_section("Would modify", report.get("would_modify", []))
    else:
        _print_path_section("Deleted", report.get("deleted", []))
        _print_path_section("Modified", report.get("modified", []))
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

"""
digest.py — Vault statistics generator for the Seed Vault wiki.

Fully deterministic, no LLM required.

Usage:
    uv run python _vault/lib/digest.py [--json | --markdown]

Default output is --markdown.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Vault root: this file lives at <vault>/_vault/lib/digest.py
# ---------------------------------------------------------------------------
VAULT_ROOT = Path(__file__).resolve().parent.parent.parent
WIKI_DIR = VAULT_ROOT / "wiki"
RAW_DIR = VAULT_ROOT / "raw"

# Files to exclude from article counts
_EXCLUDED_NAMES = {"_index.md", "_log.md", "_migration-log.md"}
_EXCLUDED_SUFFIXES = {".base"}

# Regex for [[wikilinks]] — captures the target (before | or #)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#\n]+?)(?:[|#][^\]]*?)?\]\]")

# ---------------------------------------------------------------------------
# Frontmatter import with regex fallback
# ---------------------------------------------------------------------------
try:
    from _vault.lib.frontmatter import parse_file, scan_directory  # type: ignore

    _USE_LIB = True
except ImportError:
    _USE_LIB = False

    _FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    _FIELD_RE = re.compile(r"^(\w[\w\-]*):\s*(.*)$", re.MULTILINE)
    _LIST_ITEM_RE = re.compile(r"^\s*-\s+(.+)$", re.MULTILINE)

    def _parse_yaml_value(raw: str) -> list[str] | str:
        raw = raw.strip()
        # Inline list: [a, b, c]
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1]
            return [s.strip().strip('"').strip("'") for s in inner.split(",") if s.strip()]
        # Quoted scalar
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            return raw[1:-1]
        return raw

    def parse_file(filepath: Path) -> dict:  # type: ignore[misc]
        try:
            text = Path(filepath).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return {}
        m = _FM_RE.match(text)
        if not m:
            return {}
        block = m.group(1)
        result: dict = {}
        for key, raw in _FIELD_RE.findall(block):
            result[key] = _parse_yaml_value(raw)
        return result

    def scan_directory(dirpath: Path, fields=None) -> list[dict]:  # type: ignore[misc]
        results = []
        for md_file in sorted(Path(dirpath).rglob("*.md")):
            metadata = parse_file(md_file)
            if fields is not None:
                metadata = {k: metadata[k] for k in fields if k in metadata}
            results.append({"path": str(md_file), "metadata": metadata})
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_excluded(path: Path) -> bool:
    return path.name in _EXCLUDED_NAMES or path.suffix in _EXCLUDED_SUFFIXES


def _collect_wiki_files() -> list[Path]:
    if not WIKI_DIR.exists():
        return []
    return [p for p in WIKI_DIR.rglob("*.md") if not _is_excluded(p)]


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, (date, datetime)):
        return value.date() if isinstance(value, datetime) else value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _normalize_title(title_or_path) -> str:
    """Return a display title, preferring the frontmatter title field."""
    if isinstance(title_or_path, dict):
        fm = title_or_path.get("metadata", {})
        title = fm.get("title", "")
        if title:
            return str(title)
        path = Path(title_or_path.get("path", ""))
    else:
        path = Path(title_or_path)
    # Derive from filename: kebab-case → Title Case
    stem = path.stem
    return stem.replace("-", " ").replace("_", " ").title()


def _slug(title: str) -> str:
    """Lowercase stripped title used as a lookup key."""
    return title.strip().lower()


# ---------------------------------------------------------------------------
# Core statistics builder
# ---------------------------------------------------------------------------

def build_stats() -> dict:
    files = _collect_wiki_files()

    # --- Article metadata ---------------------------------------------------
    articles: list[dict] = []
    for p in files:
        fm = parse_file(p)
        title = fm.get("title") or p.stem.replace("-", " ").replace("_", " ").title()
        articles.append(
            {
                "path": p,
                "title": str(title),
                "type": str(fm.get("type", "unknown")).strip(),
                "status": str(fm.get("status", "unknown")).strip(),
                "tags": _coerce_list(fm.get("tags")),
                "updated": _parse_date(fm.get("updated")),
                "created": _parse_date(fm.get("created")),
            }
        )

    total = len(articles)

    # --- Type counts --------------------------------------------------------
    type_counts: Counter = Counter(a["type"] for a in articles)

    # --- Status counts ------------------------------------------------------
    status_counts: Counter = Counter(a["status"] for a in articles)

    # --- Recently updated (top 10) -----------------------------------------
    recently_updated = sorted(
        [a for a in articles if a["updated"]],
        key=lambda a: a["updated"],
        reverse=True,
    )[:10]

    # --- Tag frequency ------------------------------------------------------
    tag_counter: Counter = Counter()
    for a in articles:
        for tag in a["tags"]:
            tag_counter[tag.strip()] += 1

    # --- Wikilink analysis --------------------------------------------------
    # incoming_links[slug] = count of [[Title]] references across all files
    incoming: Counter = Counter()
    # Track which slugs actually exist as article titles
    known_slugs: set[str] = {_slug(a["title"]) for a in articles}
    # Also index by filename stem
    known_slugs.update(_slug(p.stem.replace("-", " ").replace("_", " ").title()) for p in files)

    # Per-file outgoing wikilinks (for unresolved detection)
    all_link_targets: list[str] = []

    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        targets = _WIKILINK_RE.findall(text)
        for t in targets:
            t_clean = t.strip()
            incoming[_slug(t_clean)] += 1
            all_link_targets.append(t_clean)

    # Map slug → display title for known articles
    slug_to_title: dict[str, str] = {}
    for a in articles:
        slug_to_title[_slug(a["title"])] = a["title"]
    for p in files:
        stem_title = p.stem.replace("-", " ").replace("_", " ").title()
        s = _slug(stem_title)
        if s not in slug_to_title:
            slug_to_title[s] = stem_title

    # Hub nodes: top-5 by incoming link count (must be known articles)
    hub_candidates = [
        (slug_to_title.get(slug, slug), count)
        for slug, count in incoming.most_common()
        if slug in known_slugs and count > 0
    ][:5]

    # Orphans: known articles with 0 incoming links
    orphans = [
        a["title"]
        for a in articles
        if incoming.get(_slug(a["title"]), 0) == 0
    ]

    # Unresolved links: referenced titles not matching any known article
    unresolved: set[str] = set()
    for t in all_link_targets:
        if _slug(t) not in known_slugs:
            unresolved.add(t)

    # --- Knowledge gaps -----------------------------------------------------
    # Raw files without a corresponding source summary
    raw_files: list[Path] = []
    if RAW_DIR.exists():
        raw_files = list(RAW_DIR.glob("*.md")) + list(RAW_DIR.glob("*.txt"))

    source_stems = {
        p.stem.lower()
        for p in files
        if "sources" in str(p)
    }

    raw_without_summary = 0
    for rf in raw_files:
        # Heuristic: check if any source summary filename contains the raw stem
        raw_stem = rf.stem.lower()
        if not any(raw_stem in s for s in source_stems):
            raw_without_summary += 1

    singleton_tags = sum(1 for c in tag_counter.values() if c == 1)

    # Concepts without a topic hub link
    topic_hub_slugs: set[str] = set()
    for p in files:
        if "topics" in str(p):
            topic_hub_slugs.add(_slug(p.stem.replace("-", " ").replace("_", " ").title()))
            fm = parse_file(p)
            t = fm.get("title")
            if t:
                topic_hub_slugs.add(_slug(str(t)))

    concepts_without_hub = 0
    for p in files:
        if "concepts" not in str(p):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        linked_topics = {_slug(t) for t in _WIKILINK_RE.findall(text)}
        if not linked_topics.intersection(topic_hub_slugs):
            concepts_without_hub += 1

    return {
        "generated": date.today().isoformat(),
        "total": total,
        "type_counts": dict(type_counts),
        "status_counts": dict(status_counts),
        "recently_updated": [
            {
                "title": a["title"],
                "updated": a["updated"].isoformat() if a["updated"] else None,
                "type": a["type"],
            }
            for a in recently_updated
        ],
        "hub_nodes": [{"title": t, "incoming": c} for t, c in hub_candidates],
        "orphans": orphans,
        "unresolved_links": sorted(unresolved),
        "tag_distribution": tag_counter.most_common(),
        "gaps": {
            "raw_without_summary": raw_without_summary,
            "singleton_tags": singleton_tags,
            "concepts_without_hub": concepts_without_hub,
        },
    }


def _coerce_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def format_markdown(stats: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Vault Digest — {stats['generated']}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    tc = stats["type_counts"]
    sc = stats["status_counts"]
    lines.append(f"- Total articles: {stats['total']}")
    lines.append(
        f"- Concepts: {tc.get('concept', 0)} | "
        f"Sources: {tc.get('source-summary', 0)} | "
        f"Topics: {tc.get('topic', 0)} | "
        f"Viz: {tc.get('visualization', 0)} | "
        f"Output: {tc.get('output', 0)}"
    )
    lines.append(
        f"- Status: {sc.get('draft', 0)} draft, "
        f"{sc.get('reviewed', 0)} reviewed, "
        f"{sc.get('verified', 0)} verified"
    )
    lines.append("")

    # Recently updated
    lines.append("## Recently Updated")
    if stats["recently_updated"]:
        for i, a in enumerate(stats["recently_updated"], 1):
            lines.append(f"{i}. [[{a['title']}]] — {a['updated']} ({a['type']})")
    else:
        lines.append("_No articles with updated dates found._")
    lines.append("")

    # Hub nodes
    lines.append("## Hub Nodes (most linked)")
    if stats["hub_nodes"]:
        for i, node in enumerate(stats["hub_nodes"], 1):
            lines.append(f"{i}. [[{node['title']}]] — {node['incoming']} incoming links")
    else:
        lines.append("_No hub nodes detected._")
    lines.append("")

    # Orphans
    lines.append("## Orphan Pages (no incoming links)")
    if stats["orphans"]:
        for title in sorted(stats["orphans"]):
            lines.append(f"- [[{title}]]")
    else:
        lines.append("_No orphan pages._")
    lines.append("")

    # Tag distribution
    lines.append("## Tag Distribution")
    if stats["tag_distribution"]:
        for tag, count in stats["tag_distribution"]:
            lines.append(f"- {tag}: {count} article{'s' if count != 1 else ''}")
    else:
        lines.append("_No tags found._")
    lines.append("")

    # Knowledge gaps
    lines.append("## Knowledge Gaps")
    gaps = stats["gaps"]
    lines.append(f"- {gaps['raw_without_summary']} raw files without source summaries")
    lines.append(f"- {gaps['singleton_tags']} singleton tags")
    lines.append(f"- {gaps['concepts_without_hub']} concepts without topic hub")
    lines.append("")

    return "\n".join(lines)


def format_json(stats: dict) -> str:
    return json.dumps(stats, indent=2, default=str)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a statistics digest of the Seed Vault wiki."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--json", action="store_true", dest="as_json", help="Output as JSON"
    )
    group.add_argument(
        "--markdown",
        action="store_true",
        dest="as_markdown",
        help="Output as Markdown (default)",
    )
    args = parser.parse_args()

    stats = build_stats()

    if args.as_json:
        print(format_json(stats))
    else:
        print(format_markdown(stats))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Seed Vault — Incremental Wiki Migration Runner
Applies structural migrations to wiki articles when the framework version changes.

Normal update flow (driven by bootstrap.sh update):
  1. bootstrap.sh syncs framework paths → _vault/VERSION is now the new version
  2. bash _vault/install.sh
  3. python3 _vault/migrate.py   ← you are here

Version sources:
  - Framework version (target): _vault/VERSION   (synced by bootstrap.sh, tracked in git)
  - Vault version (current):    .vault_version   (vault root; gitignored, local-only)

Usage:
  python3 _vault/migrate.py                        # Apply pending migrations
  python3 _vault/migrate.py --dry-run              # Show what would change, no writes
  python3 _vault/migrate.py --from-version 0.0.0  # Override detected vault version
  python3 _vault/migrate.py --path wiki/topics/   # Scope to a subdirectory
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path


# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
VAULT_ROOT = SCRIPT_DIR.parent
VERSION_FILE = SCRIPT_DIR / "VERSION"
MIGRATIONS_DIR = SCRIPT_DIR / "migrations"
VAULT_VERSION_FILE = VAULT_ROOT / ".vault_version"                  # install-state, vault root
LEGACY_VAULT_VERSION_FILE = VAULT_ROOT / "wiki" / ".vault_version"  # pre-3.x location
MIGRATION_LOG = VAULT_ROOT / "wiki" / "_migration-log.md"


# ── Semver helpers ────────────────────────────────────────────────────────────

def parse_semver(v: str) -> tuple[int, ...]:
    """Parse 'X.Y.Z' into a comparable tuple of ints. Treats '0.0.0' as baseline."""
    v = v.strip().strip('"\'')
    parts = v.split(".")
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        raise SystemExit(f"Invalid version string: {v!r}")


def semver_gt(a: str, b: str) -> bool:
    """Return True if version a > version b."""
    return parse_semver(a) > parse_semver(b)


def semver_gte(a: str, b: str) -> bool:
    """Return True if version a >= version b."""
    return parse_semver(a) >= parse_semver(b)


# ── Frontmatter parsing ───────────────────────────────────────────────────────

def split_frontmatter(content: str) -> tuple[list[str] | None, str]:
    """
    Split file content into (frontmatter_lines, body).
    Returns (None, content) if no frontmatter found.
    frontmatter_lines does NOT include the opening/closing --- delimiters.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return None, content

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break

    if end is None:
        return None, content

    frontmatter_lines = lines[1:end]
    body = "\n".join(lines[end + 1:])
    return frontmatter_lines, body


def get_field(frontmatter_lines: list[str], field: str) -> str | None:
    """Return the value of a frontmatter field, or None if absent."""
    pattern = re.compile(r'^' + re.escape(field) + r'\s*:\s*(.*)', re.IGNORECASE)
    for line in frontmatter_lines:
        m = pattern.match(line)
        if m:
            return m.group(1).strip().strip('"\'')
    return None


def rebuild_content(frontmatter_lines: list, body: str) -> str:
    """Reassemble file content from frontmatter lines and body."""
    fm = "\n".join(["---"] + frontmatter_lines + ["---"])
    if body.startswith("\n"):
        return fm + body
    return fm + "\n" + body


# ── Operations ────────────────────────────────────────────────────────────────

def op_add_field(fm_lines: list, op: dict, to_version: str) -> tuple:
    """
    Add a new field to frontmatter if not already present.
    Returns (modified_lines, changed: bool).
    """
    field = op["field"]
    value = op.get("value", to_version)
    skip_if_present = op.get("skip_if_present", True)

    if skip_if_present and get_field(fm_lines, field) is not None:
        return fm_lines, False

    new_line = f'{field}: "{value}"'
    return fm_lines + [new_line], True


def op_set_field(fm_lines: list, op: dict, to_version: str) -> tuple:
    """
    Set a field to a specific value, adding it if absent.
    Returns (modified_lines, changed: bool).
    """
    field = op["field"]
    value = op.get("value", to_version)
    pattern = re.compile(r'^' + re.escape(field) + r'\s*:.*', re.IGNORECASE)
    new_line = f'{field}: "{value}"'

    new_lines = []
    found = False
    changed = False
    for line in fm_lines:
        if pattern.match(line):
            found = True
            if line != new_line:
                new_lines.append(new_line)
                changed = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if not found:
        new_lines.append(new_line)
        changed = True

    return new_lines, changed


def op_rename_field_value(fm_lines: list, op: dict, to_version: str) -> tuple:
    """
    Rename a specific value of a field (e.g. type: source-summary → type: source).
    Returns (modified_lines, changed: bool).
    """
    field = op["field"]
    old_value = op["old_value"]
    new_value = op["new_value"]
    pattern = re.compile(
        r'^(' + re.escape(field) + r'\s*:\s*["\']?)' + re.escape(old_value) + r'(["\']?\s*)$',
        re.IGNORECASE
    )

    new_lines = []
    changed = False
    for line in fm_lines:
        m = pattern.match(line)
        if m:
            new_lines.append(f'{field}: "{new_value}"')
            changed = True
        else:
            new_lines.append(line)

    return new_lines, changed


def op_delete_field(fm_lines: list, op: dict, to_version: str) -> tuple:
    """
    Remove a field from frontmatter entirely.
    Returns (modified_lines, changed: bool).
    """
    field = op["field"]
    pattern = re.compile(r'^' + re.escape(field) + r'\s*:.*', re.IGNORECASE)
    new_lines = [line for line in fm_lines if not pattern.match(line)]
    changed = len(new_lines) != len(fm_lines)
    return new_lines, changed


OPERATIONS = {
    "add_field": op_add_field,
    "set_field": op_set_field,
    "rename_field_value": op_rename_field_value,
    "delete_field": op_delete_field,
}


# ── Article type filtering ────────────────────────────────────────────────────

def get_article_type(fm_lines: list) -> str:
    return get_field(fm_lines, "type") or ""


def article_matches_affects(fm_lines: list, affects) -> bool:
    if affects == "all":
        return True
    if isinstance(affects, list):
        t = get_article_type(fm_lines)
        return t in affects
    return False


# ── File discovery ────────────────────────────────────────────────────────────

def find_wiki_files(scope_path: str | None = None) -> list[Path]:
    """
    Return all wiki .md files eligible for migration.
    Excludes system files: _index.md, _catalog.md, _migration-log.md, *.base
    """
    base = VAULT_ROOT / scope_path if scope_path else VAULT_ROOT / "wiki"
    exclude = {"_index.md", "_catalog.md", "_migration-log.md", "_log.md"}

    files = []
    for p in sorted(Path(base).rglob("*.md")):
        if p.name in exclude or p.suffix == ".base":
            continue
        files.append(p)
    return files


# ── Vault version detection ───────────────────────────────────────────────────

def read_vault_version() -> str:
    """
    Read the vault's current framework version from .vault_version (vault root).
    Back-compat: falls back to the legacy wiki/.vault_version if the root file is
    absent. This file is gitignored and local-only, so it never conflicts on merge.
    Falls back to 0.0.0 if neither exists (new or pre-versioned vault).
    """
    src = VAULT_VERSION_FILE if VAULT_VERSION_FILE.exists() else LEGACY_VAULT_VERSION_FILE
    if not src.exists():
        return "0.0.0"
    v = src.read_text(encoding="utf-8").strip().strip('"\'')
    return v if v else "0.0.0"


def write_vault_version(version: str, dry_run: bool):
    """Write the vault's framework version to .vault_version (vault root)."""
    if dry_run:
        print(f"  [dry-run] .vault_version → {version}")
        return
    VAULT_VERSION_FILE.write_text(version + "\n", encoding="utf-8")
    print(f"  .vault_version → {version}")


# ── Migration log ─────────────────────────────────────────────────────────────

def append_migration_log(from_v: str, to_v: str, affected: int, dry_run: bool):
    today = date.today().isoformat()
    row = f"| {today} | {from_v} | {to_v} | {affected} articles updated | vault-migrate |"

    if dry_run:
        return

    if MIGRATION_LOG.exists():
        existing = MIGRATION_LOG.read_text(encoding="utf-8")
        MIGRATION_LOG.write_text(existing.rstrip() + "\n" + row + "\n", encoding="utf-8")
    else:
        header = (
            "---\n"
            'title: "Migration Log"\n'
            "type: migration-log\n"
            f"updated: {today}\n"
            "---\n\n"
            "# Migration Log\n\n"
            "| Date | From | To | Articles Affected | Applied By |\n"
            "|------|------|----|-------------------|------------|\n"
        )
        MIGRATION_LOG.write_text(header + row + "\n", encoding="utf-8")


# ── Core migration logic ──────────────────────────────────────────────────────

def apply_migration(migration: dict, wiki_files: list, dry_run: bool) -> dict:
    """Apply one migration to all eligible files. Returns stats."""
    to_version = migration["to"]
    operations = migration.get("operations", [])
    today = date.today().isoformat()

    stats = {"changed": 0, "skipped": 0, "errors": 0}

    for filepath in wiki_files:
        try:
            content = filepath.read_text(encoding="utf-8")
            fm_lines, body = split_frontmatter(content)

            if fm_lines is None:
                stats["skipped"] += 1
                continue

            any_changed = False
            for op in operations:
                affects = op.get("affects", "all")
                if not article_matches_affects(fm_lines, affects):
                    continue

                op_name = op["op"]
                fn = OPERATIONS.get(op_name)
                if fn is None:
                    print(f"  [warn] Unknown operation: {op_name!r} — skipping")
                    continue

                fm_lines, changed = fn(fm_lines, op, to_version)
                if changed:
                    any_changed = True

            if any_changed:
                # Update the 'updated:' date
                fm_lines, _ = op_set_field(fm_lines, {"field": "updated", "value": today}, to_version)
                new_content = rebuild_content(fm_lines, body)
                rel = filepath.relative_to(VAULT_ROOT)
                if dry_run:
                    print(f"  [dry-run] {rel}")
                else:
                    filepath.write_text(new_content, encoding="utf-8")
                    print(f"  updated: {rel}")
                stats["changed"] += 1
            else:
                stats["skipped"] += 1

        except Exception as e:
            print(f"  [error] {filepath}: {e}")
            stats["errors"] += 1

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Parse args
    dry_run = "--dry-run" in sys.argv
    complete = "--complete" in sys.argv
    scope_path = None
    from_version_override = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--path" and i + 1 < len(args):
            scope_path = args[i + 1]
            i += 2
        elif args[i] == "--from-version" and i + 1 < len(args):
            from_version_override = args[i + 1]
            i += 2
        else:
            i += 1

    if dry_run:
        print("[ DRY RUN — no files will be written ]\n")

    # Read versions
    if not VERSION_FILE.exists():
        raise SystemExit(f"Error: {VERSION_FILE} not found. Is this a Seed Vault repository?")

    framework_version = VERSION_FILE.read_text(encoding="utf-8").strip()

    # --complete finalizes a held-back migration: the vault-migrate skill calls
    # this AFTER performing the manual requires_llm step(s), to advance
    # .vault_version to the framework version. It is the only thing that should
    # advance the version past a requires_llm migration — migrate.py itself holds
    # the version back (see the apply loop below) so a half-finished update can't
    # masquerade as complete.
    if complete:
        write_vault_version(framework_version, dry_run)
        print(f"Vault version finalized → {framework_version}")
        return

    vault_version = from_version_override or read_vault_version()

    print(f"Framework version : {framework_version}  (from _vault/VERSION — synced by bootstrap.sh update)")
    print(f"Vault version     : {vault_version}  (from .vault_version — reflects existing articles)")

    # Compare
    if parse_semver(vault_version) == parse_semver(framework_version):
        print("\nVault is current. No migrations needed.")
        return

    if semver_gt(vault_version, framework_version):
        print(f"\n[warn] Vault version ({vault_version}) is ahead of framework ({framework_version}). Nothing to do.")
        return

    # Load migrations
    migration_files = sorted(MIGRATIONS_DIR.glob("*.json"))
    if not migration_files:
        print(f"\nNo migration specs found in {MIGRATIONS_DIR}")
        # Framework moved forward but ships no migrations — content needs nothing,
        # so record that the vault is current. (migrate.py owns .vault_version.)
        write_vault_version(framework_version, dry_run)
        return

    pending = []
    for mf in migration_files:
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[warn] Could not parse {mf.name}: {e}")
            continue
        # Include if 'from' >= vault_version and 'to' <= framework_version
        if semver_gte(m["from"], vault_version) and not semver_gt(m["to"], framework_version):
            pending.append(m)

    if not pending:
        print(f"\nNo applicable migrations found between {vault_version} and {framework_version}.")
        # Nothing bridges the gap, so there is no content work to do — mark the
        # vault current at the framework version.
        write_vault_version(framework_version, dry_run)
        return

    # Report plan
    print(f"\nMigrations to apply: {len(pending)}")
    for m in pending:
        llm_flag = "  [requires LLM step]" if m.get("requires_llm") else ""
        print(f"  {m['from']} → {m['to']}  — {m['description']}{llm_flag}")

    # Discover files once
    wiki_files = find_wiki_files(scope_path)
    print(f"\nWiki articles in scope: {len(wiki_files)}")
    if scope_path:
        print(f"  (scoped to: {scope_path})")

    print()

    # Apply each migration.
    #
    # The recorded vault version only advances past a migration this script can
    # FULLY apply on its own. A requires_llm migration has a manual semantic step
    # (handled afterwards by the vault-migrate skill) that migrate.py cannot
    # perform — so we apply its deterministic operations but HOLD the recorded
    # version at that migration's 'from' and stop. Advancing past it here would
    # make a half-finished update look complete: the next `bootstrap.sh update`
    # (and vault-migrate's own version check) would see vault == framework and
    # silently skip the pending LLM step forever. vault-migrate advances the
    # version with `migrate.py --complete` once the manual step is done.
    total_changed = 0
    llm_migrations = []
    safe_version = vault_version  # highest version fully applied so far

    for migration in pending:
        print(f"Applying {migration['from']} → {migration['to']}: {migration['description']}")

        if not migration.get("operations"):
            print("  (no structural operations — version step only)")
            append_migration_log(migration["from"], migration["to"], 0, dry_run)
        else:
            stats = apply_migration(migration, wiki_files, dry_run)
            append_migration_log(migration["from"], migration["to"], stats["changed"], dry_run)
            total_changed += stats["changed"]
            print(f"  changed: {stats['changed']}  skipped: {stats['skipped']}  errors: {stats['errors']}")

        if migration.get("requires_llm"):
            llm_migrations.append(migration)
            # Hold here — later migrations depend on this one finishing first.
            break

        safe_version = migration["to"]

    last_to_version = safe_version
    if llm_migrations:
        print(f"\nVault version held at {safe_version} — a migration needs a manual LLM step")
        print("and will advance once vault-migrate completes the step(s) below.")
    else:
        print(f"\nUpdating vault version in .vault_version → {safe_version}")
    write_vault_version(safe_version, dry_run)

    # Summary
    print(f"\n{'─' * 50}")
    print(f"Migration {'(dry-run) ' if dry_run else ''}complete — {date.today().isoformat()}")
    print(f"  {vault_version} → {last_to_version}")
    print(f"  Articles updated : {total_changed}")
    print(f"{'─' * 50}")

    # LLM migration instructions
    if llm_migrations:
        print(f"\n⚠ {len(llm_migrations)} migration(s) require a semantic LLM step.")
        print("  Run vault-migrate in Claude Code or Antigravity CLI to complete these:\n")
        for m in llm_migrations:
            instructions = m.get("llm_instructions", "(see migration spec)")
            header = f"  [{m['from']} \u2192 {m['to']}]"
            if isinstance(instructions, list):
                print(header)
                for line in instructions:
                    print(f"    {line}")
            else:
                print(f"{header} {instructions}")

    # Post-migration hints
    needs_reindex = any(m.get("requires_reindex") for m in pending)
    if needs_reindex and not dry_run:
        print("\nNote: one or more migrations require a re-index. Run vault-index to rebuild _index.md.")


if __name__ == "__main__":
    main()

# Updating Your Vault

This page covers how to update an **existing, in-use vault** — one you've already cloned from the template and are actively using. For initial setup, see the [README](../README.md).

There are two types of updates:

1. **Framework updates** — new skills, improved Python engines, fixes to `CLAUDE.md`/`AGENTS.md` (synced by `bootstrap.sh update`)
2. **Article migrations** — structural changes to the wiki format that require existing articles to be updated

---

## 1. Pull Framework Updates

The Seed Vault framework periodically adds new skills, improves engines, and updates
`CLAUDE.md`/`AGENTS.md`. Pull them with the installer's `update` subcommand — no remotes,
no merge, no git history required (your vault doesn't even have to be a git repo).

### Run the update

```bash
cd ~/your-vault

# Latest release
bash bootstrap.sh update

# …or pin an exact version
bash bootstrap.sh update --version v3.0.0

# Preview only — writes nothing, skips migrations/index
bash bootstrap.sh update --dry-run
```

**What gets overwritten:** exactly the paths in `_vault/manifest.txt` — `_vault/` skills &
engines, `_templates/`, `CLAUDE.md`, `AGENTS.md`, `pyproject.toml`, `.gitignore`. The
manifest is the single source of truth for "what is framework."

**What is never touched:** `raw/`, `wiki/`, `viz/`, `outputs/`, and your `README.md` title.
Content safety is structural — update only writes manifest paths, so conflicts on your notes
are impossible.

`update` runs the full cycle for you: sync framework → `_vault/install.sh` (re-link skills,
`uv sync`) → `_vault/migrate.py` (migrate articles if the version bumped) → rebuild the index
→ record the version in `.vault_version`.

> **`.vault_version` records what your *content* is actually at, not just which framework files
> are installed.** Migrations that need LLM reasoning (`requires_llm: true`) are flagged, and
> `migrate.py` deliberately **holds `.vault_version` back** at the pre-migration version until you
> finish them — otherwise a half-done update would look complete and the next `update` would
> silently skip the pending step. Finish flagged migrations by running `vault-migrate` in Claude
> Code or Antigravity CLI (see §2); it advances the version for you once the manual step is done. Until
> then, re-running `bootstrap.sh update` re-syncs the framework and keeps re-flagging the pending
> migration rather than hiding it.

---

## 2. Migrate Existing Wiki Articles

After a framework version bump (check `_vault/VERSION`), existing wiki articles may need structural updates — new required frontmatter fields, renamed tags, updated link patterns, etc.

### Check the current framework version

```bash
cat _vault/VERSION
```

### Run the migration

In Claude Code or Antigravity CLI, invoke the migrate skill:

```
vault-migrate
```

Or describe it: *"Migrate my wiki"* / *"Apply framework updates"*

The skill runs `_vault/migrate.py`, which:
1. Reads all migration specs from `_vault/migrations/`
2. Applies deterministic structural changes (field renames, frontmatter additions)
3. Flags any steps that require LLM reasoning (`requires_llm: true`) for your LLM frontend to handle
4. Appends results to `wiki/_migration-log.md`

### After migration

Rebuild the search index to pick up any changed frontmatter:

```bash
uv run python _vault/lib/index.py --rebuild-qmd
```

Or in Claude Code / Antigravity CLI: *"Reindex"* / *"Rebuild index"*

---

## 3. Verify After Updating

After any framework update or migration, run a health check:

```
vault-lint
```

This runs 9 structural checks and flags broken links, orphaned articles, missing frontmatter, and other issues. Fix any reported problems before continuing to add content.

---

## Customizing Framework Files

`update` overwrites every manifest path wholesale — so edits you make directly to
`CLAUDE.md`, `_vault/` engines, or `_templates/` are replaced on the next update. That's
intentional: the framework stays canonical and transferable. Keep your customizations where
update never reaches:

- **Project-specific instructions**: your vault's `README.md` (templated once on install,
  never re-overwritten) or a local `.claude/` settings file.
- **Local-only content**: `wiki/`, `raw/`, `viz/`, `outputs/`.
- **Forking the framework itself**: if you need to change engines or skills permanently,
  fork the framework repo and point `bootstrap.sh`'s `REPO_URL` at your fork.

---

## Checking What Changed

Preview an update before applying it:

```bash
bash bootstrap.sh update --dry-run          # lists every file that would change
cat .vault_version                          # your vault's current framework version
```

Pin to a known version with `--version vX.Y.Z` if you want to control exactly what lands.

---

## Summary Checklist

- [ ] `bash bootstrap.sh update` (or `--version vX.Y.Z` to pin)
- [ ] Check `.vault_version` — did the framework version bump?
- [ ] If a migration flagged an LLM step: run `vault-migrate`
- [ ] Run `vault-lint` to verify wiki health

## See Also

- [Architecture](Architecture.md)
- [LLM Frontends](LLM-Frontends.md)
- [Article Frontmatter](Article-Frontmatter.md)

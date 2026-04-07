# Updating Your Vault

This page covers how to update an **existing, in-use vault** — one you've already cloned from the template and are actively using. For initial setup, see the [README](../README.md).

There are two types of updates:

1. **Framework updates** — new skills, improved Python engines, fixes to `CLAUDE.md`/`GEMINI.md` (pulled from the upstream template)
2. **Article migrations** — structural changes to the wiki format that require existing articles to be updated

---

## 1. Pull Framework Updates

The upstream Seed Vault template periodically adds new skills, improves engines, and updates `CLAUDE.md`/`GEMINI.md`. These are tracked in git and can be merged into your vault.

### One-time: Add the upstream remote

```bash
git remote add upstream https://github.com/you/seed-vault
```

Replace the URL with the actual Seed Vault template repository URL.

### Each update cycle

```bash
# Fetch upstream changes
git fetch upstream

# Merge framework changes into your vault
# --allow-unrelated-histories is needed if your wiki diverged significantly
git merge upstream/main --allow-unrelated-histories
```

**What gets merged:** Everything tracked in git — `_vault/` skills & engines, `CLAUDE.md`, `GEMINI.md`, `_templates/`, `.obsidian/`, `pyproject.toml`.

**What is never touched:** `raw/`, `wiki/`, `viz/`, `outputs/` — these are fully gitignored and live only on your machine. No merge conflicts are possible on wiki content.

### After merging

```bash
# Re-sync Python dependencies
uv sync

# Re-install skills (Claude Code symlinks + Gemini CLI hard links)
bash _vault/install.sh
```

In Claude Code, skills in `.claude/skills/` are auto-loaded — no reload needed. In Gemini CLI, restart with `gemini` in the vault directory.

---

## 2. Migrate Existing Wiki Articles

After a framework version bump (check `_vault/VERSION`), existing wiki articles may need structural updates — new required frontmatter fields, renamed tags, updated link patterns, etc.

### Check the current framework version

```bash
cat _vault/VERSION
```

### Run the migration

In Claude Code or Gemini CLI, invoke the migrate skill:

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

Or in Claude Code / Gemini CLI: *"Reindex"* / *"Rebuild index"*

---

## 3. Verify After Updating

After any framework update or migration, run a health check:

```
vault-lint
```

This runs 9 structural checks and flags broken links, orphaned articles, missing frontmatter, and other issues. Fix any reported problems before continuing to add content.

---

## Handling Merge Conflicts

If you've modified tracked files (e.g. `CLAUDE.md` or a template), you may hit merge conflicts when pulling upstream changes. In general:

- **`CLAUDE.md` / `GEMINI.md`**: Upstream version is authoritative — accept upstream changes, then re-apply any custom additions you want to keep.
- **`_vault/` skills and engines**: Always accept upstream — these are managed by the framework.
- **`_templates/`**: Accept upstream; templates rarely change.
- **`.obsidian/`**: Usually safe to accept upstream; check if any personal plugin settings are affected.

---

## Checking What Changed

To see what a framework update changed before merging:

```bash
git fetch upstream
git log HEAD..upstream/main --oneline        # commit summary
git diff HEAD upstream/main -- _vault/       # engine/skill diffs
git diff HEAD upstream/main -- CLAUDE.md     # instructions diff
```

---

## Summary Checklist

- [ ] `git fetch upstream && git merge upstream/main`
- [ ] `uv sync`
- [ ] `bash _vault/install.sh`
- [ ] Check `_vault/VERSION` — did the framework version bump?
- [ ] If version bumped: run `vault-migrate`
- [ ] Run `vault-lint` to verify wiki health
- [ ] Rebuild index: `uv run python _vault/lib/index.py --rebuild-qmd`

## See Also

- [Architecture](Architecture.md)
- [LLM Frontends](LLM-Frontends.md)
- [Article Frontmatter](Article-Frontmatter.md)

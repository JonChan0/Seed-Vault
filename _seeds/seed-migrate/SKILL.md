---
name: seed-migrate
description: Migrate existing wiki articles to match the current framework version. Use this skill when the user says "migrate", "migrate my wiki", "update my wiki to the new version", "apply framework updates", "migrate the vault", "my articles are out of date", or after they have pulled a framework update (git pull / git merge from upstream). Detects which migrations are pending and runs the deterministic migration script — then handles any semantic LLM steps if required.
---

# seed-migrate — Incremental Wiki Migration

You are migrating a Seed Vault wiki from an older framework version to the current one. The heavy lifting is done by `_seeds/migrate.py` — a deterministic Python script that applies structural changes (frontmatter field additions, renames, deletions) without any LLM involvement. Your role is to run the script, report results, and handle any semantic migration steps that require LLM reasoning.

---

## Step 1: Version Check

Read `_seeds/VERSION` and `wiki/_index.md` frontmatter.

- If `wiki/_index.md` has no `framework_version:` field, the vault is at `0.0.0` (pre-versioning baseline)
- Compare the two versions

If they match: report "Your vault is already at framework version X.Y.Z. No migration needed." and stop.

---

## Step 2: Show the Migration Plan (Dry Run First)

Run the dry-run to show the user what will change before committing:

```
python3 _seeds/migrate.py --dry-run
```

Report the output to the user. If the vault is large (>50 articles), ask the user to confirm before proceeding. For small vaults you may proceed directly.

---

## Step 3: Apply Migrations

Run the migration script:

```
python3 _seeds/migrate.py
```

Read and report the output summary:
- Version before → after
- Articles updated / skipped / errors
- Whether a reindex is needed

If the script exits with errors, report them to the user and stop. Do not attempt to manually fix migration errors — the script is the source of truth.

---

## Step 4: Handle LLM-Required Migrations (if any)

If the script output includes a warning like "⚠ N migration(s) require a semantic LLM step", read the relevant migration JSON files in `_seeds/migrations/` and look for entries with `"requires_llm": true`.

For each such migration:
1. Read the `llm_instructions` field — it describes exactly what to do
2. Read the `affects` field — it scopes which article type(s) need updating
3. `Glob` only the affected article type directory (e.g., `wiki/topics/*.md`)
4. For each affected article, check whether the change is already present (idempotency)
5. Apply the change as described in `llm_instructions` — be surgical, touch only what is specified
6. Update the `updated:` date on every file you modify
7. Report: "LLM migration applied to N articles"

**Token efficiency rules for LLM steps:**
- Read only the articles in scope — never the full wiki
- Check for the presence of the new section/field before writing — skip if already present
- Use the `llm_instructions` prompt verbatim — do not expand scope

---

## Step 5: Post-Migration

1. If the script reported `requires_reindex: true`: offer to run `seed-index` now
2. Run `seed-lint` if the user wants a health check after migration
3. Report a final summary:

```
Migration complete — YYYY-MM-DD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vault:    0.0.0 → 1.0.0
Script:   N articles updated
LLM step: N articles updated  (or: none required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run seed-lint to verify no issues were introduced.
```

---

## Notes

**Dry-run mode**: If the user says "dry-run" or "show me what would change", run only Step 2 and stop.

**Scoped migration**: If the user wants to migrate only part of the wiki (e.g., "migrate only concepts"), pass `--path wiki/concepts/` to the script:
```
python3 _seeds/migrate.py --path wiki/concepts/
```

**Rollback**: The script does not support rollback. If the user wants safety before migrating, suggest they back up their `wiki/` directory or run `git init wiki/` first.

**Re-running**: The script is idempotent. Running it again after a successful migration will report "Already current. 0 changes." Safely re-runnable.

**Framework authors**: When shipping a new version with breaking changes, bump `_seeds/VERSION` and add a new JSON file to `_seeds/migrations/` describing the operations. See existing files in that directory for the format. Migrations with `requires_llm: true` must include an `llm_instructions` field with a precise, bounded description of what Claude should do.

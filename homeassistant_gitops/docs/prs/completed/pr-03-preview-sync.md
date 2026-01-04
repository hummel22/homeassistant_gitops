# PR-03: Preview sync (dry-run diffs for HA-facing YAML only)

## Summary

Add a “Preview sync” action that shows what YAML Modules would change **without writing any files**.

Preview output must:

- include only HA-facing YAML files (domain YAML + module YAML + one-offs)
- exclude `.gitops/*` state/mappings and exclude `/system/*` exports
- group diffs into:
  - “modules → domain” (build)
  - “domain → modules/one-offs” (update)

## Motivation

Sync is currently a write operation. Operators need a safe way to review the exact YAML edits before
they happen, especially once bulk package moves and item operations exist.

We already have a diff viewer in the UI (Diff2Html). Preview should feed diffs into that viewer.

## Goals

- Implement `/api/modules/preview` returning structured diffs.
- Add a “Preview sync” button in the YAML Modules tab next to “Sync modules”.
- Show diffs in two sections as described above.

## Non-goals

- Previewing GitOps state file diffs (`.gitops/mappings/*`, `.gitops/sync-state.yaml`,
  `.gitops/exports.config.yaml`).
- Previewing `/system` exports.

## Backend design

### API shape

Add:

- `POST /api/modules/preview`

Response example:

```json
{
  "status": "ok",
  "summary": {
    "would_change_count": 3,
    "warnings": []
  },
  "build_diffs": [
    { "path": "automations.yaml", "diff": "diff --git a/automations.yaml b/automations.yaml\n..." }
  ],
  "update_diffs": [
    { "path": "automations/automations.unassigned.yaml", "diff": "diff --git a/..." }
  ],
  "warnings": []
}
```

### How to compute diffs without writing

Recommended approach (implementor choice, but keep it deterministic and testable):

Option A — Writer abstraction (preferred):

- Refactor YAML Modules sync logic to write via an injected “writer” interface:
  - `read(path) -> str`
  - `write(path, content) -> None` (or capture)
- In preview mode, capture `(path, old, new)` and compute diffs in-memory.

Option B — Worktree copy:

- Copy only relevant YAML files to a temporary directory, run sync against it (with `CONFIG_DIR`
  temporarily pointed), then diff temp vs real.
- Must be careful about performance and must not require Git or network.

### Diff formatting

Produce “git-style” unified diffs so Diff2Html can render them:

- Include `diff --git a/<path> b/<path>`
- Include `--- a/<path>` / `+++ b/<path>`
- Use Python `difflib.unified_diff` for hunks.

### File inclusion rules

Include paths that are:

- `*.yaml` / `*.yml`
- not under `.gitops/`
- not under `system/` (exports)

## UI changes

Add:

- Button: “Preview sync”
- Two diff panels:
  - “Domain changes (Build)”
  - “Module changes (Update)”

Operator messaging:

- If there are warnings, show them prominently (same as sync warnings).
- If no diffs, show “No changes.”

## Tests

- Unit test that preview:
  - reports diffs for the same file set that a real sync would change
  - excludes `.gitops/*` and `/system/*` even if they would change in a real sync

## Acceptance criteria

- Operator can preview without modifying any files.
- Preview diffs match subsequent actual sync results (for the same starting state).
- Preview output is limited to HA-facing YAML.


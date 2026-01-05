# PR-15: Toggle `.gitignore` from Git UI

## Summary

Add an "Ignore / Unignore" (toggle) action for files in the Git tab so operators can quickly hide
noisy generated files by updating `/config/.gitignore` from the UI.

## Motivation

When Home Assistant or integrations generate new files (or when the operator adds local-only
artifacts), these can show up as untracked changes repeatedly. Operators should be able to ignore
these without shell access.

## Goals

- In the Git tab, provide a per-file action to toggle ignore state:
  - Diff card action (always available for working tree changes).
  - File viewer action (when previewing a file).
  - (If PR-14 is implemented) Tree item action.
- If a file is currently ignored, the UI shows "Unignore"; otherwise "Ignore".
- The action updates the repo `.gitignore` in the config directory (`settings.CONFIG_DIR/.gitignore`).
- The UI refreshes status after changes and shows a toast with a clear operator-facing message.

## Non-goals

- A full `.gitignore` editor UI.
- Managing global excludes (`.git/info/exclude`, global gitignore).
- Ignoring already-tracked files as a way to hide diffs (gitignore does not affect tracked files).

## Backend design

### Endpoints

Add:

- `GET /api/gitignore/status?path=<relpath>`
  - Returns whether git considers the path ignored and (optionally) the matching rule location.
- `POST /api/gitignore/toggle`

Payload:

```json
{ "path": "path/relative/to/repo", "action": "toggle|ignore|unignore" }
```

Return:

```json
{
  "path": "path/relative/to/repo",
  "ignored": true,
  "changed": true,
  "message": "Added to .gitignore"
}
```

### Implementation notes

- Determine ignore status using git (preferred for correctness):
  - `git check-ignore -v -- <path>` (ignored when exit code is 0)
- Update `.gitignore` safely and predictably by maintaining a managed block:

```gitignore
# BEGIN GitOps Bridge managed
path/to/file
# END GitOps Bridge managed
```

Rules:

- Ignore action:
  - Ensure block exists; add exact path line if not present (idempotent).
- Unignore action:
  - If the path exists in the managed block, remove it.
  - If the path is ignored due to a rule outside the managed block, return a warning message
    (and do not attempt to auto-override unless explicitly requested).

Security constraints:

- Reject path traversal (`..`), absolute paths, and paths outside the repo root.

## UI changes

- Add an "Ignore" / "Unignore" button in diff card actions next to Stage/Unstage.
- When clicked:
  - disable the button while the request is in-flight
  - show toast with result message
  - refresh `GET /api/status` (and PR-14 tree list if present)
- If the selected file is tracked (already committed), keep the button but show a note in the toast
  (or tooltip) that gitignore does not stop diffs for tracked files.

## Tests

- Backend unit tests (temp git repo):
  - Toggling ignore adds/removes from the managed block and is idempotent.
  - Path traversal is rejected.
  - Ignored-by-non-managed rule returns a warning on unignore.

## Acceptance criteria

- Operator can ignore an untracked file and it disappears from the Git tab after refresh.
- Operator can unignore a previously ignored file (added by the UI) and it reappears after refresh.
- `.gitignore` remains readable and changes are constrained to a clearly marked managed block.

## Decisions

- Unignore should add `!<path>` in the managed block when a non-managed ignore rule still applies.

## Open questions

- Should the UI offer "Ignore directory" when the selected path is a folder?

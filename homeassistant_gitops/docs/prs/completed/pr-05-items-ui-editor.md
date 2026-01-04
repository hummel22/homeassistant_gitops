# PR-05: YAML Modules UI — per-file item list + item-focused editor

## Summary

Extend the YAML Modules tab UI to support:

- Selecting a file shows an indented row/list of “top-level items” under the file entry (sidebar).
- Clicking an item loads *just that item* into the editor.
- Support multi-select (shift / ctrl / cmd click) to build an “active selection set”.
  - For v1, multi-select is primarily for bulk move/delete/unassign (PR-06).
  - Editor behavior for multi-select should be “append to view” (read-only preview acceptable).

## Depends on

- `pr-04-items-api.md`

## Motivation

Packaging workflows require selecting and operating on individual YAML entries, not entire files.
This PR is the UI foundation for those workflows.

## Goals

- Show item list for the currently selected file.
- Single-click item selection loads YAML for that item into the editor.
- Multi-select supported via:
  - shift-click range selection
  - ctrl/cmd-click toggle selection
- Editor behavior:
  - Single selection: editable; “Save” writes back via items API.
  - Multi selection: appended YAML view; **read-only** by default (to avoid ambiguous saves).

## Non-goals

- Move/delete/unassign actions and modal (PR-06).
- Templates support.

## UI/UX details

### Sidebar layout

When a file is selected in the file list:

- Render an indented “item row” under that file entry.
- Items are shown as small “cards” or list rows with:
  - display name (alias/name/title)
  - id/key (secondary text)
  - selection highlighting

### Selection behavior

- Clicking a different file clears the selection set.
- Clicking an item:
  - if no modifier: selects only that item
  - ctrl/cmd: toggles the clicked item in the set
  - shift: selects a contiguous range from last focused item

### Editor behavior

- Single item: load YAML from `/api/modules/item` and enable editing.
- Multi select:
  - append each item YAML to the editor view separated by a clear delimiter, e.g.:
    - `# --- ITEM: <id> (<name>) ---`
  - editor becomes read-only, with message: “Multiple items selected. Use Move/Delete/Unassign.”

### Operator messaging

Keep messaging operator-facing:

- When multi-select is active, show “N items selected.”
- If a save is attempted while multi-select, block and show “Save is available for single-item edits only.”

## Implementation notes

- The current module file list renderer is a simple `<div class="commit-item">` list.
  The “indented row” can be implemented as a nested container rendered right after the file item.
- Avoid heavy DOM churn: re-render only the active file’s item list.

## Acceptance criteria

- Selecting a file shows its items beneath it.
- Selecting an item loads only that item into the editor.
- Multi-select works with expected modifiers and appends items to the editor view.
- Single-item save updates only that item.

## Tests

- Frontend: minimal JS unit tests are not present today; rely on manual verification checklist:
  - single select load/save
  - shift selection range
  - ctrl/cmd toggle selection
  - selection resets on file change

Add backend tests only if additional backend behavior is introduced here.


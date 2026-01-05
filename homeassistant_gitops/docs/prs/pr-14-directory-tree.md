# PR-14: Git tab directory tree + file viewer

## Summary

Add a left-hand directory tree to the Git tab's "Working Tree Diffs" area to make it faster to
navigate large working trees and operate on multiple files (stage/unstage selection sets). Also add
a read-only file viewer for non-diff browsing.

## Motivation

Today operators must scroll a long list of diff cards to find files. A tree view enables:

- Faster navigation by directory structure.
- Visual grouping of staged/unstaged/untracked changes.
- Bulk stage/unstage workflows using multi-selection (shift/cmd/ctrl), similar to other git UIs.
- Quick inspection of unchanged files without leaving the UI.

## Goals

- Add a directory tree in the Git tab, positioned left of the diff list.
- Tree supports two modes:
  - **Changed** (default): staged/unstaged/untracked files only.
  - **All files**: all tracked files, plus untracked files; optionally show ignored files.
- Provide lightweight status decoration in the tree:
  - staged / unstaged / untracked / renamed
  - ignored (when shown)
  - clean (unchanged)
- Clicking a tree item:
  - If the file has a diff card in the current diff list, scroll to it and expand it.
  - If the file is clean (no diff), open a file viewer showing the full file contents.
- Multi-select in the tree (shift range select, cmd/ctrl toggle):
  - "Stage selected" and "Unstage selected" actions operate on the selection set.
  - Selection state is visible and includes a selection count.
- Add a read-only file viewer:
  - For text files: show full contents (with a size limit + truncation message).
  - For binary files: do not render; show "Binary file; preview not available."
- Diff cards get a "View file" action that opens the file viewer for that file (worktree content).

## Non-goals

- Editing arbitrary files from the Git tab (YAML Modules editor already exists).
- Full-featured repo explorer features (drag-drop, rename, delete, search across repo).
- Blame/history views.
- Streaming very large files (simple truncation is fine).

## Backend design

### 1) File listing for tree

Changed mode can be derived from existing `GET /api/status` (`changes[]`), but "All files" needs a
new endpoint.

Add:

- `GET /api/git/files?mode=changed|all&include_ignored=false`

Return (flat list; frontend builds the tree):

```json
{
  "mode": "all",
  "files": [
    {
      "path": "automations.yaml",
      "rename_from": null,
      "staged": false,
      "unstaged": true,
      "untracked": false,
      "ignored": false,
      "clean": false
    }
  ]
}
```

Implementation notes:

- "changed" can reuse `git_ops.git_status()` plus `git check-ignore` (optional) for `ignored`.
- "all" can combine:
  - `git ls-files -z` (tracked)
  - `git status --porcelain=v1 -z` (changed + untracked)
  - `git status --porcelain=v1 -z --ignored` or `git ls-files --others --ignored --exclude-standard -z`
    (ignored, when requested)

### 2) File viewer endpoint

Add:

- `GET /api/git/file?path=<relpath>&ref=worktree|HEAD`

Return:

```json
{
  "path": "automations.yaml",
  "ref": "worktree",
  "is_binary": false,
  "truncated": false,
  "size_bytes": 1234,
  "content": "..."
}
```

Constraints:

- Reject path traversal (`..`), absolute paths, and anything outside `settings.CONFIG_DIR`.
- Enforce a max size (e.g. 512KB) and return `truncated=true` with partial content.

## UI changes

### Layout

In `homeassistant_gitops/rootfs/app/static/index.html`, update the Git tab's diff section to use the
existing `.git-grid` layout:

- Left: new "Files" card (tree + controls).
- Right: existing "Working Tree Diffs" card (toolbar + diff list), with minor additions for selection
  actions.

### Tree UX

- Controls:
  - Segmented toggle: Changed / All files
- (Optional) checkbox: "Show ignored"
  - Search input (optional; nice-to-have if tree gets large)
- Each file row shows:
  - filename + directory nesting
  - status chips or subtle icons reusing existing staged/unstaged/untracked styling
- Selection behavior should match the YAML Modules item list selection approach in `app.js`
  (shift range, cmd/ctrl toggle, single-click selects one).

### Navigation

- Clicking a changed file:
  - scrolls to the diff card
  - expands it (if collapsed)
- Clicking a clean file:
  - opens file viewer panel (either in the right column above the diff list or as a modal)

## Tests

- Backend unit tests:
  - `GET /api/git/files` returns correct flags for staged/unstaged/untracked/clean in a temp repo.
  - `GET /api/git/file` blocks traversal and truncates large content.
- Manual UI checklist:
- Tree renders and filters correctly (Changed vs All files).
  - Multi-select + stage/unstage selected works.
  - Clicking tree items scrolls and expands the corresponding diff card.
  - Clean file preview works; binary files show placeholder.

## Acceptance criteria

- Git tab shows a file tree to the left of the diff list.
- Changed mode shows only staged/unstaged/untracked files with correct status decoration.
- All files mode lists tracked files, with optional ignored display.
- Tree multi-selection can stage/unstage the selection set.
- Clicking a file navigates to its diff when present; otherwise shows file preview.

## Decisions

- File preview uses `HEAD` only (no worktree toggle yet).
- "All files" mode includes untracked files by default.
- "Show ignored" remains default off.

## Open questions

- For renamed files, should the tree show `old -> new` (like diff cards) or only the new path?

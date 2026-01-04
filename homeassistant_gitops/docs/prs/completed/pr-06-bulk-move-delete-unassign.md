# PR-06: Bulk move to package/one-off + delete + unassign

## Summary

Implement the core packaging workflow:

- Move selected unassigned items into:
  - an existing package (append)
  - a new package (create + write)
  - a one-off file under the domain folder (create/append)
- Delete selected items from HA config entirely.
- Unassign selected items from a package/one-off back into the canonical unassigned file.

Includes UI modal for destination selection and supports multi-selection (shift/cmd/ctrl).

## Depends on

- `pr-01-automation-id-management.md` (for stable automation IDs)
- `pr-04-items-api.md`
- `pr-05-items-ui-editor.md`

## Motivation

Operators need a first-class way to curate UI-created/unassigned items into packages or one-offs,
and to remove or unassign items without manually editing YAML across multiple files.

## Goals

- Bulk operations on the current item selection set:
  - Move (to package/new package/one-off)
  - Delete (remove from HA-facing YAML)
  - Unassign (move to canonical unassigned file)
- Ensure YAML Modules mapping stays correct after operations.
- For automations: if the moved item is missing `id`, assign `id` derived from `alias` before writing.
- After operations, run YAML Modules sync to rebuild domain files and keep everything consistent.

## Non-goals

- Templates support.
- Export features.
- CLI features.

## Backend design

### Endpoints

Add a bulk operation endpoint:

- `POST /api/modules/items/operate`

Payload:

```json
{
  "operation": "move|delete|unassign",
  "items": [
    { "path": "automations/automations.unassigned.yaml", "selector": { ... } }
  ],
  "move_target": {
    "type": "existing_package|new_package|one_off",
    "package_name": "kitchen",
    "one_off_filename": "dishwasher.yaml"
  }
}
```

Return:

```json
{
  "status": "ok",
  "changed_files": ["packages/kitchen/automation.yaml", "automations.yaml", "..."],
  "warnings": []
}
```

### Move semantics

- Moving means:
  1. remove item from its current file
  2. append item to destination file
  3. update `.gitops/mappings/*` via subsequent sync (or update immediately and still sync)

Destination rules:

- Existing package:
  - directory `packages/<package_name>/`
  - domain file name determined by domain spec:
    - automation: `automation.yaml`
    - scene: `scene.yaml`
    - script: `script.yaml`
    - helpers: `helpers.yaml`
    - lovelace: `lovelace.yaml`
- New package:
  - create directory and domain file if missing
- One-off:
  - under `<domain>/<one_off_filename>` (confirmed)
  - append if file exists

### Unassign semantics

- Remove item from current file (package or one-off)
- Append into the canonical unassigned file for that domain:
  - `<domain>/<domain>.unassigned.yaml`

### Delete semantics

- Remove item from its current file.
- Do not move elsewhere.
- Subsequent sync should remove it from the domain YAML outputs too.

### Automation ID injection during move

- If moving an automation item with missing `id`:
  - set `id` derived from `alias` (per PR-01 rules)
  - ensure collision-safe inside the destination file

### Post-operation sync

After any operation:

- run `sync_yaml_modules()`
- return combined `changed_files` and warnings

## UI changes

### New controls in center card

Add buttons:

- “Move / Save to package…” (opens modal)
- “Delete” (confirm)
- “Unassign” (confirm)

Disable buttons when:

- no items selected
- YAML Modules disabled

### Move modal

Modal content:

- Destination type:
  - Existing package (dropdown)
  - New package (text input)
  - One-off file (text input filename under domain folder)
- Summary: “Moving N items from <source file(s)> to <target>”
- Confirm button

### UX for bulk selection

Multi-select selection set created in PR-05 is the input.

On successful operation:

- clear selection set
- refresh module index + file list
- show toast + warnings if any

## Tests

Backend unit tests:

- Moving from unassigned to:
  - existing package (append)
  - new package (create)
  - one-off (create/append)
- Unassign from package back to canonical unassigned
- Delete removes item and sync removes it from domain output
- Automation move injects `id` from `alias` when missing

## Acceptance criteria

- Operator can select multiple items and move them into a package/new package/one-off.
- Operator can delete items and they disappear from domain YAML outputs after sync.
- Operator can unassign items and they land in the canonical unassigned file.
- Mapping remains consistent and sync produces no unexpected churn.


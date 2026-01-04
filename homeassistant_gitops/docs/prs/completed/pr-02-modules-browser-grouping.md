# PR-02: Fix YAML Modules browser grouping (Packages / One-offs / Unassigned)

## Summary

Fix a UI/UX bug in the YAML Modules “Module Browser” dropdown:

- Current label “Domains” is misleading.
- We want three operator-facing groups:
  - **Packages** (from `packages/<name>/...`)
  - **One-offs** (domain folder YAML files such as `automations/*.yaml`, excluding the canonical
    unassigned file)
  - **Unassigned** (canonical unassigned YAML files only, e.g. `automations/automations.unassigned.yaml`)

## Motivation

Operators currently see a “Domains” group that actually represents the per-domain folders. In our
mental model, “domain files” are the top-level UI-managed aggregates (`automations.yaml`,
`scripts.yaml`, etc.), and the folder files are one-offs/modules. We also want the canonical unassigned
files to be first-class and easy to locate.

## Goals

- Rename the dropdown grouping to match the intended model.
- Ensure **only canonical** unassigned files appear in “Unassigned”.
- Keep the existing workflow: dropdown selects a “module”, then the file list updates.

## Non-goals

- Adding top-level domain YAML files (`automations.yaml`, `scripts.yaml`, etc.) into the module browser.
- Any packaging/move functionality (handled in later PRs).

## Backend changes (index metadata)

Today: `/api/modules/index` returns modules with:

- `kind: "package"` for package modules
- `kind: "domain"` for domain-folder modules (automations/scripts/etc)

Change proposal:

- Replace `"domain"` kind with `"one_offs"` for per-domain folder modules.
- Add `"unassigned"` kind modules for canonical unassigned files.

Definition: canonical unassigned file path is:

- `<domain>/<domain>.unassigned.yaml` (e.g. `automations/automations.unassigned.yaml`)
- same pattern for helpers/lovelace/scenes/scripts
- only include it if it exists on disk

One-offs module behavior:

- For each domain folder (automations/scripts/scenes/templates/helpers/lovelace), list YAML files
  excluding the canonical unassigned file.
- If no files remain after exclusion, omit that module.

## UI changes

Update the “Module Browser” dropdown grouping:

- `Packages` optgroup: `kind === "package"`
- `One-offs` optgroup: `kind === "one_offs"`
- `Unassigned` optgroup: `kind === "unassigned"`

Display naming:

- For one-offs modules, show the domain folder name (e.g. “automations”).
- For unassigned modules, show a friendly name (e.g. “automations (unassigned)”).

## Acceptance criteria

- Dropdown shows 3 groups (when data exists).
- Canonical unassigned files are listed only under `Unassigned` and not duplicated under `One-offs`.
- Selecting any module still shows the correct file list and allows opening/editing files as before.

## Tests

Add/extend `addons/homeassistant_gitops/tests/test_yaml_modules.py`:

- Create `automations/automations.unassigned.yaml` and another `automations/foo.yaml`.
- Assert index includes:
  - one-offs module contains only `automations/foo.yaml`
  - unassigned module contains only `automations/automations.unassigned.yaml`

## Notes

This PR intentionally keeps the browser “module” concept (module -> list of files). Later PRs add
item-level operations inside a selected file.


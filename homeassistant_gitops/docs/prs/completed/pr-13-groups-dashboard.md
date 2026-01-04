# PR-13: Groups dashboard (manage + import + ignore)

## Summary

Add a dedicated UI dashboard for Home Assistant groups that supports:

- Create / edit / delete GitOps-managed groups (backed by YAML Modules `groups.yaml`).
- Optional import of existing Home Assistant groups into GitOps-managed YAML.
- Ignoring/hiding groups that should not be managed by GitOps Bridge.
- Tracking whether a Home Assistant restart has occurred since groups changed (restart required).

## Depends on

- `pr-12-yaml-modules-groups-domain.md`

## Motivation

Editing groups by hand in YAML is error-prone and not discoverable for operators who primarily use
the UI. A groups dashboard provides a safe, reviewable workflow and makes "GitOps-managed groups"
explicit.

## Goals

- Add a UI tab "Groups" in the ingress UI.
- Default view shows only GitOps-managed groups.
- Provide an "Import" workflow for non-managed `group.*` entities discovered from Home Assistant.
- Provide an ignore mechanism so operators can keep certain groups unmanaged.
- Require operators to restart Home Assistant, and track restart-needed status inside GitOps Bridge
  until the operator acknowledges the restart.

## Non-goals

- Editing groups that are not imported/managed by GitOps Bridge.
- Automatically deleting or mutating Home Assistant UI-managed group helpers.
- Supporting non-group "helper group" domains (e.g., light groups) beyond `group.*` in v1.

## Proposed design

### 1) Discovery model

Show two sources:

1. GitOps-managed groups (from YAML Modules `groups.yaml` + module files).
2. Home Assistant groups (from `GET /api/states`, domain `group`).

Classification:

- A group is "managed" if its key exists in YAML Modules mapping for `group`
  (`/config/.gitops/mappings/group.yaml`).
- A group is "unmanaged" if it exists in HA states but not in YAML Modules.

### 2) Ignore config

New file:

- `/config/.gitops/groups.config.yaml`

Schema proposal:

```yaml
schema_version: 1
ignored:
  entity_ids:
    - group.all_lights
```

Behavior:

- Ignored groups are hidden from the dashboard by default.
- Provide a "Show ignored" toggle for troubleshooting.

### 3) UI workflow

UI tab: "Groups"

Sections:

- "Managed" (editable)
- "Unmanaged" (read-only list with "Import" actions; hidden by default behind a toggle)

Create/edit form fields:

- `object_id` (e.g. `kitchen`)
- `name`
- `members` (multi-select or newline list of entity IDs)

Destination:

- New/edited groups can be written to either:
  - a one-off file under `/groups/*.yaml`, or
  - a package module file `/packages/<pkg>/groups.yaml`

A single destination file can contain multiple groups.

Actions:

- Create
- Save edits
- Delete
- Import (creates a YAML entry and marks it as managed)
- Ignore / Unignore

Operator messaging must be explicit:

- Importing a group may conflict if Home Assistant already has a group with the same `entity_id`.
- After creating/importing, run YAML Modules sync and reload group configuration if needed.

Conflict rule (v1):

- If creating a new managed group would result in an entity ID that already exists in Home Assistant
  runtime state (from `GET /api/states`) but is not already managed by YAML Modules, reject the
  operation with HTTP `409` and instruct the operator to either import the group or choose a new
  `object_id`.

### 3b) Restart-required tracking (manual restart)

We will not auto-call reload services from the add-on for this workflow. Instead:

- Any time GitOps-managed group config changes (create/edit/delete/import/sync), mark
-  `groups_restart_needed = true`.
- The UI shows a persistent banner: "Groups changed. Restart Home Assistant, then click
  'I restarted'."
- Add an "I restarted" action that clears the flag.

Persist state (proposal):

- `/config/.gitops/groups.restart-state.yaml`
- Store:
  - `schema_version`
  - `last_groups_change_hash` (hash of group-relevant config files)
  - `last_restart_ack_hash` (hash at time of operator acknowledgment)

This is intentionally based on config hashes (not git commit state) so it works even with local,
uncommitted edits.

### 4) Backend APIs

Add endpoints (shape can be refined during implementation):

- `GET /api/groups`:
  - returns managed + unmanaged lists, ignore config, configuration warning, and restart status
- `POST /api/groups`:
  - create/update a managed group (writes via YAML Modules module file + sync)
- `DELETE /api/groups/{group_id}`:
  - delete a managed group (writes via YAML Modules + sync)
- `POST /api/groups/import`:
  - import an unmanaged HA group into YAML Modules (writes + sync)
- `POST /api/groups/ignore`:
  - update ignore config
- `GET /api/groups/restart_status`:
  - returns whether a restart is required and why (which files changed)
- `POST /api/groups/restart_ack`:
  - marks the current group config as "restarted" (operator acknowledgment)

Implementation should prefer reusing existing YAML Modules item operations where possible (mapping
domain selectors).

## Tests

- Backend unit tests for:
  - ignore config load/save validation
  - importing a group from mocked HA states writes the expected YAML entry
  - managed group create/update/delete writes deterministically and syncs
  - collision guard returns HTTP-409 style error when `group.<object_id>` exists in HA but is unmanaged

## Acceptance criteria

- Operators can manage GitOps-backed groups from the UI without manual YAML editing.
- Unmanaged groups are hidden by default but can be imported intentionally.
- Ignore list is persisted and respected across restarts.

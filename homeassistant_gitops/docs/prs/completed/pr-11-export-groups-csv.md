# PR-11: Export groups (and group-like entities) to `/system/groups.csv`

## Summary

Extend the existing Export feature to include:

- Home Assistant `group.*` entities
- Group-like entities (main target: sensor groups) discovered from state attributes

Write a single export:

- `Groups` -> write `/system/groups.csv`

## Motivation

Groups often represent high-value "operator intent" (what belongs together), but many setups manage
them in the UI or as runtime state. A CSV export provides a diff-friendly snapshot that can be
reviewed in PRs without committing `.storage`.

## Goals

- Add a "Groups" export kind alongside Entities/Areas/Devices.
- Export group membership in a deterministic, diff-friendly format.
- Display the export in the UI table view like the other exports.

## Non-goals

- Writing YAML group definitions.
- Editing/creating groups (handled in a separate groups management PR).
- Making groups export configurable beyond a small set of options.

## Proposed design

### 1) Data source

Groups and group-like entities are not part of the entity/device/area registries in a way we can
export reliably. Use the HA state API:

- `GET /api/states` and filter entities with domain `group`.

Also include "group-like" entities where state attributes indicate membership.

Proposed scope for v1:

- `group.*` entities
- `sensor.*` group entities created via the Group integration
- `light.*` group entities created via the Group integration

Heuristic:

- include an entity if:
  - the entity domain is `group`, `sensor`, or `light`, and
  - `attributes.entity_id` is a list of entity IDs

For each exported state, extract:

- `entity_id`
- `attributes.friendly_name` (or `name`)
- `attributes.entity_id` list (members)

### 2) Output path + schema

- `/config/system/groups.csv`

Proposed columns (kept minimal and diff-friendly):

- `entity_id`
- `name`
- `members` (semicolon-delimited entity IDs, stable ordering)
- `member_count`

Determinism requirements:

- Sort groups by `group_entity_id`.
- Sort members by entity_id and join with `;`.

### 3) UI

Add a 4th export tab:

- Entities / Areas / Devices / Groups

Behavior matches existing exports:

- "Run export" writes CSV.
- Table shows current file content.
- If no export run yet, show a clear operator message.

## Tests

- Mock `/api/states` response and verify:
  - only `group.*` entities are exported
  - member ordering is stable
  - row ordering is stable
  - missing attributes produce empty/default cells, not crashes

## Acceptance criteria

- Operator can export groups and see `/system/groups.csv`.
- Output is deterministic and diff-friendly.
- UI displays groups export like other export kinds.

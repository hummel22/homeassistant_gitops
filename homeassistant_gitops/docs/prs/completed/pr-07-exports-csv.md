# PR-07: Export Entities / Areas / Devices to `/system/*.csv`

## Summary

Add a new UI tab “Export” with three sub-tabs:

- Entities → write `/system/entities.csv`
- Areas → write `/system/areas.csv`
- Devices → write `/system/devices.csv`

Also add a config file `.gitops/exports.config.yaml` to store export settings, including an
integration blacklist for entities.

## Motivation

Operators want version-controlled, reviewable snapshots of registry-like data without committing
Home Assistant `.storage/` (which is volatile and often contains sensitive state).

CSV is chosen for portability and diff-friendliness.

## Goals

- Add `/api/exports/*` endpoints to:
  - generate exports on-demand
  - load current export file(s)
  - read/write `.gitops/exports.config.yaml`
- UI:
  - “Export” tab with Entities/Areas/Devices sub-tabs
  - Table display of current CSV content
  - Controls to “Run export” and “Save config”
- Entity export supports integration blacklist (do not export entities from those integrations).

## Non-goals

- Writing YAML exports.
- Including `.storage` in git.
- Advanced filtering beyond integration blacklist (can be later).

## Backend design

### Storage paths

- `/config/system/entities.csv`
- `/config/system/areas.csv`
- `/config/system/devices.csv`
- `/config/.gitops/exports.config.yaml`

Ensure `system/` exists before writing.

### Config schema (`exports.config.yaml`)

Initial proposal:

```yaml
schema_version: 1
entities:
  integration_blacklist:
    - hacs
    - google_assistant
```

### Data source (Home Assistant Core APIs)

Use Supervisor token to call HA Core HTTP APIs (new helper similar to `ha_services.call_service`):

- Areas: `GET /api/config/area_registry`
- Devices: `GET /api/config/device_registry`
- Entities: `GET /api/config/entity_registry`

Implementation must handle:

- missing/invalid token (return 400/500 with clear operator message)
- HA unavailable/timeouts

### CSV schema (to confirm in implementation)

Entities (`entities.csv`) suggested columns:

- `entity_id`
- `name`
- `platform` (if available) or `integration` (derived)
- `domain` (from `entity_id`)
- `device_id`
- `device_name` (lookup via device registry)
- `area_id`
- `area_name` (lookup via area registry)
- `disabled` / `hidden` flags (if available)
- `original_name` / `icon` / `unit_of_measurement` (optional; include only if stable)

try to include entity type if avaiable

Areas (`areas.csv`) suggested columns:

- `area_id`
- `name`
- `floor` (if available; else blank)

Devices (`devices.csv`) suggested columns:

- `device_id`
- `name`
- `manufacturer` / `model` (if available)
- `area_id`
- `area_name`

### Determinism requirements

- Stable column ordering.
- Stable row ordering (e.g. sort by `entity_id` / `area_id` / `device_id`).
- Quote/escape CSV consistently.

## UI design

Add a top-level tab “Export”:

- Sub-tabs for Entities/Areas/Devices.
- Each sub-tab shows:
  - “Run export” button
  - Table view of current CSV file
  - Status/warnings area

Entities tab adds:

- integration blacklist editor (multiline input or tokenized list)
- “Save export config” button

Operator messaging:

- If the export file does not exist yet, show “No export run yet.”

## Tests

- Backend unit tests should mock HA API responses and verify:
  - CSV files are written
  - blacklist filters entities
  - output ordering is stable
  - missing token returns a clear error

## Acceptance criteria

- Operator can run exports and see resulting tables.
- CSVs are written to `/system` and can be committed.
- Integration blacklist persists in `.gitops/exports.config.yaml` and is applied.


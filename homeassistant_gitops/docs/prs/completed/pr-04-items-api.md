# PR-04: File item APIs (list/read/write items; skip templates)

## Summary

Add backend APIs that expose “top-level items” within a YAML module file so the UI can:

- show an item list beneath a selected file
- load *just one item* into the editor
- support multi-select item sets for later move/delete/unassign operations

Templates are explicitly skipped for now.

## Motivation

The current YAML Modules UI operates at the file level only. Our packaging workflow needs item-level
operations (select/move/delete/unassign) and item-focused editing.

## Goals

- Add endpoints to:
  - list items in a file
  - fetch a single item (as YAML) for editing
  - save a single edited item back into the file (single-select only)
- Return enough metadata for UI to render:
  - display name (alias/name/title)
  - item id/key
  - stable fingerprint
  - domain kind (list vs mapping vs helpers vs lovelace)

## Non-goals

- Bulk move/delete/unassign (PR-06).
- Multi-item editing and saving (PR-05/PR-06 can decide read-only preview).
- Templates domain support.

## API design

### Identify file type / domain

Given a file path, infer its “domain spec”:

- package file `packages/<pkg>/<automation.yaml|scene.yaml|script.yaml|helpers.yaml|...>`
- one-off file `<domain>/<name>.yaml`

Return a `file_kind`:

- `list` (automations/scenes/templates/lovelace views list; templates skipped anyway)
- `mapping` (scripts)
- `helpers` (helpers.yaml format)
- `lovelace` (list or dict shape)

### Endpoints

1) List items in a file

- `GET /api/modules/items?path=<relpath>`

Response:

```json
{
  "path": "packages/wakeup/automation.yaml",
  "file_kind": "list",
  "items": [
    {
      "selector": { "type": "list_index", "index": 0, "id": "wake-up" },
      "id": "wake-up",
      "name": "Wake up",
      "fingerprint": "a1b2c3d4e5f6"
    }
  ],
  "warnings": []
}
```

2) Read a single item for editing

- `GET /api/modules/item?path=<relpath>&selector=<encoded>`

Return:

```json
{
  "path": "...",
  "file_kind": "list",
  "selector": { ... },
  "yaml": "alias: Wake up\ntrigger: []\nid: wake-up\n"
}
```

3) Save a single item

- `POST /api/modules/item`

Payload:

```json
{
  "path": "...",
  "selector": { ... },
  "yaml": "alias: Wake up updated\ntrigger: []\nid: wake-up\n"
}
```

Return: status + new fingerprint.

### Selector model (important)

Do not rely on “list index” alone because list order can change.

Recommended selector fields:

- For list-kind: `{ type: "list_id", id: "<id>", fingerprint: "<fp>" }`
- For mapping-kind: `{ type: "map_key", key: "<key>" }`
- For helpers: `{ type: "helper", helper_type: "<type>", key: "<id>" }`
- For lovelace: `{ type: "lovelace_view", id: "<path>", fingerprint: "<fp>" }`

Implementor note:

- YAML Modules already computes `fingerprint` excluding `id` for list domains. Use that for stable
  matching when needed.

## File parsing rules (v1)

- For automations/scenes: treat each list item as a unit.
- For scripts: treat each top-level key as a unit.
- For lovelace: treat each view as a unit (list or dict-with-views).
- For helpers: decide whether “items” are helper entries (preferred) or helper-type blocks.
  - If we choose per-helper-entry, the UI list is more useful for unassign/move later.

## Error handling

- Invalid YAML: return warnings and do not crash.
- Missing item: 404 with clear message.
- Ambiguous match (e.g. duplicate fingerprints): reject save and require user to re-open.

## Tests

- List items for each supported file kind.
- Read/save round-trip for:
  - list item (automation)
  - mapping key (script)
  - helper entry (helpers.yaml)

## Acceptance criteria

- UI can request item lists and load single-item YAML for editing.
- Saving an edited item updates only that item in the file and preserves other content/order.


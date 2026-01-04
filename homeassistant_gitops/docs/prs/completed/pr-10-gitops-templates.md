# PR-10: File-based templates (`*.template.yaml`) with `!/<path>` includes

## Summary

Add a lightweight template/include system for YAML Modules:

- Templates are normal YAML files named `*.template.yaml` anywhere under `/config/`.
- Other YAML files can include templates using the `!` operator with a config-relative path:
  - Example: `!/packages/common_actions.template.yaml`
  - Example (glob): `!/packages/*.template.yaml`
- During build/sync, templates are expanded and injected into the generated domain YAML so Home
  Assistant never sees the template tags.

## Motivation

YAML Modules encourages modular configuration, but common patterns still lead to copy/paste:

- repeated triggers/conditions/actions in automations
- shared service call blocks in scripts
- repeated card/view metadata in lovelace modules

File-based templates keep snippets close to the YAML they affect, avoid a new `.gitops/` schema, and
make reuse explicit.

## Goals

- Support template includes in any YAML Modules source file (packages, one-offs, unassigned).
- Expand includes during build so domain YAML is plain YAML (no template tags written to HA-facing
  files).
- Compute fingerprints after template expansion (fingerprint the expanded item).
- If a template include is invalid/missing, record an error and skip applying it (do not crash).
- Handle "domain edited inside a template-expanded region" by generating a `*.diff` artifact instead
  of guessing.

## Non-goals

- Supporting the Home Assistant `templates.yaml` domain (still unsupported in YAML Modules).
- Jinja evaluation, runtime rendering, or a full templating language.
- Auto-applying UI edits back into template files.

## Proposed design (v1)

### 1) Template discovery

Definition:

- Any YAML file under `/config/` that matches `**/*.template.yaml` is a template file.
- Template files are never included into domain outputs unless referenced by an include.

### 2) Include syntax (`!/<path>`)

In any YAML Modules file, a value can be replaced with a template include by tagging it with a
config-relative path:

Examples:

- Replace an entire list value:

```yaml
action: !/packages/common_actions.template.yaml
```

- Replace an entire mapping value:

```yaml
variables: !packages/common_vars.template.yaml
```

Leading slash is optional. `!/packages/foo.template.yaml` and `!packages/foo.template.yaml` are
equivalent.

Glob includes:

- `!/packages/*.template.yaml` expands to multiple template payloads.
- Merge behavior depends on the resolved payload shapes:
  - list payloads: concatenate (sorted by path for determinism)
  - mapping payloads: deep-merge (sorted by path; later templates override earlier templates)
  - mixed payloads: error + skip include

### 3) Build-time behavior

- Template tags are resolved during YAML loading (or a pre-processing pass) before YAML Modules
  normal parsing/merging.
- Domain outputs written by YAML Modules must not contain template tags; only expanded YAML is
  written.
- Preview diffs must reflect the expanded output (what would be written).

### 4) Fingerprints and mappings

Fingerprints must be based on the expanded item (after template merge).

Implication: changing a template will change fingerprints for every item that includes it.

### 5) Update behavior when a domain file is edited inside a template-expanded region

Problem: domain YAML contains expanded content. If the operator edits the domain file (UI or file
edit) and the edit touches content that originated from a template include, we cannot safely infer
whether they intended to change:

- the template file
- the module file that included it
- or just the expanded result

v1 approach:

- Detect that an edited region corresponds to a template include (based on stored include metadata).
- Do not modify the template automatically.
- Create a diff artifact next to the template:
  - `<template_path>.diff` (example: `packages/common_actions.template.yaml.diff`)
- At the top of the `.diff` file, write a YAML comment header describing where the edit happened and
  which include site it came from, for example:
  - `automations.yaml:49`
  - `packages/myautomation.yaml:60 (included packages/common_actions.template.yaml)`
- The remainder of the file is a unified diff representing the proposed change to the template.
- Sync should return a warning/error explaining that a template-backed edit was detected and a diff
  file was generated for operator review.

This keeps the system safe and reviewable: operators decide whether to apply the diff to the
template and then resync.

## TODO

- Add an operator-facing doc with a full example:
  - a template file
  - a module file that includes it
  - the resulting expanded domain YAML output

## Tests

Add unit tests under `addons/homeassistant_gitops/tests/`:

- Template include resolves a single file and expands into domain output.
- Glob include resolves multiple templates deterministically.
- Missing template include produces an error and does not crash.
- Fingerprints change when template content changes (expanded fingerprint).
- Template-backed domain edits generate a `.diff` artifact with correct header metadata.

## Acceptance criteria

- Operators can use `*.template.yaml` files and include them via `!/<path>`.
- Domain YAML outputs never contain template tags; only expanded YAML is written.
- Invalid includes are surfaced clearly (error + skip), and the service does not crash.
- If a domain edit touches template-expanded content, a `.diff` file is generated instead of
  guessing an automatic fix.

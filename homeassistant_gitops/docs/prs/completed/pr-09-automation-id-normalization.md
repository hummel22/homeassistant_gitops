# PR-09: Automation ID normalization (generate `id` from name when missing)

## Summary

Validate Home Assistant automation `id` requirements and, if needed, adjust YAML Modules so new
automations without an `id` get a safe, deterministic `id` derived from the automation name.

Proposed simplest behavior:

- If an automation item is missing `id`, generate `id` from `alias` using a snake_case-like rule
  (lowercase words joined with `_`), ensure uniqueness, write it back to the module file, then build.

This PR is only about how we generate new IDs when missing. It must not rewrite existing `id`
values.

## Context / current behavior

PR-01 is implemented. Today YAML Modules generates missing automation IDs using the raw `alias`
string (unique via suffix rules) and can reconcile IDs after HA reload if HA rewrites
`automations.yaml`.

This PR exists to verify whether our current behavior matches Home Assistant expectations and to
switch to a more conservative generated-ID format if that reduces risk (spaces/punctuation, etc.).

## Research (needs confirmation in this PR)

Home Assistant docs indicate that when migrating YAML automations into `automations.yaml` for use
with the UI editor:

- `automations.yaml` must remain a list
- each automation needs a unique `id` (it can be any unique string)

Reference: https://www.home-assistant.io/docs/automation/yaml/

This PR should confirm whether HA truly accepts arbitrary strings (spaces/punctuation) for `id`, or
whether a normalized format is safer in practice.

Observed doc excerpt (as of 2026-01):

- "Make sure that automations.yaml remains a list! For each automation that you copy over, you'll
  have to add an id. This can be any string as long as it's unique."

## Goals

- If `id` is missing for an automation:
  - generate a deterministic ID from `alias` using a normalization rule
  - ensure uniqueness within the target file
  - persist the generated `id` back into the module file (so subsequent syncs are stable)
- Do not modify existing `id` values (even if they do not match the new normalization).
- Keep mapping stability (no churn across runs).

## Non-goals

- Changing scene or lovelace ID behavior.
- Implementing new reconciliation logic (only adjust generation if required).
- Template-domain support.

## Proposed normalization rule (v1)

Input: `alias` string.

Output: `id` string, computed as:

1. `alias.strip()`
2. Split camelCase boundaries into words (so `KitchenLights` becomes `Kitchen_Lights`)
3. Lowercase
4. Convert runs of non-`[a-z0-9]` characters to `_`
5. Collapse multiple `_` to a single `_`
6. Strip leading/trailing `_`
7. If the result is empty, fall back to a synthetic ID (existing behavior)
8. Ensure uniqueness:
   - if collision, append `_2`, `_3`, ...

Generated IDs are restricted to `[a-z0-9_]`.

## Tests

Add/update unit tests under `addons/homeassistant_gitops/tests/`:

- Missing `id` + `alias: "Kitchen Lights"` -> `id: "kitchen_lights"`
- Punctuation/spaces collapse deterministically.
- Collision handling produces stable suffixes.
- Existing IDs are not rewritten.

## Acceptance criteria

- New automations without `id` get a deterministic, safe ID derived from `alias`.
- Sync/build does not churn IDs across runs.
- Behavior aligns with Home Assistant requirements for YAML automation editor compatibility.

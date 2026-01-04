# PR-01: Automation ID management (alias-based IDs + optional reconciliation)

## Summary

Improve automation `id` behavior in YAML Modules so newly created/moved automations are stable and
human-friendly, using `alias` as the default `id` source, and (optionally) reconciling module IDs if
Home Assistant rewrites `automations.yaml` after reload/restart.

This PR is foundational for package moves and unassigned workflows because mapping stability depends
on reliable IDs.

## Depends on

- `pr-00-automation-id-spike.md` (confirms what HA actually does)

## Goals

- When an automation item is missing `id`, assign a deterministic ID derived from `alias`.
- Support existing configurations where:
  - `id` is a UUID-like string
  - `id` equals the human name / alias
  - `id` is absent (legacy or hand-authored)
- Enable a safe path to reconcile module IDs if HA changes the ID in `automations.yaml` after a reload
  (only if the spike confirms this happens).

## Non-goals

- Template domain improvements (explicitly skipped).
- Introducing HA “create automation” APIs (file-driven only for now).

## User-facing behavior

- New/moved automations should end up with an `id` that looks like the alias.
- Existing `id` values should **never** be rewritten automatically unless we are explicitly
  reconciling with a domain-file change that was authored by Home Assistant itself.
- After a sync/build, the operator can stage/commit in the UI; if reconciliation produced further
  changes, those should also be visible and stageable.

## Proposed implementation details

### 1) Alias-based ID generation

Where IDs are injected today:

- YAML Modules list-domain parsing assigns an `id` when missing and `auto_id` is true.

Change the ID generation for `automation` (and optionally `scene`, `lovelace` later) to prefer:

1. `alias` (exact string) as the ID source.
2. If unsafe/invalid, use a slugified/normalized variant (define normalization rules).
3. If collision occurs inside the same domain file, add a deterministic suffix (e.g. `-2`, `-3`).

Open implementor detail:

- Whether HA accepts spaces/punctuation in `id` should be decided from PR-00 results.
  - If HA accepts raw alias: keep raw alias.
  - If HA normalizes or rejects: implement a normalization strategy and document it.

### 2) ID reconciliation after reload (conditional)

Only implement if PR-00 shows that HA rewrites YAML automation IDs on disk.

Desired transaction for “new automation added”:

1. Run “build” (modules → `automations.yaml`) in the add-on.
2. Call `automation.reload` (or restart if required).
3. Wait for HA to finish and for `automations.yaml` to settle (file hash stable or watcher-based).
4. If HA rewrote automation IDs:
   - Match old items to new items using `fingerprint` (excluding `id`) with `alias` as a tiebreaker.
   - Update the module file item’s `id` to the new HA-written ID.
   - Update `.gitops/mappings/automation.yaml` entries accordingly.
5. Return the final changed file set to the operator; do not auto-stage/commit.

Matching rules (suggested):

- Primary: `fingerprint` equality (already computed excluding `id`).
- Secondary (if multiple items share same fingerprint): `alias` equality.
- If still ambiguous: emit a warning and skip reconciliation for those items (do not guess).

Safety:

- Time bound waiting (e.g. 10–30s) to avoid hanging the API request.
- If HA never rewrites the file within timeout, skip reconciliation.
- If reconciliation would rewrite many IDs unexpectedly, emit warnings and require operator review.

### 3) API changes

Decide one of:

- Extend existing `/api/modules/sync` response with:
  - `post_reload_reconciled: bool`
  - `reconciled_ids: [{ old_id, new_id, source_file }]`
  - additional warnings

Or:

- Add a separate endpoint `/api/modules/automation/reconcile_ids` (called after sync).

### 4) Tests

Add targeted unit tests in `addons/homeassistant_gitops/tests/`:

- New automation without `id` becomes `id == alias` (or normalized alias).
- Duplicate alias collision -> deterministic suffix.
- If reconciliation is implemented: simulate domain file rewrite and ensure module ID updates happen
  via fingerprint matching and mapping entry updates.

## Acceptance criteria

- Adding an automation item without `id` results in a stable, human-friendly `id` derived from
  `alias`.
- Sync/build does not churn IDs across runs.
- If reconciliation is enabled:
  - It only runs when needed (new IDs injected or domain changed by HA).
  - It updates module IDs and mapping entries deterministically.
  - It emits clear warnings on ambiguity.

## Operator messaging (UI)

If reconciliation runs, surface a clear operator note:

- “Home Assistant rewrote automation IDs after reload; YAML Modules updated module files to match.
  Review and commit the changes.”

## Risks / Mitigations

- Risk: HA rejects/ignores non-slug IDs. Mitigation: base normalization rules on PR-00 results.
- Risk: fingerprint collisions cause wrong matches. Mitigation: never reconcile when ambiguous.
- Risk: long waits on reload. Mitigation: timeouts + warnings.


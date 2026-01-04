# PR-00: Spike — Home Assistant Automation `id` semantics

## Summary

Run a focused research spike to confirm how Home Assistant treats `id` for YAML automations
(`automations.yaml`) across:

- missing `id`
- `id` set to the automation `alias`
- edits performed via UI vs file edits
- reloads (`automation.reload`) and restarts

This spike produces a short write-up + a concrete recommendation that unblocks the implementation
work in `pr-01-automation-id-management.md`.

## Motivation

We plan to auto-assign an automation `id` when moving/newly creating an automation module entry.
Current assumption: we can set `id` to the automation `alias`. Uncertainty: Home Assistant may
rewrite IDs or assign a different stable ID at runtime and/or on reload/restart. If HA rewrites the
ID, we must detect it and write it back into the module file to keep mapping stable.

We are explicitly **file-driven** for now (no HA “create automation” API usage), so we need to
understand what HA will and won’t mutate on disk.

## Scope / Deliverables

- A written report (add to the PR description or a short doc in this folder) answering the questions
  below with evidence (observations + logs + file diffs).
- A recommended implementation strategy for:
  - “new automation item with missing `id`”
  - “domain file changed and `id` changed”
  - “how to reconcile module `id` to domain `id`”
- Decide whether we need an “automation reload + reconcile IDs” step in the add-on after build/sync.

## Non-goals

- Implementing code changes (this PR is a spike only).
- Covering templates domain (explicitly skipped for now).

## Questions to Answer (Acceptance Criteria)

1. If an automation entry in YAML **has no `id`**, does HA:
   - accept it and keep it id-less on disk?
   - assign an internal ID only (not written back)?
   - write a new `id` back into `automations.yaml` at any point?
2. If we set `id: <alias>` (spaces/punctuation included), does HA:
   - accept it as-is?
   - normalize/slugify it?
   - reject it?
3. Does `automation.reload` cause HA to write any changes back into `automations.yaml`?
4. Does a full HA restart cause HA to write any changes back into `automations.yaml`?
5. If a user edits an automation via the UI, where does it land:
   - `.storage/` only?
   - or can it write into `automations.yaml`?
6. Is there any observed path where HA changes only the `id` while keeping the rest of the item
   functionally identical?
7. If HA does not write anything back to `automations.yaml`, do we still need reconciliation, or can
   we treat our on-disk `id` as authoritative?

## Proposed Experiment Plan

Run each scenario and record:

- exact input YAML (before)
- action performed (sync/build, reload, restart, UI edit)
- resulting files (after), especially:
  - `/config/automations.yaml`
  - any module file involved (e.g. `/config/packages/<pkg>/automation.yaml`)
  - any `.storage` artifacts relevant to automations (if present)

### Scenario A — Missing `id`

1. Create an automation item with an `alias` and no `id` in a module file.
2. Run the add-on build/sync to generate `automations.yaml`.
3. Call `automation.reload`.
4. Restart HA.
5. Observe whether `automations.yaml` changes.

### Scenario B — `id == alias`

1. Create automation with `id: "<alias>"` (alias contains spaces + punctuation).
2. Run build/sync.
3. Reload + restart.
4. Observe mutations/rejections.

### Scenario C — UI edits

1. Take an automation that exists in YAML.
2. Attempt to edit it via the UI editor (if HA allows).
3. Observe whether `automations.yaml` changes or if changes are stored elsewhere.

## Expected Output (What to write up)

- A clear answer to whether HA rewrites IDs in YAML automations.
- If HA rewrites IDs, describe the exact condition(s) and timing.
- A recommendation for PR-01:
  - whether “reconcile IDs after reload” is necessary
  - and if yes, what matching strategy is safe (fingerprint + alias fallback, timeouts, etc.)

## Notes / Pointers

- Existing YAML Modules already computes an `item.fingerprint` that excludes the `id` field for list
  domains (automation/scene/lovelace). That fingerprint can be used to match items when `id` changes.
- Existing add-on code can call services using Supervisor token (see
  `addons/homeassistant_gitops/rootfs/app/gitops_bridge/ha_services.py`).


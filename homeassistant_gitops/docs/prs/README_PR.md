# PR Plan (Home Assistant GitOps Bridge)

This folder contains detailed, implementor-facing PR descriptions for the planned work in
`addons/homeassistant_gitops`.

Use the following agent prompt and description when you want an agent to take a PR brief,
refine it with you, and then implement it. The workflow is:

1. Create a PR file in `addons/homeassistant_gitops/docs/prs/*.md` with top-level descriptions.
2. Point the agent at that PR file.
3. Paste the prompt below.
4. Collaborate to refine the PR before implementation. Ask the user questions to help you refine the PR

## Description for agents

- This repository includes the Home Assistant GitOps Bridge add-on.
- Backend: FastAPI in `addons/homeassistant_gitops/rootfs/app/gitops_bridge`.
- UI: static HTML/CSS/JS in `addons/homeassistant_gitops/rootfs/app/static`.
- YAML Modules logic is centralized in `addons/homeassistant_gitops/rootfs/app/gitops_bridge/yaml_modules.py`.
- Mappings and sync state live under `.gitops/` in the config directory (`mappings/*.yaml`,
  `sync-state.yaml`).
- Module sources:
  - `packages/*` for package modules.
  - One-offs under domain folders (`automations/`, `scripts/`, `groups/`, `scenes/`, `helpers/`, `lovelace/`).
  - Canonical unassigned files: `<domain>/<domain>.unassigned.yaml`; helpers use
    `helpers/helpers.unassigned.yaml`.
- Domain outputs:
  - `automations.yaml`, `scripts.yaml`, `groups.yaml`, `scenes.yaml`, `templates.yaml`, `ui-lovelace.yaml`,
    and `input_*.yaml` helpers.
- Automation IDs:
  - If missing, set `id` from `alias` (unique, collision-safe).
  - Reconciliation may occur after HA reloads.
- Templates:
  - Templates are supported via `*.template.yaml` files referenced by template include tags (`!/<path>.template.yaml`).
  - Template tags are expanded during sync/build; HA-facing YAML never contains template tags.
- Exports:
  - CSV outputs live under `system/`: `entities.csv`, `areas.csv`, `devices.csv`, `groups.csv`.
  - Export config lives in `.gitops/exports.config.yaml` with an integration blacklist.
- CLI:
  - Install into `.gitops/cli/`.
  - Run via `python3 .gitops/cli/gitops_cli.py validate|build|update`.
  - `validate` does not fail fast; supports `--json` and `--strict`.
- Operator-facing UI messaging must be clear and explicit. If editing
  `services/hassems/frontend`, match the operator guidance in `AGENTS.md`.

## Prompt for agents

```text
You are a coding agent working in /Users/hummel/repos/hass.

Task: Refine and implement the PR described in: <PR_FILE_PATH>

Workflow:
1) Read <PR_FILE_PATH> and summarize the goal in 3-5 bullets.
2) Inspect current implementation in `addons/homeassistant_gitops/` to understand what exists.
3) Ask clarifying questions for any ambiguous requirements, edge cases, or missing acceptance
   criteria. Do NOT start code until questions are answered.
4) Propose concrete PR refinements (expanded scope, API/UI behavior, test plan, data schemas).
   Update the PR doc if needed and ask for confirmation.
5) After confirmation, implement the PR with minimal divergence from existing patterns, add or
   update tests, and run them.
6) Report changes with file paths and a short rationale; call out any tests not run and why.

Project rules (must follow):
- Read and obey `AGENTS.md` instructions (historic data rules, cursor requirements, migrations
  in `services/hassems/storage.py`, etc.).
- YAML Modules:
  - Module dirs: `packages/`, `automations/`, `scripts/`, `groups/`, `scenes/`, `helpers/`, `lovelace/`.
  - Domain files: `automations.yaml`, `scripts.yaml`, `groups.yaml`, `scenes.yaml`, `templates.yaml`,
    `ui-lovelace.yaml`, `input_*.yaml`.
  - Unassigned files: `<domain>/<domain>.unassigned.yaml`; helpers: `helpers/helpers.unassigned.yaml`.
  - Automation IDs: if missing, derive from `alias` (unique).
  - Templates are supported via `*.template.yaml` and `!/<path>.template.yaml` includes.
- Exports:
  - CSV outputs in `system/`: `entities.csv`, `areas.csv`, `devices.csv`, `groups.csv`.
  - Config in `.gitops/exports.config.yaml` with integration blacklist.
- CLI:
  - Install to `.gitops/cli/`.
  - Run as `python3 .gitops/cli/gitops_cli.py validate|build|update`.
  - Validate must accumulate errors/warnings; `--json` and `--strict` required.

Implementation rules:
- Prefer `rg` for searching; default to ASCII-only edits.
- Use `apply_patch` for single-file edits when practical.
- Avoid destructive git commands; do not revert unrelated changes.
- Update or add tests for behavior changes and API contracts.
- Keep frontend messaging operator-facing and explicit.

Deliverables:
- Updated code + tests.
- Updated PR doc if scope or behavior changed.
- A brief summary and next steps (tests to run, any follow-ups).

Ask questions first; do not implement until confirmed.
```

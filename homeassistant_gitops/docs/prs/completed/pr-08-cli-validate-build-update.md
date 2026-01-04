# PR-08: Installable CLI (`validate`, `build`, `update`) in `.gitops/cli`

## Summary

Add a lightweight, repo-local CLI that can be installed from the add-on UI into:

- `/config/.gitops/cli/`

The CLI provides commands:

- `validate` — run checks and produce a structured report (does not “fail fast”)
- `build` — write domain YAML from module files
- `update` — write module files from domain YAML

The CLI should require **only `python3`** (no `uv`, no venv requirement).

## Motivation

Operators want local validation and reproducible build/update steps outside the add-on UI, suitable
for pre-commit hooks or CI. The CLI should mirror the YAML Modules logic closely to avoid “works in
UI but fails in CI”.

## Goals

- Add UI control in Settings: “Install CLI”
  - writes files into `.gitops/cli/`
  - does not overwrite local modifications unless explicitly confirmed
- Implement CLI commands:
  - `validate`: produces a report of issues and warnings at each step; it should not exit early
  - `build`: “modules → domain” only
  - `update`: “domain → modules/unassigned” only

## Non-goals

- Requiring external dependencies beyond python3 + whatever the add-on already depends on.
- Managing git operations from the CLI (commit/push).

## CLI behavior details

### Packaging and entrypoint

Suggested layout:

```
.gitops/cli/
  gitops_cli.py
  README.md
```

Run as:

- `python3 .gitops/cli/gitops_cli.py validate`
- `python3 .gitops/cli/gitops_cli.py build`
- `python3 .gitops/cli/gitops_cli.py update`

### Output (validate)

Validate should generate a report object and print it as:

- human-readable text (default)
- optional `--json` for machine use

Report should include:

- per-domain results (automation/script/scene/helpers/lovelace)
- parse errors
- mapping inconsistencies
- what build/update would change (counts + paths)

Important: validate should not “fail fast” or exit at the first failure. It should accumulate and
return reasons for each failure at each step.

### Exit codes

Open implementor decision (document clearly):

- either always exit `0` (strictly informational), or
- exit `1` if any errors exist (still printing the full report)

Given the requirement “should not fail and exit”, prefer:

- exit `0` by default
- add `--strict` to exit non-zero if errors exist

### Implementation approach

The current YAML Modules implementation is “sync” oriented. To support build/update:

- Refactor YAML Modules logic to allow:
  - forced preference = “modules” (build)
  - forced preference = “domain” (update)
  - and/or “write only these targets” (domain-only writes for build, module-only writes for update)

Prefer minimal divergence between add-on and CLI:

- Reuse the same internal functions.
- Do not duplicate YAML logic in a separate copy if avoidable.

## UI installer design

Add a Settings action:

- Button: “Install CLI”
- Writes `.gitops/cli/*`
- If files already exist, show confirmation and/or “overwrite” toggle.

## Tests

- Unit test the generator that writes CLI files (idempotency, no overwrite without confirmation).
- Unit test CLI validate produces a report even on errors.

## Acceptance criteria

- Operator can install the CLI from Settings.
- CLI runs with python3 and performs validate/build/update as specified.
- Validate produces a full report and does not stop at first error.


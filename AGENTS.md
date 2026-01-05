# AGENTS.md

This file defines the working agreement for automated agents (and humans) editing this
repository. Follow these rules for any changes within this repo.

## Scope

- This file applies to the entire repository unless a more specific `AGENTS.md` exists
  in a subdirectory.
- When in doubt, prioritize clarity, maintainability, and modularity.

## System overview (high level)

The Home Assistant GitOps Bridge add-on monitors the Home Assistant `/config` directory,
provides an ingress UI to stage/commit changes, and syncs with GitHub over SSH. It also
supports webhook-triggered pulls and a YAML Modules workflow for keeping configuration
organized across packages and domain-specific files.

Key areas:

- Add-on packaging/config: repository root and `homeassistant_gitops/` (build files,
  manifest, Dockerfile, and add-on metadata).
- Runtime application: `homeassistant_gitops/rootfs/app/` (the Python service that
  runs in the add-on container).
- Docs & tests: `homeassistant_gitops/docs/` and `homeassistant_gitops/tests/`.

## Module-by-module map (runtime application)

Runtime code lives in `homeassistant_gitops/rootfs/app/gitops_bridge/`.
Use this map to locate functionality:

- `__init__.py`: Package initialization and exported symbols.
- `api.py`: HTTP/API surface for the ingress UI and webhook endpoints.
- `cli_installer.py`: CLI/installation helpers used during setup flows.
- `config_store.py`: Persistence layer for GitOps config state and metadata.
- `exports.py`: Export helpers/serialization used by API/UI.
- `fs_utils.py`: File system utilities and path helpers. Prefer this module for
  file operations to keep behavior consistent.
- `git_ops.py`: Git interaction logic (status, commits, pushes, pulls).
- `gitignore_ops.py`: Git ignore template handling and updates.
- `groups.py`: Grouping helpers for YAML Modules and UI representation.
- `ha_services.py`: Home Assistant service interactions and glue code.
- `settings.py`: Configuration loading and accessors.
- `ssh_ops.py`: SSH key generation and remote connection helpers.
- `watchers.py`: File watching and change detection for `/config`.
- `yaml_modules.py`: YAML Modules sync logic (build/update/sync behaviors).
- `yaml_tags.py`: Custom YAML tag handling and parsing utilities.
- `spikes/`: Experimental or exploratory code; avoid production dependencies on this.

Other runtime entry points:

- `homeassistant_gitops/rootfs/app/main.py`: Service startup entry point.
- `homeassistant_gitops/rootfs/app/static/`: UI assets served by the ingress UI.

## Editing rules

### Comments & docstrings

- Every public class and function **must** have a docstring that explains:
  - What it does.
  - Key parameters/return values.
  - Side effects or important caveats.
- Inline comments should be used sparingly and only when logic is non-obvious.
- If you modify behavior, update associated comments/docstrings in the same change.
- Prefer clear, concise language and include examples only when they clarify usage.

### Documentation updates

- Update README files and this `AGENTS.md` when changes are **substantial** or
  user-facing (new features, behavior changes, new configuration options).
- If a change is minor or purely internal, documentation updates may be skipped.
- When updates are required:
  - Keep descriptions accurate and concise.
  - Update only the relevant sections.
  - Avoid duplicating content across docs; link instead when possible.

### Modular design rules

- Keep changes scoped to the smallest meaningful module.
- Avoid cross-cutting edits unless they are truly necessary.
- Prefer adding focused helpers in the most relevant module rather than expanding
  an unrelated module.
- Avoid circular dependencies across `gitops_bridge` modules.
- Reuse shared utilities (`fs_utils`, `config_store`, etc.) rather than re-implementing.

## Implementation patterns for agents

- Start from the module map above to pick the most appropriate location.
- Keep pull requests small and focused; avoid unrelated refactors.
- Prefer clear, incremental changes over large rewrites.
- Update comments/docstrings and docs in the same change set when behavior changes.
- If you add new code, also update tests and README sections as needed.

## Testing guidance

### When to add or update tests

- Add tests for all new behavior, new configuration options, or bug fixes.
- Update existing tests if behavior changes (even if the public API stays the same).
- Skip tests only if the change is documentation-only; note this explicitly in PR notes.

### What to test

- Test at the level of **user stories** and **module boundaries**:
  - Example: “When the webhook endpoint is hit, it triggers a pull without losing
    local changes.”
  - Example: “YAML Modules sync preserves assigned modules and tracks unassigned items.”
- Cover both success paths and failure modes (e.g., missing SSH keys, invalid config).
- Use fixtures/helpers where appropriate to keep tests readable and isolated.

### How to run tests

- Preferred: `uv run --project homeassistant_gitops --extra dev pytest homeassistant_gitops/tests`
- If a smaller test set is sufficient, document the subset in your PR notes.

## README and agent file update policy

- If you modify code or add new modules, update:
  - Relevant README sections (root or `homeassistant_gitops/README.md`).
  - This `AGENTS.md` if guidance, module maps, or workflows change.
- If changes are minor or internal, you may skip README updates.
  - In that case, state why in the PR summary.

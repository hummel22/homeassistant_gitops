# Home Assistant GitOps Bridge

The Home Assistant GitOps Bridge add-on tracks configuration changes in `/config`, exposes an
ingress UI to stage and commit changes, and syncs with Git via SSH.

## Installation

1. Add this repository to your Home Assistant add-on store.
2. Install the Home Assistant GitOps Bridge add-on.
3. Start the add-on and open the ingress UI from the sidebar.

## Add-on configuration

| Option | Description | Default |
| --- | --- | --- |
| `remote_url` | SSH URL for the Git repository (example: `git@github.com:user/ha-config.git`). | `""` |
| `remote_branch` | Remote branch to sync. | `main` |
| `notification_enabled` | Enable persistent notifications. | `true` |
| `webhook_enabled` | Enable the webhook pull endpoint. | `false` |
| `webhook_path` | Path segment for the webhook. | `pull` |
| `poll_interval_minutes` | Periodic remote check interval in minutes. | `15` |
| `yaml_modules_enabled` | Enable YAML Modules sync across package and one-off YAML files. | `true` |
| `ui_theme` | UI theme preference (`light`, `dark`, or `system`). | `system` |

## Usage

1. Configure `remote_url` and add the generated SSH public key to GitHub (or your Git host).
2. Use the UI to commit and push changes.
3. Enable the webhook and/or periodic checks if desired.

## GitOps config file

The add-on writes a GitOps config file into your repository at `/config/.gitops/config.yaml`.
It mirrors all add-on options so they can be tracked in Git and reviewed in pull requests.
If you edit `/config/.gitops/config.yaml`, restart the add-on to apply changes.
Legacy `/config/.gitops.yaml` files are migrated into the new folder on startup.

## Manual Git setup

If you already manage `/config` with Git, the add-on will detect the existing repository and
will not re-initialize or overwrite it. It will keep using your `.gitignore` and history.

To configure Git manually:

1. Create a Git repository (empty, no README or `.gitignore`).
2. From the Home Assistant host, initialize or clone into `/config`:
   - New repo: `cd /config && git init -b main`
   - Existing repo: `cd /config && git clone git@github.com:YOUR_USER/YOUR_REPO.git .`
3. Add a `.gitignore` (start with the add-on template entries): `homeassistant_gitops/rootfs/app/gitignore_example`
4. Commit and push:
   - `git add -A`
   - `git commit -m "Initial Home Assistant configuration"`
   - `git remote add origin git@github.com:YOUR_USER/YOUR_REPO.git`
   - `git push -u origin main`
5. Set the add-on `remote_url` and start using the UI for ongoing commits.

## Webhook

When `webhook_enabled` is true, POST to `/api/webhook/<webhook_path>` to trigger a pull.

## YAML Modules workflow

YAML Modules lets you keep configuration split across package modules and one-off files while
still supporting Home Assistant domain files. The UI exposes a single action: Sync modules.

Folder convention (hybrid):

```
/packages/wakeup/automation.yaml
/packages/wakeup/helpers.yaml
/packages/wakeup/template.yaml
/automations/dishwasher.yaml
/scripts/water_plants.yaml
/scenes/movie_time.yaml
/templates/hvac.yaml
/lovelace/living_room.yaml
```

Unassigned items created from the UI are stored in the one-off folder using the
`*.unassigned.yaml` pattern, example: `automations/automations.unassigned.yaml`.

Sync behavior:

- Module files can live in `/packages/<module>/` or per-domain folders (hybrid layout).
- Sync builds domain files like `automations.yaml`, `scripts.yaml`, and `scenes.yaml`.
- Sync updates module files when domain files change (UI edits).
- Missing automation or scene IDs are auto-injected; lovelace views use `path` if missing.
- Helper modules (`helpers.yaml`) are split into per-helper-type domain files.
- Lovelace YAML mode is supported via `ui-lovelace.yaml`.

Helper module files should use helper types as top-level keys, for example:

```
input_boolean:
  kitchen_motion:
    name: Kitchen motion
input_datetime:
  wakeup_time:
    name: Wakeup time
```

Lovelace module files can be either a list of views or a map with a `views` list plus metadata
keys (the first module with metadata becomes the base).

YAML Modules stores mapping and sync state under `/config/.gitops/`:

- `mappings/*.yaml` tracks which items belong to which module files.
- `sync-state.yaml` stores hashes used to detect changes.

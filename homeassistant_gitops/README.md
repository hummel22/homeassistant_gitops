# Home Assistant GitOps

Smarthome as Code initiative 

The Home Assistant GitOps Bridge add-on tracks configuration changes in `/config`, exposes an
ingress UI to stage/commit changes, and syncs with GitHub via SSH.


## Add-on options

| Option | Description | Default |
| --- | --- | --- |
| `remote_url` | SSH URL for the GitHub repository (e.g. `git@github.com:user/ha-config.git`). | `""` |
| `remote_branch` | Remote branch to sync. | `main` |
| `notification_enabled` | Enable persistent notifications. | `true` |
| `webhook_enabled` | Enable the webhook pull endpoint. | `false` |
| `webhook_path` | Path segment for the webhook. | `pull` |
| `poll_interval_minutes` | Periodic remote check interval in minutes. | `15` |
| `yaml_modules_enabled` | Enable YAML Modules sync across package and one-off YAML files. | `true` |
| `ui_theme` | UI theme preference (`light`, `dark`, or `system`). | `system` |

## Usage

1. Install the add-on and start it.
2. Open the ingress UI from the sidebar.
3. Configure `remote_url` and add the generated SSH public key to GitHub.
4. Use the UI to commit and push changes.
5. Enable the webhook and/or periodic checks if desired.

## GitOps config file

The add-on writes a GitOps config file into your repository at `/config/.gitops/config.yaml`.
It mirrors all add-on options so they can be tracked in Git and reviewed in pull requests.
If you edit `/config/.gitops/config.yaml`, restart the add-on to apply changes.
Commit this file along with the rest of your Home Assistant configuration.
Legacy `/config/.gitops.yaml` files are migrated into the new folder on startup.

## Manual Git setup

If you already manage `/config` with Git, the add-on will detect the existing repository and will not re-initialize or overwrite it. It will keep using your `.gitignore` and history.

To configure Git manually:

1. Create a GitHub repository (empty, no README or `.gitignore`).
2. From the Home Assistant host, initialize or clone into `/config`:
   - New repo: `cd /config && git init -b main`
   - Existing repo: `cd /config && git clone git@github.com:YOUR_USER/YOUR_REPO.git .`
3. Add a `.gitignore` (start with the add-on template entries): `addons/homeassistant_gitops/rootfs/app/gitignore_example`
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
still supporting Home Assistant domain files. The UI exposes a single action: **Sync modules**.

Definitions:

- Build: write domain YAML from module files.
- Update: write module files from domain YAML.
- Sync: runs build and update with conflict rules (assigned modules win, unassigned changes stay
  in unassigned files).
- Modules: Git ops pacakges, either found in /packages or one-offs found under domain folder ex: /automations/my_automation.yaml
- Domain files: top level files created by home assistant

### Folder convention (hybrid)

Package modules (cohesive bundles):

```
/packages/wakeup/automation.yaml
/packages/wakeup/helpers.yaml
/packages/wakeup/template.yaml
```

One-offs (single-domain files):

```
/automations/dishwasher.yaml
/scripts/water_plants.yaml
/scenes/movie_time.yaml
/templates/hvac.yaml
/lovelace/living_room.yaml
```

Unassigned items created from the UI are stored in the one-off folder using the
`*.unassigned.yaml` pattern, e.g. `automations/automations.unassigned.yaml`.

### Sync behavior

- Module files can live in `/packages/<module>/` or per-domain folders (hybrid layout).
- Sync builds domain files like `automations.yaml`, `scripts.yaml`, and `scenes.yaml`.
- Sync updates module files when domain files change (UI edits).
- Missing automation/scene IDs are auto-injected; lovelace views use `path` if missing.
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

### GitOps mappings

YAML Modules stores mapping and sync state under `/config/.gitops/`:

- `mappings/*.yaml` tracks which items belong to which module files.
- `sync-state.yaml` stores hashes used to detect changes.

See `addons/homeassistant_gitops/docs/feature-checklist.md` for planned enhancements.

## Development

Use `uv` to run the service and tests locally:

```
uv run --project addons/homeassistant_gitops python addons/homeassistant_gitops/rootfs/app/main.py
uv run --project addons/homeassistant_gitops --extra dev pytest addons/homeassistant_gitops/tests
```

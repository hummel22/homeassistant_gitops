from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from watchdog.observers import Observer

from . import (
    cli_installer,
    config_store,
    exports,
    groups,
    git_ops,
    gitignore_ops,
    ha_services,
    settings,
    ssh_ops,
    watchers,
    yaml_modules,
)
from .fs_utils import file_hash

OPTIONS = config_store.OPTIONS
tracker = watchers.create_tracker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    config_store.ensure_gitops_config()
    git_ops.ensure_repo(OPTIONS.remote_branch)
    git_ops.ensure_remote(OPTIONS.remote_url)
    ssh_ops.ensure_ssh_agent_key()
    watchers.set_tracker_loop(tracker, asyncio.get_running_loop())
    observer = Observer()
    handler = watchers.ConfigEventHandler(tracker)
    observer.schedule(handler, str(settings.CONFIG_DIR), recursive=True)
    observer.start()

    periodic_task = None
    if OPTIONS.poll_interval_minutes:
        periodic_task = asyncio.create_task(periodic_remote_check())

    try:
        yield
    finally:
        observer.stop()
        observer.join(timeout=5)
        if periodic_task:
            periodic_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await periodic_task


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(settings.STATIC_DIR / "index.html")


@app.get("/api/status")
async def api_status() -> JSONResponse:
    pending = await watchers.snapshot_pending(tracker)
    changes = git_ops.git_status()
    staged_count = sum(1 for change in changes if change["staged"])
    unstaged_count = sum(1 for change in changes if change["unstaged"])
    untracked_count = sum(1 for change in changes if change["untracked"])
    remote_status = git_ops.get_remote_status(OPTIONS.remote_url, OPTIONS.remote_branch, refresh=False)
    return JSONResponse(
        {
            "pending": pending,
            "changes": changes,
            "commits": git_ops.git_log(),
            "remote": OPTIONS.remote_url,
            "remote_status": remote_status,
            "branch": git_ops.current_branch(),
            "staged_count": staged_count,
            "unstaged_count": unstaged_count,
            "untracked_count": untracked_count,
            "dirty": bool(changes),
            "yaml_modules_enabled": OPTIONS.yaml_modules_enabled,
            "gitops_config_path": str(settings.GITOPS_CONFIG_PATH),
        }
    )


@app.get("/api/remote/status")
async def api_remote_status(refresh: bool = False) -> JSONResponse:
    return JSONResponse(git_ops.get_remote_status(OPTIONS.remote_url, OPTIONS.remote_branch, refresh=refresh))


@app.get("/api/config")
async def api_config() -> JSONResponse:
    return JSONResponse({"config": config_store.load_full_config(), "requires_restart": True})


@app.post("/api/config")
async def api_update_config(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        config_payload = dict(payload)
        if "git_user_name" in config_payload:
            git_ops.set_git_config_value("user.name", config_payload.pop("git_user_name"))
        if "git_user_email" in config_payload:
            git_ops.set_git_config_value("user.email", config_payload.pop("git_user_email"))
        if "merge_automations" in config_payload and "yaml_modules_enabled" not in config_payload:
            config_payload["yaml_modules_enabled"] = config_payload.pop("merge_automations")
        requires_restart = bool(config_payload)
        if config_payload:
            config_store.apply_config_update(config_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {
            "status": "updated",
            "config": config_store.load_full_config(),
            "requires_restart": requires_restart,
        }
    )


@app.post("/api/cli/install")
async def api_install_cli(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    overwrite = bool(payload.get("overwrite", False))
    try:
        return JSONResponse(cli_installer.install_cli(overwrite=overwrite))
    except cli_installer.CliInstallError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/branches")
async def api_branches() -> JSONResponse:
    return JSONResponse({"current": git_ops.current_branch(), "branches": git_ops.list_branches()})


@app.get("/api/commits")
async def api_commits(branch: str | None = None, limit: int = 50) -> JSONResponse:
    ref = branch or git_ops.current_branch()
    if branch and not git_ops.branch_exists(branch):
        raise HTTPException(status_code=404, detail="Branch not found")
    return JSONResponse({"branch": ref, "commits": git_ops.git_commits(ref, limit=limit)})


@app.get("/api/commit/files")
async def api_commit_files(sha: str) -> JSONResponse:
    if not git_ops.commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    changes = git_ops.git_commit_changes(sha)
    return JSONResponse({"sha": sha, "files": changes})


@app.get("/api/commit/diff")
async def api_commit_diff(sha: str, path: str, max_lines: int | None = None) -> JSONResponse:
    if not git_ops.commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    diff_data = git_ops.git_commit_diff(sha, path, max_lines=max_lines)
    return JSONResponse({"sha": sha, "path": path, **diff_data})


@app.get("/api/diff")
async def api_diff(
    path: str,
    mode: str = "unstaged",
    max_lines: int | None = None,
    untracked: bool = False,
) -> JSONResponse:
    mode = mode.lower()
    if mode not in {"unstaged", "staged", "all"}:
        raise HTTPException(status_code=400, detail="Invalid diff mode")
    diff_data = git_ops.git_diff(path, mode=mode, max_lines=max_lines, untracked=untracked)
    return JSONResponse({"path": path, "mode": mode, **diff_data})


@app.get("/api/git/files")
async def api_git_files(mode: str = "changed", include_ignored: bool = False) -> JSONResponse:
    try:
        files = git_ops.git_list_files(mode=mode, include_ignored=include_ignored)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"mode": mode, "files": files})


@app.get("/api/git/file")
async def api_git_file(path: str, ref: str = "head") -> JSONResponse:
    try:
        preview = git_ops.git_file_preview(path, ref=ref)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found in HEAD") from None
    return JSONResponse(preview)


@app.get("/api/gitignore/status")
async def api_gitignore_status(path: str) -> JSONResponse:
    try:
        status = git_ops.git_check_ignore(path)
        managed_entries = set(gitignore_ops.managed_block_entries())
        tracked = git_ops.git_is_tracked(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ignore_line = status.get("path")
    managed_ignore = ignore_line in managed_entries
    managed_override = f"!{ignore_line}" in managed_entries
    return JSONResponse(
        {
            "path": status.get("path", path),
            "ignored": bool(status.get("ignored", False)),
            "tracked": tracked,
            "managed": managed_ignore,
            "managed_override": managed_override,
            "source": status.get("source"),
            "pattern": status.get("pattern"),
        }
    )


@app.post("/api/gitignore/toggle")
async def api_gitignore_toggle(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    path = payload.get("path")
    action = (payload.get("action") or "toggle").lower()
    if action not in {"toggle", "ignore", "unignore"}:
        raise HTTPException(status_code=400, detail="Invalid action")
    try:
        status = git_ops.git_check_ignore(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if action == "toggle":
        action = "unignore" if status.get("ignored") else "ignore"

    changed = False
    message = ""
    if action == "ignore":
        changed = gitignore_ops.update_managed_block(status["path"], "ignore")
        message = "Added to .gitignore" if changed else "Already ignored in managed block"
    else:
        changed = gitignore_ops.update_managed_block(status["path"], "unignore")
        try:
            post_status = git_ops.git_check_ignore(status["path"])
        except ValueError:
            post_status = {"ignored": False}
        if post_status.get("ignored"):
            override_changed = gitignore_ops.update_managed_block(status["path"], "override")
            changed = changed or override_changed
            message = (
                "Added override to .gitignore"
                if override_changed
                else "Override already present in .gitignore"
            )
        else:
            message = "Removed from .gitignore" if changed else "No .gitignore update needed"

    try:
        final_status = git_ops.git_check_ignore(status["path"])
    except ValueError:
        final_status = {"ignored": False}

    return JSONResponse(
        {
            "path": status["path"],
            "ignored": bool(final_status.get("ignored", False)),
            "changed": changed,
            "message": message,
            "tracked": git_ops.git_is_tracked(status["path"]),
        }
    )


@app.post("/api/stage")
async def api_stage(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    files = payload.get("files") or []
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    git_ops.run_git(["add", "--", *files])
    return JSONResponse({"status": "staged", "files": files})


@app.post("/api/unstage")
async def api_unstage(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    files = payload.get("files") or []
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    git_ops.run_git(["reset", "HEAD", "--", *files])
    return JSONResponse({"status": "unstaged", "files": files})


@app.post("/api/commit")
async def api_commit(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    message = payload.get("message")
    files = payload.get("files") or []
    include_unstaged = bool(payload.get("include_unstaged", True))
    if not message:
        raise HTTPException(status_code=400, detail="Commit message required")
    if files:
        git_ops.run_git(["add", "--", *files])
    elif include_unstaged:
        git_ops.run_git(["add", "-A"])
    result = git_ops.run_git(["commit", "-m", message], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Commit failed")
    return JSONResponse({"status": "committed", "message": message})


@app.post("/api/reset")
async def api_reset(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    sha = payload.get("sha")
    confirm_dirty = bool(payload.get("confirm_dirty", False))
    stash_message = payload.get("message")
    if not sha:
        raise HTTPException(status_code=400, detail="Commit SHA required")
    if not git_ops.commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    dirty = not git_ops.working_tree_clean()
    stash_branch = None
    if dirty:
        if not confirm_dirty:
            raise HTTPException(
                status_code=409,
                detail="Working tree has uncommitted changes. Confirmation required.",
            )
        stash_branch = git_ops.create_gitops_stash_branch(stash_message)
    result = git_ops.run_git(["reset", "--hard", sha], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Reset failed")
    return JSONResponse(
        {"status": "reset", "sha": sha, "stash_branch": stash_branch, "dirty": dirty}
    )


@app.post("/api/push")
async def api_push() -> JSONResponse:
    git_ops.ensure_remote(OPTIONS.remote_url)
    if not OPTIONS.remote_url:
        raise HTTPException(status_code=400, detail="Remote URL is not configured")
    result = git_ops.run_git(["push", "origin", OPTIONS.remote_branch], check=False)
    if result.returncode == 0:
        return JSONResponse({"status": "pushed"})
    if "non-fast-forward" in result.stderr or "fetch first" in result.stderr:
        branch = f"ha-local-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        git_ops.run_git(["checkout", "-b", branch])
        git_ops.run_git(["push", "-u", "origin", branch])
        git_ops.run_git(["checkout", OPTIONS.remote_branch])
        await ha_services.notify(
            "HA Config Version Control",
            f"Remote has new commits. Your changes were pushed to {branch}.",
            "gitops-push-conflict",
        )
        return JSONResponse({"status": "pushed", "branch": branch})
    raise HTTPException(status_code=400, detail=result.stderr.strip() or "Push failed")


@app.post("/api/pull")
async def api_pull() -> JSONResponse:
    changes = await handle_pull()
    return JSONResponse({"status": "pulled", "changes": changes})


@app.post("/api/ssh/generate")
async def api_generate_key() -> JSONResponse:
    if not ssh_ops.get_ssh_status()["ssh_keygen_available"]:
        raise HTTPException(status_code=500, detail="ssh-keygen is not available in the add-on image")
    try:
        settings.SSH_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create {settings.SSH_DIR}: {exc.strerror or 'permission denied'}",
        ) from exc
    if not os.access(settings.SSH_DIR, os.W_OK):
        raise HTTPException(status_code=500, detail=f"SSH directory is not writable: {settings.SSH_DIR}")
    key_path = settings.SSH_DIR / "id_ed25519"
    if key_path.exists():
        raise HTTPException(status_code=400, detail="SSH key already exists")
    result = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Key generation failed")
    ssh_ops.ensure_ssh_agent_key()
    return JSONResponse(
        {"status": "generated", "public_key": key_path.with_suffix(".pub").read_text(encoding="utf-8")}
    )


@app.get("/api/ssh/status")
async def api_ssh_status() -> JSONResponse:
    return JSONResponse(ssh_ops.get_ssh_status())


@app.get("/api/ssh/public_key")
async def api_public_key() -> JSONResponse:
    key_path = settings.SSH_DIR / "id_ed25519.pub"
    if not key_path.exists():
        raise HTTPException(status_code=404, detail="No public key found")
    return JSONResponse({"public_key": key_path.read_text(encoding="utf-8")})


@app.post("/api/ssh/test")
async def api_ssh_test(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    data = payload or {}
    host = data.get("host") or "git@github.com"
    if not isinstance(host, str) or not host:
        raise HTTPException(status_code=400, detail="Host must be a string")
    status = ssh_ops.get_ssh_status()
    if not status["ssh_available"]:
        raise HTTPException(status_code=500, detail="ssh client is not available in the add-on image")
    if not status["private_key_exists"]:
        raise HTTPException(status_code=400, detail="SSH key not found")
    result = subprocess.run(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=8",
            host,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    normalized = output.lower()
    success = result.returncode == 0 or (
        result.returncode == 1 and "successfully authenticated" in normalized
    )
    message = "SSH authentication succeeded." if success else "SSH authentication failed."
    if "github" in normalized and "successfully authenticated" in normalized:
        message = "Authenticated with GitHub. GitHub does not provide shell access."
    return JSONResponse(
        {
            "status": "success" if success else "failed",
            "returncode": result.returncode,
            "message": message,
            "output": output,
            "host": host,
        }
    )


async def _wait_for_file_settle(
    path: Path,
    previous_hash: str,
    timeout_seconds: float = 20.0,
    poll_interval: float = 0.5,
) -> tuple[bool, str]:
    """Wait for a file hash to change and then stabilize."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last_hash = previous_hash
    changed = False
    while loop.time() < deadline:
        await asyncio.sleep(poll_interval)
        current_hash = file_hash(path)
        if current_hash != last_hash:
            last_hash = current_hash
            changed = True
            continue
        if changed:
            return True, current_hash
    return False, last_hash


async def _maybe_reconcile_automation_ids(
    sync_result: dict[str, Any],
) -> dict[str, Any]:
    """Reload automations and reconcile IDs if HA rewrites automations.yaml."""
    changed_files = sync_result.get("changed_files") or []
    if "automations.yaml" not in changed_files:
        return {
            "status": "skipped",
            "reason": "automations.yaml was not modified by sync.",
            "changed_files": [],
            "warnings": [],
            "reconciled_ids": [],
        }
    if not os.environ.get("SUPERVISOR_TOKEN"):
        return {
            "status": "skipped",
            "reason": "Supervisor token not available; cannot reload automations.",
            "changed_files": [],
            "warnings": [],
            "reconciled_ids": [],
        }

    automations_path = settings.CONFIG_DIR / "automations.yaml"
    if not automations_path.exists():
        return {
            "status": "skipped",
            "reason": "automations.yaml not found after sync.",
            "changed_files": [],
            "warnings": [],
            "reconciled_ids": [],
        }

    before_hash = file_hash(automations_path)
    await ha_services.call_service("automation", "reload")
    changed, _after_hash = await _wait_for_file_settle(automations_path, before_hash)
    if not changed:
        return {
            "status": "skipped",
            "reason": "Automation reload did not change automations.yaml.",
            "changed_files": [],
            "warnings": [],
            "reconciled_ids": [],
        }

    reconcile = yaml_modules.reconcile_automation_ids()
    reconcile_changed = reconcile.get("changed_files") or []
    if reconcile_changed:
        resync = yaml_modules.sync_yaml_modules()
        reconcile["warnings"] = reconcile.get("warnings", []) + resync.get("warnings", [])
        reconcile["changed_files"] = sorted(
            set(reconcile_changed) | set(resync.get("changed_files", []))
        )
    return reconcile


async def _sync_modules_with_reconcile() -> dict[str, Any]:
    """Sync YAML modules and optionally reconcile automation IDs."""
    result = yaml_modules.sync_yaml_modules()
    reconcile = await _maybe_reconcile_automation_ids(result)
    if reconcile.get("status") == "skipped" and not reconcile.get("warnings"):
        return result
    merged_files = sorted(
        set(result.get("changed_files", [])) | set(reconcile.get("changed_files", []))
    )
    merged_warnings = result.get("warnings", []) + reconcile.get("warnings", [])
    result["changed_files"] = merged_files
    result["warnings"] = merged_warnings
    result["reconcile_status"] = reconcile.get("status")
    result["reconcile_reason"] = reconcile.get("reason")
    result["reconciled_ids"] = reconcile.get("reconciled_ids", [])
    return result


@app.post("/api/modules/sync")
async def api_sync_modules() -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    result = await _sync_modules_with_reconcile()
    return JSONResponse(result)


@app.post("/api/modules/preview")
async def api_preview_modules() -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    result = yaml_modules.preview_yaml_modules()
    return JSONResponse(result)


@app.get("/api/modules/index")
async def api_modules_index() -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    return JSONResponse(yaml_modules.list_yaml_modules_index())


@app.get("/api/modules/file")
async def api_module_file(path: str) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    try:
        return JSONResponse(yaml_modules.read_module_file(path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/modules/items")
async def api_module_items(path: str) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    try:
        return JSONResponse(yaml_modules.list_module_items(path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/modules/item")
async def api_module_item(path: str, selector: str) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    try:
        selector_payload = json.loads(selector)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Selector must be valid JSON") from exc
    try:
        return JSONResponse(yaml_modules.read_module_item(path, selector_payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/modules/file")
async def api_save_module_file(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    path = payload.get("path")
    content = payload.get("content")
    if not isinstance(path, str) or not path:
        raise HTTPException(status_code=400, detail="Module path is required")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="Module content must be a string")
    try:
        return JSONResponse(yaml_modules.write_module_file(path, content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/modules/item")
async def api_save_module_item(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    path = payload.get("path")
    selector = payload.get("selector")
    content = payload.get("yaml")
    if not isinstance(path, str) or not path:
        raise HTTPException(status_code=400, detail="Module path is required")
    if not isinstance(selector, dict):
        raise HTTPException(status_code=400, detail="Selector must be an object")
    if not isinstance(content, str):
        raise HTTPException(status_code=400, detail="YAML content must be a string")
    try:
        return JSONResponse(yaml_modules.write_module_item(path, selector, content))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/modules/items/operate")
async def api_operate_module_items(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    operation = payload.get("operation")
    items = payload.get("items")
    move_target = payload.get("move_target")
    if not isinstance(operation, str) or not operation:
        raise HTTPException(status_code=400, detail="Operation is required")
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="Items must be a non-empty list")
    try:
        return JSONResponse(yaml_modules.operate_module_items(operation, items, move_target))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/api/modules/file")
async def api_delete_module_file(path: str) -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    try:
        return JSONResponse(yaml_modules.delete_module_file(path))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/exports/config")
async def api_exports_config() -> JSONResponse:
    try:
        return JSONResponse({"config": exports.load_exports_config()})
    except exports.ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/exports/config")
async def api_save_exports_config(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        config = exports.save_exports_config(payload)
    except exports.ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse({"status": "saved", "config": config})


@app.get("/api/exports/file/{kind}")
async def api_export_file(kind: str) -> JSONResponse:
    try:
        return JSONResponse(exports.read_export_file(kind))
    except exports.ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/exports/run/{kind}")
async def api_run_export(kind: str) -> JSONResponse:
    try:
        result = await exports.run_export(kind)
    except exports.ExportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return JSONResponse(result)


@app.get("/api/groups")
async def api_groups() -> JSONResponse:
    try:
        payload = groups.list_groups()
        payload["unmanaged"] = await groups.list_unmanaged_groups()
        return JSONResponse(payload)
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/groups")
async def api_upsert_group(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        object_id = payload.get("object_id")
        if isinstance(object_id, str) and object_id.strip():
            await groups.assert_no_unmanaged_group_collision(object_id)
        return JSONResponse(groups.upsert_group(payload))
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.delete("/api/groups/{object_id}")
async def api_delete_group(object_id: str) -> JSONResponse:
    try:
        return JSONResponse(groups.delete_group(object_id))
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/groups/import")
async def api_import_group(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(await groups.import_group(payload))
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/groups/ignore")
async def api_groups_ignore(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        return JSONResponse(groups.set_group_ignored(payload))
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/api/groups/restart_status")
async def api_groups_restart_status() -> JSONResponse:
    try:
        return JSONResponse(groups.restart_status())
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/groups/restart_ack")
async def api_groups_restart_ack() -> JSONResponse:
    try:
        return JSONResponse(groups.ack_restart())
    except groups.GroupsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/automation/merge")
async def api_merge_automations() -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    result = await _sync_modules_with_reconcile()
    return JSONResponse(result)


@app.post("/api/automation/sync")
async def api_sync_automations() -> JSONResponse:
    if not OPTIONS.yaml_modules_enabled:
        raise HTTPException(status_code=400, detail="YAML Modules sync is disabled")
    result = await _sync_modules_with_reconcile()
    return JSONResponse(result)


@app.post("/api/webhook/{path}")
async def api_webhook(path: str) -> JSONResponse:
    if not OPTIONS.webhook_enabled or path != OPTIONS.webhook_path:
        raise HTTPException(status_code=404, detail="Webhook not enabled")
    changes = await handle_pull()
    return JSONResponse({"status": "pulled", "changes": changes})


async def handle_pull() -> list[str]:
    git_ops.ensure_remote(OPTIONS.remote_url)
    if not OPTIONS.remote_url:
        raise HTTPException(status_code=400, detail="Remote URL is not configured")
    if not git_ops.working_tree_clean():
        await ha_services.notify(
            "HA Config Version Control",
            "Remote updates are available, but there are local uncommitted changes.",
            "gitops-pull-blocked",
        )
        raise HTTPException(status_code=409, detail="Working tree is dirty")
    git_ops.run_git(["fetch", "origin", OPTIONS.remote_branch])
    result = git_ops.run_git(["pull", "--ff-only", "origin", OPTIONS.remote_branch], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Pull failed")
    pull_output = f"{result.stdout}\n{result.stderr}".lower()
    if "already up to date" in pull_output:
        return []
    previous_head = git_ops.run_git(["rev-parse", "HEAD@{1}"], check=False)
    if previous_head.returncode != 0:
        return []
    changed_files = git_ops.run_git(
        ["diff", "--name-only", previous_head.stdout.strip(), "HEAD"], check=False
    ).stdout.splitlines()
    if OPTIONS.yaml_modules_enabled and yaml_modules.should_sync_yaml_modules(changed_files):
        sync_result = yaml_modules.sync_yaml_modules()
        changed_files.extend(sync_result.get("changed_files", []))
    domains = yaml_modules.list_changed_domains(changed_files)
    reloadable = {
        "automation",
        "script",
        "scene",
        "template",
        "input_boolean",
        "input_button",
        "input_datetime",
        "input_number",
        "input_select",
        "input_text",
        "counter",
        "timer",
        "schedule",
    }
    for domain in sorted(domains):
        if domain not in reloadable:
            continue
        await ha_services.call_service(domain, "reload")
    if (domains - reloadable) and changed_files:
        await ha_services.notify(
            "HA Config Version Control",
            "Configuration changes pulled. Some updates require a Home Assistant restart.",
            "gitops-restart-needed",
        )
    elif not domains and changed_files:
        await ha_services.notify(
            "HA Config Version Control",
            "Configuration changes pulled. A Home Assistant restart may be required.",
            "gitops-restart-needed",
        )
    return changed_files


async def periodic_remote_check() -> None:
    while True:
        interval = OPTIONS.poll_interval_minutes or 0
        await asyncio.sleep(interval * 60)
        if not OPTIONS.remote_url:
            continue
        git_ops.ensure_remote(OPTIONS.remote_url)
        git_ops.run_git(["fetch", "origin", OPTIONS.remote_branch], check=False)
        behind = git_ops.run_git(
            ["rev-list", "--count", f"HEAD..origin/{OPTIONS.remote_branch}"]
        ).stdout.strip()
        if behind and int(behind) > 0:
            if git_ops.working_tree_clean():
                await handle_pull()
            else:
                await ha_services.notify(
                    "HA Config Version Control",
                    "Remote updates are available but local changes are uncommitted.",
                    "gitops-periodic-behind",
                )

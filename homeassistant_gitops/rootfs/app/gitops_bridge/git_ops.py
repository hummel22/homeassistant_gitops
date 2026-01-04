from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import HTTPException

from . import settings
from .gitignore_ops import ensure_gitignore


def run_git(args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=settings.CONFIG_DIR,
        text=True,
        capture_output=True,
        check=check,
    )


def get_origin_url() -> str | None:
    try:
        result = run_git(["remote", "get-url", "origin"], check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def get_git_config_value(key: str) -> str | None:
    result = run_git(["config", "--local", "--get", key], check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def set_git_config_value(key: str, value: str | None) -> None:
    if value is None or str(value).strip() == "":
        run_git(["config", "--local", "--unset", key], check=False)
        return
    run_git(["config", "--local", key, str(value).strip()], check=False)


def ensure_repo(remote_branch: str) -> None:
    if (settings.CONFIG_DIR / ".git").exists():
        return
    ensure_gitignore()
    init_result = run_git(["init", "-b", remote_branch], check=False)
    if init_result.returncode != 0:
        run_git(["init"])
        run_git(["branch", "-M", remote_branch])
    run_git(["add", "-A"])
    run_git(["commit", "-m", "Initial Home Assistant configuration"], check=False)


def ensure_remote(remote_url: str | None) -> None:
    if not remote_url:
        return
    result = run_git(["remote"], check=False)
    remotes = {line.strip() for line in result.stdout.splitlines()}
    if "origin" not in remotes:
        run_git(["remote", "add", "origin", remote_url])
    else:
        run_git(["remote", "set-url", "origin", remote_url])


def working_tree_clean() -> bool:
    result = run_git(["status", "--porcelain"], check=False)
    return result.stdout.strip() == ""


def current_branch() -> str:
    result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = result.stdout.strip()
    return branch or "HEAD"


def branch_exists(name: str) -> bool:
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{name}"], check=False)
    return result.returncode == 0


def commit_exists(sha: str) -> bool:
    result = run_git(["cat-file", "-e", f"{sha}^{{commit}}"], check=False)
    return result.returncode == 0


def list_branches() -> list[str]:
    result = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], check=False)
    branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return sorted(branches)


def get_remote_status(remote_url: str | None, remote_branch: str, refresh: bool = False) -> dict[str, Any]:
    if not remote_url:
        return {"configured": False, "ahead": 0, "behind": 0, "branch": remote_branch}
    ensure_remote(remote_url)
    if refresh:
        run_git(["fetch", "origin", remote_branch], check=False)
    remote_ref = f"origin/{remote_branch}"
    remote_exists = run_git(["rev-parse", "--verify", remote_ref], check=False).returncode == 0
    if not remote_exists:
        return {
            "configured": True,
            "ahead": 0,
            "behind": 0,
            "branch": remote_branch,
            "error": f"Remote branch {remote_ref} not found",
        }
    result = run_git(["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"], check=False)
    ahead = behind = 0
    if result.returncode == 0 and result.stdout.strip():
        left, right = result.stdout.strip().split()
        ahead = int(left)
        behind = int(right)
    return {"configured": True, "ahead": ahead, "behind": behind, "branch": remote_branch}


def git_status() -> list[dict[str, Any]]:
    result = run_git(["status", "--porcelain=v1", "-z"], check=False)
    changes: list[dict[str, Any]] = []
    if result.returncode != 0:
        return changes
    entries = result.stdout.split("\0")
    idx = 0
    while idx < len(entries):
        entry = entries[idx]
        if not entry:
            idx += 1
            continue
        status = entry[:2]
        path = entry[3:] if len(entry) > 3 else ""
        rename_from = None
        if status[0] in {"R", "C"}:
            rename_from = path
            idx += 1
            if idx >= len(entries):
                break
            path = entries[idx]
        staged = status[0] not in {" ", "?"}
        unstaged = status[1] not in {" ", "?"}
        untracked = status == "??"
        changes.append(
            {
                "status": status,
                "path": path,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "rename_from": rename_from,
            }
        )
        idx += 1
    return changes


def git_log(limit: int = 20) -> list[dict[str, str]]:
    result = run_git(
        [
            "--no-pager",
            "log",
            f"-n{limit}",
            "--pretty=format:%H%x09%h%x09%an%x09%ad%x09%s",
            "--date=short",
        ],
        check=False,
    )
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) == 5:
            entries.append(
                {
                    "sha_full": parts[0],
                    "sha": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
    return entries


def git_commits(ref: str, limit: int = 50) -> list[dict[str, str]]:
    result = run_git(
        [
            "--no-pager",
            "log",
            ref,
            f"-n{limit}",
            "--pretty=format:%H%x09%h%x09%an%x09%ad%x09%s",
            "--date=short",
        ],
        check=False,
    )
    entries: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) == 5:
            entries.append(
                {
                    "sha_full": parts[0],
                    "sha": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
    return entries


def _truncate_diff(diff: str, max_lines: int | None) -> tuple[str, bool, int]:
    total_lines = diff.count("\n")
    if max_lines is None or max_lines <= 0:
        return diff, False, total_lines
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff, False, len(lines)
    truncated = "\n".join(lines[:max_lines]) + "\n"
    return truncated, True, len(lines)


def git_diff(
    path: str,
    mode: str = "unstaged",
    max_lines: int | None = None,
    untracked: bool = False,
) -> dict[str, Any]:
    if untracked and mode in {"unstaged", "all"}:
        result = run_git(["--no-pager", "diff", "--no-index", "--", "/dev/null", path], check=False)
    elif mode == "staged":
        result = run_git(["--no-pager", "diff", "--cached", "--", path], check=False)
    elif mode == "all":
        result = run_git(["--no-pager", "diff", "HEAD", "--", path], check=False)
    else:
        result = run_git(["--no-pager", "diff", "--", path], check=False)
    diff = result.stdout
    truncated, is_truncated, total_lines = _truncate_diff(diff, max_lines)
    return {"diff": truncated, "truncated": is_truncated, "total_lines": total_lines}


def git_commit_changes(sha: str) -> list[dict[str, Any]]:
    result = run_git(["diff-tree", "--no-commit-id", "--name-status", "-r", sha], check=False)
    if result.returncode != 0:
        return []
    changes: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                changes.append({"status": status, "path": parts[2], "rename_from": parts[1]})
            continue
        if len(parts) >= 2:
            changes.append({"status": status, "path": parts[1], "rename_from": None})
    return changes


def git_commit_diff(sha: str, path: str, max_lines: int | None = None) -> dict[str, Any]:
    result = run_git(["--no-pager", "show", sha, "--pretty=format:", "--", path], check=False)
    diff = result.stdout
    truncated, is_truncated, total_lines = _truncate_diff(diff, max_lines)
    return {"diff": truncated, "truncated": is_truncated, "total_lines": total_lines}


def create_gitops_stash_branch(message: str | None = None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base_name = f"gitops-stash-{timestamp}"
    branch_name = base_name
    counter = 1
    while branch_exists(branch_name):
        branch_name = f"{base_name}-{counter}"
        counter += 1
    original_branch = current_branch()
    original_sha = run_git(["rev-parse", "HEAD"], check=False).stdout.strip()
    checkout_result = run_git(["checkout", "-b", branch_name], check=False)
    if checkout_result.returncode != 0:
        raise HTTPException(
            status_code=400, detail=checkout_result.stderr.strip() or "Failed to create stash branch"
        )
    run_git(["add", "-A"], check=False)
    commit_message = message or f"GitOps stash before reset {timestamp} UTC"
    commit_result = run_git(["commit", "-m", commit_message], check=False)
    if original_branch == "HEAD":
        return_result = run_git(["checkout", "--detach", original_sha], check=False)
    else:
        return_result = run_git(["checkout", original_branch], check=False)
    if commit_result.returncode != 0:
        raise HTTPException(
            status_code=400, detail=commit_result.stderr.strip() or "Failed to commit stash branch"
        )
    if return_result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=return_result.stderr.strip() or "Failed to return to original branch",
        )
    return branch_name

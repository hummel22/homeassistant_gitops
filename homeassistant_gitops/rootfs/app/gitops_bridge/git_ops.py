from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException

from . import settings
from .gitignore_ops import ensure_gitignore

MAX_FILE_PREVIEW_BYTES = 512 * 1024


def run_git(args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=settings.CONFIG_DIR,
        text=True,
        capture_output=True,
        check=check,
    )


def run_git_bytes(args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=settings.CONFIG_DIR,
        text=False,
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


def normalize_repo_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError("Path required")
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Invalid path")
    resolved = (settings.CONFIG_DIR / candidate).resolve()
    config_root = settings.CONFIG_DIR.resolve()
    if not resolved.is_relative_to(config_root):
        raise ValueError("Invalid path")
    return resolved.relative_to(config_root).as_posix()


def _parse_status_entries(output: str) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    entries = output.split("\0")
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
        is_dir = False
        if path.endswith("/"):
            is_dir = True
            path = path.rstrip("/")
        ignored = status == "!!"
        untracked = status == "??"
        staged = False
        unstaged = False
        if not ignored and not untracked:
            staged = status[0] not in {" ", "?"}
            unstaged = status[1] not in {" ", "?"}
        changes.append(
            {
                "status": status,
                "path": path,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "ignored": ignored,
                "is_dir": is_dir,
                "rename_from": rename_from,
            }
        )
        idx += 1
    return changes


def git_status_entries(include_ignored: bool = False) -> list[dict[str, Any]]:
    args = ["status", "--porcelain=v1", "-z"]
    if include_ignored:
        args.append("--ignored")
    result = run_git(args, check=False)
    if result.returncode != 0:
        return []
    return _parse_status_entries(result.stdout)


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
    return git_status_entries(include_ignored=False)


def git_list_files(mode: str = "changed", include_ignored: bool = False) -> list[dict[str, Any]]:
    mode = (mode or "changed").lower()
    if mode not in {"changed", "all"}:
        raise ValueError("Invalid file list mode")

    if mode == "changed":
        changes = git_status_entries(include_ignored=include_ignored)
        files = []
        for change in changes:
            if change["ignored"] and not include_ignored:
                continue
            clean = not (
                change["staged"]
                or change["unstaged"]
                or change["untracked"]
                or change["ignored"]
            )
            files.append({**change, "clean": clean})
        return files

    tracked_result = run_git(["ls-files", "-z"], check=False)
    tracked = [entry for entry in tracked_result.stdout.split("\0") if entry]
    files: dict[str, dict[str, Any]] = {}
    for path in tracked:
        files[path] = {
            "status": "  ",
            "path": path,
            "staged": False,
            "unstaged": False,
            "untracked": False,
            "ignored": False,
            "is_dir": False,
            "rename_from": None,
            "clean": True,
        }

    for change in git_status_entries(include_ignored=include_ignored):
        if change["ignored"] and not include_ignored:
            continue
        entry = files.get(change["path"])
        if not entry:
            entry = {
                "status": change["status"],
                "path": change["path"],
                "staged": False,
                "unstaged": False,
                "untracked": False,
                "ignored": False,
                "is_dir": change.get("is_dir", False),
                "rename_from": None,
                "clean": True,
            }
            files[change["path"]] = entry
        entry["status"] = change["status"]
        entry["staged"] = bool(change["staged"])
        entry["unstaged"] = bool(change["unstaged"])
        entry["untracked"] = bool(change["untracked"])
        entry["ignored"] = bool(change["ignored"])
        entry["is_dir"] = bool(change.get("is_dir", False))
        entry["rename_from"] = change.get("rename_from")
        entry["clean"] = not (
            entry["staged"] or entry["unstaged"] or entry["untracked"] or entry["ignored"]
        )

    return [files[path] for path in sorted(files)]


def git_check_ignore(path: str) -> dict[str, Any]:
    rel_path = normalize_repo_path(path)
    result = run_git(["check-ignore", "-v", "--", rel_path], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return {"path": rel_path, "ignored": False}
    line = result.stdout.strip().splitlines()[0]
    source = ""
    pattern = ""
    line_number = None
    if "\t" in line:
        source_block, match_path = line.split("\t", 1)
    else:
        source_block, match_path = line, rel_path
    if source_block.count(":") >= 2:
        source, line_part, pattern = source_block.split(":", 2)
        if line_part.isdigit():
            line_number = int(line_part)
    return {
        "path": rel_path,
        "ignored": True,
        "source": source,
        "line": line_number,
        "pattern": pattern,
        "match": match_path,
    }


def git_is_tracked(path: str) -> bool:
    rel_path = normalize_repo_path(path)
    result = run_git(["ls-files", "--error-unmatch", "--", rel_path], check=False)
    return result.returncode == 0


def _read_worktree_bytes(path: Path) -> tuple[bytes, int]:
    size_bytes = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_PREVIEW_BYTES + 1)
    return data, size_bytes


def _read_head_bytes(rel_path: str) -> tuple[bytes, int]:
    result = run_git_bytes(["show", f"HEAD:{rel_path}"], check=False)
    if result.returncode != 0:
        raise FileNotFoundError(rel_path)
    data = result.stdout or b""
    return data, len(data)


def git_file_preview(path: str, ref: str = "worktree") -> dict[str, Any]:
    rel_path = normalize_repo_path(path)
    ref = (ref or "worktree").lower()
    if ref not in {"worktree", "head"}:
        raise ValueError("Invalid ref")
    if ref == "head":
        data, size_bytes = _read_head_bytes(rel_path)
    else:
        worktree_path = settings.CONFIG_DIR / rel_path
        if not worktree_path.exists():
            raise FileNotFoundError(rel_path)
        data, size_bytes = _read_worktree_bytes(worktree_path)
    truncated = len(data) > MAX_FILE_PREVIEW_BYTES
    if truncated:
        data = data[:MAX_FILE_PREVIEW_BYTES]
    is_binary = b"\0" in data
    content = ""
    if not is_binary:
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            is_binary = True
            content = ""
    return {
        "path": rel_path,
        "ref": ref,
        "is_binary": is_binary,
        "truncated": truncated,
        "size_bytes": size_bytes,
        "content": content,
    }


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

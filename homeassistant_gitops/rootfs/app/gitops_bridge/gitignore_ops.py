from __future__ import annotations

import fnmatch
from pathlib import Path

from . import settings

GITIGNORE_CACHE: tuple[float, list[tuple[bool, str, bool, bool, bool]]] | None = None
MANAGED_START = "# BEGIN GitOps Bridge managed"
MANAGED_END = "# END GitOps Bridge managed"


def load_gitignore_template() -> list[str]:
    if not settings.GITIGNORE_TEMPLATE.exists():
        return []
    lines = [
        line.strip()
        for line in settings.GITIGNORE_TEMPLATE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return lines


def load_gitignore_patterns() -> list[tuple[bool, str, bool, bool, bool]]:
    gitignore_path = settings.CONFIG_DIR / ".gitignore"
    if not gitignore_path.exists():
        return []
    patterns: list[tuple[bool, str, bool, bool, bool]] = []
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        negated = entry.startswith("!")
        if negated:
            entry = entry[1:].strip()
            if not entry:
                continue
        is_dir = entry.endswith("/")
        pattern = entry.rstrip("/") if is_dir else entry
        is_glob = any(char in pattern for char in "*?[]")
        is_path = "/" in pattern
        patterns.append((negated, pattern, is_dir, is_path, is_glob))
    return patterns


def get_gitignore_patterns() -> list[tuple[bool, str, bool, bool, bool]]:
    global GITIGNORE_CACHE
    gitignore_path = settings.CONFIG_DIR / ".gitignore"
    try:
        mtime = gitignore_path.stat().st_mtime
    except FileNotFoundError:
        return []
    if GITIGNORE_CACHE and GITIGNORE_CACHE[0] == mtime:
        return GITIGNORE_CACHE[1]
    patterns = load_gitignore_patterns()
    GITIGNORE_CACHE = (mtime, patterns)
    return patterns


def ensure_gitignore() -> None:
    gitignore_path = settings.CONFIG_DIR / ".gitignore"
    template_lines = load_gitignore_template()
    existing = set()
    if gitignore_path.exists():
        existing = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}
    new_lines = [entry for entry in template_lines if entry not in existing]
    if not existing:
        if not template_lines:
            return
        content = "\n".join(template_lines) + "\n"
        gitignore_path.write_text(content, encoding="utf-8")
        return
    if new_lines:
        with gitignore_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(new_lines) + "\n")


def load_gitignore_lines() -> list[str]:
    gitignore_path = settings.CONFIG_DIR / ".gitignore"
    if not gitignore_path.exists():
        return []
    return gitignore_path.read_text(encoding="utf-8").splitlines()


def save_gitignore_lines(lines: list[str]) -> None:
    gitignore_path = settings.CONFIG_DIR / ".gitignore"
    if not lines:
        gitignore_path.write_text("", encoding="utf-8")
        return
    content = "\n".join(lines).rstrip("\n") + "\n"
    gitignore_path.write_text(content, encoding="utf-8")


def ensure_managed_block(lines: list[str]) -> tuple[list[str], int, int]:
    start = None
    end = None
    for idx, line in enumerate(lines):
        if line.strip() == MANAGED_START and start is None:
            start = idx
            continue
        if line.strip() == MANAGED_END and start is not None:
            end = idx
            break
    if start is None or end is None or end < start:
        if lines and lines[-1].strip():
            lines.append("")
        start = len(lines)
        lines.append(MANAGED_START)
        lines.append(MANAGED_END)
        end = start + 1
    return lines, start, end


def update_managed_block(path: str, action: str) -> bool:
    lines = load_gitignore_lines()
    lines, start, end = ensure_managed_block(lines)
    block = [line.strip() for line in lines[start + 1 : end] if line.strip()]
    action = action.lower()
    updated = list(block)
    if action == "ignore":
        updated = [line for line in updated if line != f"!{path}" and line != path]
        updated.append(path)
    elif action == "unignore":
        updated = [line for line in updated if line != path]
    elif action == "override":
        updated = [line for line in updated if line != path]
        if f"!{path}" not in updated:
            updated.append(f"!{path}")
    else:
        raise ValueError("Invalid gitignore action")

    if updated == block:
        return False
    lines[start + 1 : end] = updated
    save_gitignore_lines(lines)
    return True


def managed_block_entries() -> list[str]:
    lines = load_gitignore_lines()
    if not lines:
        return []
    lines, start, end = ensure_managed_block(lines)
    return [line.strip() for line in lines[start + 1 : end] if line.strip()]


def should_ignore(path: Path) -> bool:
    rel = path.as_posix()
    ignored = False
    for negated, pattern, is_dir, is_path, is_glob in get_gitignore_patterns():
        matched = False
        if is_dir:
            matched = pattern in path.parts
        elif is_glob:
            matched = fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)
        elif is_path:
            matched = rel == pattern
        else:
            matched = path.name == pattern
        if matched:
            ignored = not negated
    if ignored:
        return True
    if path.suffix.lower() not in settings.WATCH_EXTENSIONS:
        return True
    return False

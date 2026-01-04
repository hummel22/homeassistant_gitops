from __future__ import annotations

import fnmatch
from pathlib import Path

from . import settings

GITIGNORE_CACHE: tuple[float, list[tuple[bool, str, bool, bool, bool]]] | None = None


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

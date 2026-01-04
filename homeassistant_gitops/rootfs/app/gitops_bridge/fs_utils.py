from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import settings
from .yaml_tags import GitopsYamlDumper, GitopsYamlLoader


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hash_text(read_text(path))


def modules_hash(paths: Iterable[Path]) -> str:
    hasher = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        rel: Path | str = path
        try:
            rel = path.relative_to(settings.CONFIG_DIR)
        except ValueError:
            pass
        hasher.update(str(rel).encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(read_text(path).encode("utf-8"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def yaml_load(path: Path) -> tuple[Any, list[int] | None, str | None]:
    text = read_text(path)
    if not text.strip():
        return None, None, None
    try:
        data = yaml.load(text, Loader=GitopsYamlLoader)
    except yaml.YAMLError as exc:
        return None, None, f"{path.relative_to(settings.CONFIG_DIR)}: {exc}"
    lines = None
    if isinstance(data, list):
        try:
            node = yaml.compose(text)
        except yaml.YAMLError:
            node = None
        if isinstance(node, yaml.SequenceNode):
            lines = [child.start_mark.line + 1 for child in node.value]
    return data, lines, None


def yaml_dump(data: Any) -> str:
    if data is None:
        return ""
    rendered = yaml.dump(
        data,
        Dumper=GitopsYamlDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    return rendered.rstrip() + "\n"


def write_yaml_if_changed(path: Path, data: Any) -> bool:
    rendered = yaml_dump(data)
    if rendered == read_text(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True

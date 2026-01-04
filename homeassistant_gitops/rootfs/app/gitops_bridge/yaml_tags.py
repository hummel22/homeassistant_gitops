from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class TaggedValue:
    """Represents a YAML node with an explicit tag (e.g. `!include`, `!secret`, `!/path`)."""

    tag: str
    value: Any
    line: int | None = None


class GitopsYamlLoader(yaml.SafeLoader):
    """Safe YAML loader that preserves `!` tags as TaggedValue objects."""


class GitopsYamlDumper(yaml.SafeDumper):
    """Safe YAML dumper that can emit TaggedValue objects."""


def _construct_tagged(loader: GitopsYamlLoader, suffix: str, node: yaml.Node) -> TaggedValue:
    tag = f"!{suffix}"
    line = node.start_mark.line + 1 if getattr(node, "start_mark", None) else None
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node)
    else:
        value = loader.construct_object(node)
    return TaggedValue(tag=tag, value=value, line=line)


def _represent_tagged(dumper: GitopsYamlDumper, data: TaggedValue) -> yaml.Node:
    value = data.value
    if isinstance(value, dict):
        return dumper.represent_mapping(data.tag, value)
    if isinstance(value, list):
        return dumper.represent_sequence(data.tag, value)
    rendered = "" if value is None else str(value)
    return dumper.represent_scalar(data.tag, rendered)


GitopsYamlLoader.add_multi_constructor("!", _construct_tagged)
GitopsYamlDumper.add_representer(TaggedValue, _represent_tagged)


HA_INCLUDE_TAGS = {
    "!include",
    "!include_dir_list",
    "!include_dir_merge_list",
    "!include_dir_named",
    "!include_dir_merge_named",
}

SKIP = object()


def _has_glob(pattern: str) -> bool:
    return any(char in pattern for char in "*?[]")


def _is_template_pattern(pattern: str) -> bool:
    lowered = pattern.lower()
    return lowered.endswith(".template.yaml") or lowered.endswith(".template.yml")


def is_template_tag(tag: str) -> bool:
    if not tag.startswith("!"):
        return False
    suffix = tag[1:].lstrip("/")
    return bool(suffix) and _is_template_pattern(suffix)


def _normalize_config_relative(path: str) -> str:
    candidate = path.strip().lstrip("/")
    if not candidate:
        raise ValueError("Include path is empty.")
    parts = Path(candidate).parts
    if ".." in parts:
        raise ValueError("Include path cannot include parent directory segments.")
    return candidate


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            merged[key] = list(merged[key]) + list(value)
            continue
        merged[key] = value
    return merged


def resolve_template_candidates(
    tag: str,
    *,
    config_dir: Path,
    base_path: Path,
    warnings: list[str],
) -> list[Path]:
    """Resolve a template tag into the list of matching template files."""

    if not is_template_tag(tag):
        return []
    try:
        pattern = _normalize_config_relative(tag[1:])
    except ValueError as exc:
        warnings.append(f"Invalid template include path {tag} in {base_path.as_posix()}: {exc}")
        return []
    if not _is_template_pattern(pattern):
        warnings.append(
            f"Template include must reference *.template.yaml: {tag} in {base_path.as_posix()}"
        )
        return []

    if _has_glob(pattern):
        candidates = [
            match
            for match in sorted(config_dir.glob(pattern))
            if match.is_file() and _is_template_pattern(match.name)
        ]
        return candidates

    match = (config_dir / pattern).resolve()
    try:
        match.relative_to(config_dir)
    except ValueError:
        warnings.append(
            f"Template include must stay within config dir: {tag} in {base_path.as_posix()}"
        )
        return []

    if match.exists() and match.is_file():
        return [match]
    return []


def _load_yaml_file(path: Path, warnings: list[str]) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        warnings.append(f"Missing include file: {path.as_posix()}")
        return SKIP
    if not text.strip():
        return None
    try:
        return yaml.load(text, Loader=GitopsYamlLoader)
    except yaml.YAMLError as exc:
        warnings.append(f"Invalid YAML in {path.as_posix()}: {exc}")
        return SKIP


def expand_includes(
    value: Any,
    *,
    config_dir: Path,
    base_path: Path,
    warnings: list[str],
    resolve_templates: bool,
    resolve_ha_includes: bool,
    _depth: int = 0,
) -> Any:
    """Expand template tags and optional HA include tags into plain YAML data.

    Notes:
    - Template tags are encoded as a YAML tag containing a config-relative path or glob, e.g.:
      `!/packages/common.template.yaml` or `!packages/common.template.yaml`.
    - HA include tags are `!include*` tags with scalar string values.
    - Unknown tags are preserved as TaggedValue, with nested values expanded where applicable.
    """

    if _depth > 20:
        warnings.append(f"Include expansion exceeded max depth at {base_path.as_posix()}.")
        return value

    if value is SKIP:
        return SKIP

    if isinstance(value, TaggedValue):
        if resolve_templates and is_template_tag(value.tag):
            candidates = resolve_template_candidates(
                value.tag,
                config_dir=config_dir,
                base_path=base_path,
                warnings=warnings,
            )
            if not candidates:
                warnings.append(
                    f"Template include did not match any files: {value.tag} in {base_path.as_posix()}"
                )
                return SKIP
            expanded: list[Any] = []
            for candidate in candidates:
                loaded = _load_yaml_file(candidate, warnings)
                expanded_child = expand_includes(
                    loaded,
                    config_dir=config_dir,
                    base_path=candidate,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=resolve_ha_includes,
                    _depth=_depth + 1,
                )
                if expanded_child is SKIP:
                    return SKIP
                expanded.append(expanded_child)
            if len(expanded) == 1:
                return expanded[0]
            if all(isinstance(entry, list) for entry in expanded):
                merged_list: list[Any] = []
                for entry in expanded:
                    merged_list.extend(entry or [])
                return merged_list
            if all(isinstance(entry, dict) for entry in expanded):
                merged_map: dict[str, Any] = {}
                for entry in expanded:
                    merged_map = _deep_merge(merged_map, entry or {})
                return merged_map
            warnings.append(
                f"Template glob include produced mixed shapes; skipping: {value.tag} in {base_path.as_posix()}"
            )
            return SKIP

        if resolve_ha_includes and value.tag in HA_INCLUDE_TAGS:
            include_arg = value.value
            if not isinstance(include_arg, str) or not include_arg.strip():
                warnings.append(f"{value.tag} must be a non-empty string in {base_path.as_posix()}")
                return SKIP
            include_path = (base_path.parent / include_arg).resolve()
            try:
                include_path.relative_to(config_dir)
            except ValueError:
                warnings.append(f"{value.tag} must stay within config dir in {base_path.as_posix()}")
                return SKIP

            if value.tag == "!include":
                loaded = _load_yaml_file(include_path, warnings)
                return expand_includes(
                    loaded,
                    config_dir=config_dir,
                    base_path=include_path,
                    warnings=warnings,
                    resolve_templates=resolve_templates,
                    resolve_ha_includes=resolve_ha_includes,
                    _depth=_depth + 1,
                )

            if value.tag == "!include_dir_list":
                if not include_path.exists() or not include_path.is_dir():
                    warnings.append(f"{value.tag} directory not found: {include_arg}")
                    return []
                items: list[Any] = []
                for child in sorted(include_path.glob("*.y*ml")):
                    loaded = _load_yaml_file(child, warnings)
                    expanded_child = expand_includes(
                        loaded,
                        config_dir=config_dir,
                        base_path=child,
                        warnings=warnings,
                        resolve_templates=resolve_templates,
                        resolve_ha_includes=resolve_ha_includes,
                        _depth=_depth + 1,
                    )
                    if expanded_child is SKIP:
                        continue
                    items.append(expanded_child)
                return items

            if value.tag == "!include_dir_merge_list":
                if not include_path.exists() or not include_path.is_dir():
                    warnings.append(f"{value.tag} directory not found: {include_arg}")
                    return []
                merged: list[Any] = []
                for child in sorted(include_path.glob("*.y*ml")):
                    loaded = _load_yaml_file(child, warnings)
                    expanded_child = expand_includes(
                        loaded,
                        config_dir=config_dir,
                        base_path=child,
                        warnings=warnings,
                        resolve_templates=resolve_templates,
                        resolve_ha_includes=resolve_ha_includes,
                        _depth=_depth + 1,
                    )
                    if expanded_child is SKIP:
                        continue
                    if isinstance(expanded_child, list):
                        merged.extend(expanded_child)
                    elif expanded_child is not None:
                        merged.append(expanded_child)
                return merged

            if value.tag in {"!include_dir_named", "!include_dir_merge_named"}:
                if not include_path.exists() or not include_path.is_dir():
                    warnings.append(f"{value.tag} directory not found: {include_arg}")
                    return {}
                result: dict[str, Any] = {}
                for child in sorted(include_path.glob("*.y*ml")):
                    key = child.stem
                    loaded = _load_yaml_file(child, warnings)
                    expanded_child = expand_includes(
                        loaded,
                        config_dir=config_dir,
                        base_path=child,
                        warnings=warnings,
                        resolve_templates=resolve_templates,
                        resolve_ha_includes=resolve_ha_includes,
                        _depth=_depth + 1,
                    )
                    if expanded_child is SKIP:
                        continue
                    if value.tag == "!include_dir_merge_named":
                        if isinstance(expanded_child, dict) and isinstance(result.get(key), dict):
                            result[key] = _deep_merge(result[key], expanded_child)
                        else:
                            result[key] = expanded_child
                    else:
                        result[key] = expanded_child
                return result

        # Preserve tag but expand nested structures.
        nested = value.value
        if isinstance(nested, dict):
            output: dict[str, Any] = {}
            for key, nested_value in nested.items():
                expanded_value = expand_includes(
                    nested_value,
                    config_dir=config_dir,
                    base_path=base_path,
                    warnings=warnings,
                    resolve_templates=resolve_templates,
                    resolve_ha_includes=resolve_ha_includes,
                    _depth=_depth + 1,
                )
                if expanded_value is SKIP:
                    continue
                output[key] = expanded_value
            return TaggedValue(
                tag=value.tag,
                value=output,
                line=value.line,
            )
        if isinstance(nested, list):
            output: list[Any] = []
            for entry in nested:
                expanded_value = expand_includes(
                    entry,
                    config_dir=config_dir,
                    base_path=base_path,
                    warnings=warnings,
                    resolve_templates=resolve_templates,
                    resolve_ha_includes=resolve_ha_includes,
                    _depth=_depth + 1,
                )
                if expanded_value is SKIP:
                    continue
                output.append(expanded_value)
            return TaggedValue(tag=value.tag, value=output, line=value.line)
        return value

    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, nested_value in value.items():
            expanded_value = expand_includes(
                nested_value,
                config_dir=config_dir,
                base_path=base_path,
                warnings=warnings,
                resolve_templates=resolve_templates,
                resolve_ha_includes=resolve_ha_includes,
                _depth=_depth + 1,
            )
            if expanded_value is SKIP:
                continue
            output[key] = expanded_value
        return output
    if isinstance(value, list):
        output: list[Any] = []
        for entry in value:
            expanded = expand_includes(
                entry,
                config_dir=config_dir,
                base_path=base_path,
                warnings=warnings,
                resolve_templates=resolve_templates,
                resolve_ha_includes=resolve_ha_includes,
                _depth=_depth + 1,
            )
            if expanded is SKIP:
                continue
            output.append(expanded)
        return output
    return value


def state_group_candidates(states: list[dict[str, Any]], allowed_domains: set[str]) -> list[dict[str, Any]]:
    """Filter HA `/api/states` payload to entities that look like group entities.

    The Group integration exposes group membership via `attributes.entity_id` on entities. We use
    that as the primary signal and then filter by allowed domains (e.g. group/sensor/light).
    """

    rows: list[dict[str, Any]] = []
    for state in states:
        if not isinstance(state, dict):
            continue
        entity_id = state.get("entity_id")
        if not isinstance(entity_id, str) or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain not in allowed_domains:
            continue
        attrs = state.get("attributes")
        if not isinstance(attrs, dict):
            continue
        members = attrs.get("entity_id")
        if not isinstance(members, list):
            continue
        rows.append(state)
    return rows

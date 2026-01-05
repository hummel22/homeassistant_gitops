from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

from . import settings
from .config_store import ensure_gitops_dirs
from .fs_utils import file_hash, modules_hash, read_text, write_yaml_if_changed, yaml_dump, yaml_load
from .yaml_tags import SKIP, TaggedValue, expand_includes, is_template_tag, resolve_template_candidates


@dataclass(frozen=True)
class DomainSpec:
    key: str
    domain_file: Path
    module_dir: Path
    package_filename: str
    kind: str
    id_field: str | None
    auto_id: bool
    reload_domain: str | None


@dataclass
class ModuleItem:
    ha_id: str
    data: Any
    source: str
    order: int
    name: str | None = None
    fingerprint: str | None = None
    helper_type: str | None = None
    expanded: Any | None = None
    line: int | None = None


@dataclass(frozen=True)
class TemplateEditCandidate:
    template_path: Path
    include_tag: str
    include_site: str
    include_site_line: int | None
    domain_site: str
    domain_line: int | None
    proposed_value: Any


@dataclass
class LovelaceModule:
    path: Path
    rel_path: str
    shape: str
    views: list[ModuleItem]
    meta: dict[str, Any]
    changed: bool
    valid: bool


YAML_MODULE_DOMAINS = [
    DomainSpec(
        key="automation",
        domain_file=settings.CONFIG_DIR / "automations.yaml",
        module_dir=settings.CONFIG_DIR / "automations",
        package_filename="automation.yaml",
        kind="list",
        id_field="id",
        auto_id=True,
        reload_domain="automation",
    ),
    DomainSpec(
        key="script",
        domain_file=settings.CONFIG_DIR / "scripts.yaml",
        module_dir=settings.CONFIG_DIR / "scripts",
        package_filename="script.yaml",
        kind="mapping",
        id_field=None,
        auto_id=False,
        reload_domain="script",
    ),
    DomainSpec(
        key="group",
        domain_file=settings.CONFIG_DIR / "groups.yaml",
        module_dir=settings.CONFIG_DIR / "groups",
        package_filename="groups.yaml",
        kind="mapping",
        id_field=None,
        auto_id=False,
        reload_domain=None,
    ),
    DomainSpec(
        key="scene",
        domain_file=settings.CONFIG_DIR / "scenes.yaml",
        module_dir=settings.CONFIG_DIR / "scenes",
        package_filename="scene.yaml",
        kind="list",
        id_field="id",
        auto_id=True,
        reload_domain="scene",
    ),
    DomainSpec(
        key="template",
        domain_file=settings.CONFIG_DIR / "templates.yaml",
        module_dir=settings.CONFIG_DIR / "templates",
        package_filename="template.yaml",
        kind="list",
        id_field=None,
        auto_id=False,
        reload_domain="template",
    ),
    DomainSpec(
        key="lovelace",
        domain_file=settings.CONFIG_DIR / "ui-lovelace.yaml",
        module_dir=settings.CONFIG_DIR / "lovelace",
        package_filename="lovelace.yaml",
        kind="lovelace",
        id_field="path",
        auto_id=True,
        reload_domain=None,
    ),
]

HELPER_TYPES = [
    "input_boolean",
    "input_button",
    "input_datetime",
    "input_number",
    "input_select",
    "input_text",
    "counter",
    "timer",
    "schedule",
]

HELPERS_DOMAIN_KEY = "helpers"


def list_changed_domains(paths: Iterable[str]) -> set[str]:
    domains: set[str] = set()
    helper_domains = set(HELPER_TYPES)
    for path in paths:
        lowered = path.lower()
        if lowered.endswith("automations.yaml") or lowered.startswith("automations/"):
            domains.add("automation")
        if lowered.endswith("scripts.yaml") or lowered.startswith("scripts/"):
            domains.add("script")
        if lowered.endswith("groups.yaml") or lowered.startswith("groups/"):
            domains.add("group")
        if lowered.endswith("scenes.yaml") or lowered.startswith("scenes/"):
            domains.add("scene")
        if lowered.endswith("templates.yaml") or lowered.startswith("templates/"):
            domains.add("template")
        if lowered.endswith("ui-lovelace.yaml") or lowered.startswith("lovelace/"):
            domains.add("lovelace")
        for helper in helper_domains:
            if lowered.endswith(f"{helper}.yaml"):
                domains.add(helper)
    return domains


def should_sync_yaml_modules(paths: Iterable[str]) -> bool:
    module_prefixes = (
        "automations/",
        "scripts/",
        "groups/",
        "scenes/",
        "templates/",
        "helpers/",
        "lovelace/",
        "packages/",
    )
    domain_files = (
        "automations.yaml",
        "scripts.yaml",
        "groups.yaml",
        "scenes.yaml",
        "templates.yaml",
        "ui-lovelace.yaml",
    )
    helper_domains = set(HELPER_TYPES)
    for path in paths:
        lowered = path.lower()
        if lowered.startswith(module_prefixes):
            return True
        if lowered.endswith(domain_files):
            return True
        for helper in helper_domains:
            if lowered.endswith(f"{helper}.yaml"):
                return True
    return False


def _build_automation_blocks() -> dict[str, list[str]]:
    automations_dir = settings.CONFIG_DIR / "automations"
    if not automations_dir.exists():
        return {}
    entries: dict[str, list[str]] = {}
    for file_path in sorted(automations_dir.glob("*.y*ml")):
        contents = read_text(file_path)
        rel_path = str(file_path.relative_to(settings.CONFIG_DIR))
        block = [
            f"# BEGIN {rel_path}",
            contents.rstrip(),
            f"# END {rel_path}",
            "",
        ]
        entries[rel_path] = block
    return entries


def merge_automations() -> list[str]:
    blocks = _build_automation_blocks()
    if not blocks:
        return []
    merged_path = settings.CONFIG_DIR / "automations.yaml"
    existing_lines: list[str] = []
    if merged_path.exists():
        existing_lines = merged_path.read_text(encoding="utf-8").splitlines()
    if not existing_lines:
        new_content = "\n".join(line for block in blocks.values() for line in block).strip() + "\n"
        merged_path.write_text(new_content, encoding="utf-8")
        return [str(merged_path.relative_to(settings.CONFIG_DIR))]

    output: list[str] = []
    used_blocks: set[str] = set()
    index = 0
    while index < len(existing_lines):
        line = existing_lines[index]
        if line.startswith("# BEGIN "):
            marker = line.replace("# BEGIN ", "", 1).strip()
            index += 1
            while index < len(existing_lines) and not existing_lines[index].startswith("# END "):
                index += 1
            if index < len(existing_lines):
                index += 1
            block = blocks.get(marker)
            if block:
                output.extend(block)
                used_blocks.add(marker)
            continue
        output.append(line)
        index += 1

    remaining = [block for key, block in blocks.items() if key not in used_blocks]
    if remaining:
        if output and output[-1].strip():
            output.append("")
        for block in remaining:
            output.extend(block)
    new_content = "\n".join(output).strip() + "\n"
    old_content = "\n".join(existing_lines).strip() + "\n"
    if new_content != old_content:
        merged_path.write_text(new_content, encoding="utf-8")
        return [str(merged_path.relative_to(settings.CONFIG_DIR))]
    return []


def update_source_from_markers() -> list[str]:
    merged_path = settings.CONFIG_DIR / "automations.yaml"
    if not merged_path.exists():
        return []
    lines = merged_path.read_text(encoding="utf-8").splitlines()
    current_file: Path | None = None
    buffer: list[str] = []
    updated: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_file
        if current_file is None:
            buffer = []
            return
        current_file.parent.mkdir(parents=True, exist_ok=True)
        current_file.write_text("\n".join(buffer).strip() + "\n", encoding="utf-8")
        updated.append(str(current_file.relative_to(settings.CONFIG_DIR)))
        buffer = []

    for line in lines:
        if line.startswith("# BEGIN "):
            flush()
            rel = line.replace("# BEGIN ", "", 1).strip()
            current_file = settings.CONFIG_DIR / rel
            buffer = []
            continue
        if line.startswith("# END "):
            flush()
            current_file = None
            continue
        if current_file is not None:
            buffer.append(line)
    flush()
    return updated


def _legacy_unassigned_module_path(module_dir: Path) -> Path:
    return module_dir / f"{module_dir.name}.unassigned.yaml"


def _unassigned_module_path(module_dir: Path) -> Path:
    unassigned_dir = settings.PACKAGES_DIR / "unassigned"
    if module_dir.name == "helpers":
        return unassigned_dir / "helpers.yaml"
    domain_key = MODULE_DOMAIN_MAP.get(module_dir.name)
    if domain_key:
        spec = _spec_by_key(domain_key)
        if spec:
            return unassigned_dir / spec.package_filename
    return _legacy_unassigned_module_path(module_dir)


def _merge_legacy_unassigned(
    legacy_path: Path,
    new_path: Path,
    module_dir: Path,
    spec: DomainSpec | None,
) -> None:
    data, _lines, error = yaml_load(legacy_path)
    if error:
        raise ValueError(error)
    if data is None:
        return
    if module_dir.name == "helpers":
        if not isinstance(data, dict):
            raise ValueError("Legacy unassigned helpers file is not a map.")
        items: list[dict[str, Any]] = []
        for helper_type, helper_values in data.items():
            if helper_type not in HELPER_TYPES:
                continue
            if not isinstance(helper_values, dict):
                raise ValueError("Legacy unassigned helpers file has non-map helper data.")
            for key, value in helper_values.items():
                items.append({"helper_type": helper_type, "key": str(key), "data": value})
        if items:
            _append_items_to_helpers_file(new_path, items)
        return
    if not spec:
        raise ValueError("Missing domain spec for legacy unassigned merge.")
    if spec.kind == "mapping":
        if not isinstance(data, dict):
            raise ValueError("Legacy unassigned file is not a map.")
        items = [{"key": str(key), "data": value} for key, value in data.items()]
        if items:
            _append_items_to_mapping_file(new_path, items)
        return
    if spec.kind == "lovelace":
        items_data: list[Any] = []
        if isinstance(data, list):
            items_data = data
        elif isinstance(data, dict):
            views = data.get("views")
            if not isinstance(views, list):
                raise ValueError("Legacy unassigned lovelace file is not a list.")
            items_data = views
        else:
            raise ValueError("Legacy unassigned lovelace file is not a list.")
        items = [{"data": entry} for entry in items_data if isinstance(entry, dict)]
        if items:
            _append_items_to_lovelace_file(new_path, spec, items)
        return
    if not isinstance(data, list):
        raise ValueError("Legacy unassigned file is not a list.")
    items = [{"data": entry} for entry in data if isinstance(entry, dict)]
    if items:
        _append_items_to_list_file(new_path, spec, items)


def _ensure_unassigned_path(
    module_dir: Path,
    spec: DomainSpec | None,
    warnings: list[str],
    preview: dict[str, str] | None,
) -> Path:
    new_path = _unassigned_module_path(module_dir)
    if preview is not None:
        return new_path
    legacy_path = _legacy_unassigned_module_path(module_dir)
    if legacy_path == new_path or not legacy_path.exists():
        return new_path
    new_path.parent.mkdir(parents=True, exist_ok=True)
    if not new_path.exists():
        legacy_path.rename(new_path)
        warnings.append(
            f"Migrated {legacy_path.relative_to(settings.CONFIG_DIR)} to "
            f"{new_path.relative_to(settings.CONFIG_DIR)}."
        )
        return new_path
    try:
        _merge_legacy_unassigned(legacy_path, new_path, module_dir, spec)
    except ValueError as exc:
        warnings.append(
            f"Unable to merge legacy unassigned file {legacy_path.relative_to(settings.CONFIG_DIR)} "
            f"into {new_path.relative_to(settings.CONFIG_DIR)}: {exc}"
        )
        return new_path
    legacy_path.unlink()
    warnings.append(
        f"Merged {legacy_path.relative_to(settings.CONFIG_DIR)} into "
        f"{new_path.relative_to(settings.CONFIG_DIR)}."
    )
    return new_path


def _normalize_value(value: Any, exclude_keys: set[str]) -> Any:
    if isinstance(value, TaggedValue):
        return {
            "__tag__": value.tag,
            "__value__": _normalize_value(value.value, exclude_keys),
        }
    if isinstance(value, dict):
        return {
            key: _normalize_value(value[key], exclude_keys)
            for key in sorted(value.keys())
            if key not in exclude_keys
        }
    if isinstance(value, list):
        return [_normalize_value(entry, exclude_keys) for entry in value]
    return value


def _fingerprint(value: Any, exclude_keys: set[str]) -> str:
    normalized = _normalize_value(value, exclude_keys)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _contains_template_includes(value: Any) -> bool:
    if isinstance(value, TaggedValue) and is_template_tag(value.tag):
        return True
    if isinstance(value, TaggedValue):
        return _contains_template_includes(value.value)
    if isinstance(value, dict):
        return any(_contains_template_includes(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_template_includes(child) for child in value)
    return False


def _merge_domain_value_preserving_templates(
    module_value: Any,
    domain_value: Any,
    *,
    include_site_path: Path,
    include_site_rel: str,
    domain_site_rel: str,
    domain_line: int | None,
    warnings: list[str],
    edits: list[TemplateEditCandidate],
    _depth: int = 0,
) -> Any:
    """Merge a domain-edited value into a module value, protecting template includes.

    - Non-template content is replaced with `domain_value` (domain wins).
    - Template include tags (e.g. `!/packages/foo.template.yaml`) are preserved in the module value.
    - If the domain edit changes content that originated from a template include, we record a
      TemplateEditCandidate so the caller can generate a `*.diff` artifact for the operator.
    """

    if _depth > 50:
        warnings.append(f"Template merge exceeded max depth in {include_site_rel}.")
        return copy.deepcopy(domain_value)

    if isinstance(module_value, TaggedValue) and is_template_tag(module_value.tag):
        expanded = expand_includes(
            module_value,
            config_dir=settings.CONFIG_DIR,
            base_path=include_site_path,
            warnings=warnings,
            resolve_templates=True,
            resolve_ha_includes=False,
        )
        if expanded is SKIP:
            return module_value
        if expanded != domain_value:
            candidates = resolve_template_candidates(
                module_value.tag,
                config_dir=settings.CONFIG_DIR,
                base_path=include_site_path,
                warnings=warnings,
            )
            include_site_line = module_value.line
            if len(candidates) == 1:
                edits.append(
                    TemplateEditCandidate(
                        template_path=candidates[0],
                        include_tag=module_value.tag,
                        include_site=include_site_rel,
                        include_site_line=include_site_line,
                        domain_site=domain_site_rel,
                        domain_line=domain_line,
                        proposed_value=copy.deepcopy(domain_value),
                    )
                )
            else:
                warnings.append(
                    "Template-backed edit detected for "
                    f"{module_value.tag} in {include_site_rel}:{include_site_line or '?'}; "
                    "cannot generate a diff for glob/ambiguous includes."
                )
        return module_value

    if isinstance(module_value, dict) and isinstance(domain_value, dict):
        merged: dict[str, Any] = {}
        for key, value in module_value.items():
            if key not in domain_value:
                continue
            merged[key] = _merge_domain_value_preserving_templates(
                value,
                domain_value[key],
                include_site_path=include_site_path,
                include_site_rel=include_site_rel,
                domain_site_rel=domain_site_rel,
                domain_line=domain_line,
                warnings=warnings,
                edits=edits,
                _depth=_depth + 1,
            )
        for key, value in domain_value.items():
            if key in module_value:
                continue
            merged[key] = copy.deepcopy(value)
        return merged

    if isinstance(module_value, list) and isinstance(domain_value, list):
        merged: list[Any] = []
        for idx in range(min(len(module_value), len(domain_value))):
            merged.append(
                _merge_domain_value_preserving_templates(
                    module_value[idx],
                    domain_value[idx],
                    include_site_path=include_site_path,
                    include_site_rel=include_site_rel,
                    domain_site_rel=domain_site_rel,
                    domain_line=domain_line,
                    warnings=warnings,
                    edits=edits,
                    _depth=_depth + 1,
                )
            )
        if len(domain_value) > len(module_value):
            merged.extend(copy.deepcopy(domain_value[len(module_value) :]))
        return merged

    return copy.deepcopy(domain_value)


def _build_template_diff(template_rel: str, old_text: str, new_text: str) -> str:
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{template_rel}",
            tofile=f"b/{template_rel}",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    diff_text = "\n".join(diff_lines)
    return f"diff --git a/{template_rel} b/{template_rel}\n{diff_text}\n"


def _write_template_diffs(
    edits: list[TemplateEditCandidate],
    warnings: list[str],
    preview: dict[str, str] | None,
) -> list[str]:
    changed: list[str] = []
    if not edits:
        return changed

    by_template: dict[Path, list[TemplateEditCandidate]] = {}
    for edit in edits:
        by_template.setdefault(edit.template_path, []).append(edit)

    for template_path, candidates in by_template.items():
        try:
            template_rel = template_path.relative_to(settings.CONFIG_DIR).as_posix()
        except ValueError:
            warnings.append(
                f"Template diff skipped for {template_path.as_posix()}: outside config dir."
            )
            continue

        proposed_by_fp: dict[str, Any] = {}
        for candidate in candidates:
            proposed_by_fp.setdefault(_fingerprint(candidate.proposed_value, set()), candidate.proposed_value)
        if len(proposed_by_fp) > 1:
            warnings.append(
                f"Conflicting template edits detected for {template_rel}; wrote no diff file."
            )
            continue

        proposed_value = next(iter(proposed_by_fp.values()))
        old_text = read_text(template_path)
        new_text = yaml_dump(proposed_value)
        diff_text = _build_template_diff(template_rel, old_text, new_text)
        if not diff_text.strip():
            continue

        header_lines: list[str] = [f"# TEMPLATE EDIT DETECTED for {template_rel}"]
        for candidate in candidates:
            domain_loc = (
                f"{candidate.domain_site}:{candidate.domain_line}"
                if candidate.domain_line
                else candidate.domain_site
            )
            include_loc = (
                f"{candidate.include_site}:{candidate.include_site_line}"
                if candidate.include_site_line
                else candidate.include_site
            )
            header_lines.append(f"# Edited in {domain_loc}")
            header_lines.append(f"# Included from {include_loc} ({candidate.include_tag})")
        header = "\n".join(dict.fromkeys(header_lines)) + "\n\n"

        diff_path = template_path.parent / f"{template_path.name}.diff"
        if _write_text(diff_path, header + diff_text, preview):
            changed.append(diff_path.relative_to(settings.CONFIG_DIR).as_posix())
    return changed


def _item_name(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("alias", "name", "title"):
            name = value.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _automation_alias_id(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    alias = value.get("alias")
    if not isinstance(alias, str) or not alias.strip():
        return None
    return _normalize_automation_id(alias)


def _extract_item_id(value: Any, id_field: str | None) -> str | None:
    if id_field and isinstance(value, dict):
        raw_id = value.get(id_field)
        if raw_id is None:
            return None
        return str(raw_id)
    return None


def _synthetic_id(rel_path: str, line: int | None, index: int) -> str:
    if line and line > 0:
        return f"{rel_path}:{line}"
    return f"{rel_path}:{index + 1}"


def _ensure_unique_id(candidate: str, used_ids: set[str], fingerprint: str | None) -> str:
    if candidate not in used_ids:
        return candidate
    suffix = 2
    while True:
        augmented = f"{candidate}_{suffix}"
        if augmented not in used_ids:
            return augmented
        suffix += 1


_AUTOMATION_ID_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_AUTOMATION_ID_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_AUTOMATION_ID_MULTI_UNDERSCORE = re.compile(r"_+")


def _normalize_automation_id(alias: str) -> str | None:
    """Normalize an automation alias into a safe, deterministic `id`.

    Rules (v1):
    - Split camelCase boundaries into words.
    - Lowercase.
    - Keep only [a-z0-9_] (non-alnum becomes `_`).
    - Collapse repeated `_` and strip leading/trailing `_`.
    """

    cleaned = alias.strip()
    if not cleaned:
        return None
    split = _AUTOMATION_ID_CAMEL_BOUNDARY.sub("_", cleaned)
    lowered = split.lower()
    underscored = _AUTOMATION_ID_NON_ALNUM.sub("_", lowered)
    normalized = _AUTOMATION_ID_MULTI_UNDERSCORE.sub("_", underscored).strip("_")
    return normalized or None


def _sanitize_lovelace_path(value: str) -> str:
    cleaned = value.replace("/", "-").replace(":", "-")
    cleaned = "".join(ch.lower() if ch.isalnum() or ch in {"-", "_"} else "-" for ch in cleaned)
    cleaned = cleaned.strip("-")
    return cleaned or "view"


def _list_module_files(spec: DomainSpec) -> list[Path]:
    files: list[Path] = []
    if settings.PACKAGES_DIR.exists():
        for package_dir in sorted(settings.PACKAGES_DIR.iterdir()):
            if not package_dir.is_dir():
                continue
            candidate = package_dir / spec.package_filename
            if candidate.exists():
                files.append(candidate)
    if spec.module_dir.exists():
        files.extend(sorted(spec.module_dir.glob("*.y*ml")))
    return files


def _load_sync_state() -> tuple[dict[str, Any], list[str]]:
    if not settings.SYNC_STATE_PATH.exists():
        return {"schema_version": 1, "domains": {}}, []
    try:
        data = yaml.safe_load(read_text(settings.SYNC_STATE_PATH)) or {}
    except yaml.YAMLError as exc:
        return {"schema_version": 1, "domains": {}}, [f"{settings.SYNC_STATE_PATH}: {exc}"]
    if not isinstance(data, dict):
        return {"schema_version": 1, "domains": {}}, []
    data.setdefault("schema_version", 1)
    data.setdefault("domains", {})
    if not isinstance(data["domains"], dict):
        data["domains"] = {}
    return data, []


def _save_sync_state(state: dict[str, Any], preview: bool = False) -> None:
    if preview:
        return
    ensure_gitops_dirs()
    settings.SYNC_STATE_PATH.write_text(yaml_dump(state), encoding="utf-8")


def _mapping_path(domain_key: str) -> Path:
    return settings.MAPPINGS_DIR / f"{domain_key}.yaml"


def _load_mapping(domain_key: str, unassigned_rel: str) -> tuple[dict[str, Any], list[str]]:
    path = _mapping_path(domain_key)
    if not path.exists():
        return {
            "schema_version": 1,
            "domain": domain_key,
            "unassigned_path": unassigned_rel,
            "entries": [],
        }, []
    try:
        data = yaml.safe_load(read_text(path)) or {}
    except yaml.YAMLError as exc:
        return {
            "schema_version": 1,
            "domain": domain_key,
            "unassigned_path": unassigned_rel,
            "entries": [],
        }, [f"{path.relative_to(settings.CONFIG_DIR)}: {exc}"]
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("domain", domain_key)
    data["unassigned_path"] = unassigned_rel
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    data["entries"] = entries
    return data, []


def _save_mapping(domain_key: str, mapping: dict[str, Any], preview: bool = False) -> None:
    if preview:
        return
    ensure_gitops_dirs()
    path = _mapping_path(domain_key)
    path.write_text(yaml_dump(mapping), encoding="utf-8")


def _write_yaml(path: Path, data: Any, preview: dict[str, str] | None) -> bool:
    rendered = yaml_dump(data)
    if rendered == read_text(path):
        return False
    if preview is not None:
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        preview[rel_path] = rendered
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def _is_empty_yaml_payload(data: Any) -> bool:
    if data is None or data == [] or data == {}:
        return True
    if isinstance(data, dict) and set(data.keys()) == {"views"}:
        return data.get("views") == []
    return False


def _write_domain_yaml(path: Path, data: Any, preview: dict[str, str] | None) -> bool:
    if _is_empty_yaml_payload(data):
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        if preview is not None:
            if path.exists():
                preview[rel_path] = ""
                return True
            return False
        if path.exists():
            path.unlink()
            return True
        return False
    return _write_yaml(path, data, preview)


def _write_text(path: Path, content: str, preview: dict[str, str] | None) -> bool:
    if preview is not None:
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        preview[rel_path] = content
        return True
    if content == read_text(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _mapping_entry_key(entry: dict[str, Any]) -> str:
    helper_type = entry.get("helper_type")
    if helper_type:
        return f"{helper_type}:{entry.get('id')}"
    return str(entry.get("id"))


def _parse_list_items(
    data: Any,
    lines: list[int] | None,
    rel_path: str,
    spec: DomainSpec,
    warnings: list[str],
    used_ids: set[str] | None = None,
) -> tuple[list[ModuleItem], bool]:
    if data is None:
        data = []
    if not isinstance(data, list):
        warnings.append(f"{rel_path} is not a list of items.")
        return [], False
    items: list[ModuleItem] = []
    changed = False
    exclude_keys = {spec.id_field} if spec.id_field else set()
    id_set = used_ids if used_ids is not None else set()
    for idx, entry in enumerate(data):
        if not isinstance(entry, dict):
            warnings.append(f"{rel_path} item {idx + 1} is not a map.")
            continue
        line = None
        if lines and idx < len(lines):
            line = lines[idx]
        item_id = _extract_item_id(entry, spec.id_field)
        if item_id:
            id_set.add(item_id)
        else:
            if spec.key == "automation":
                candidate = _automation_alias_id(entry)
                if not candidate:
                    candidate = _synthetic_id(rel_path, line, idx)
                fingerprint = _fingerprint(entry, exclude_keys)
                item_id = _ensure_unique_id(candidate, id_set, fingerprint)
            else:
                item_id = _synthetic_id(rel_path, line, idx)
                if spec.key == "lovelace":
                    item_id = _sanitize_lovelace_path(item_id)
            if spec.id_field and spec.auto_id:
                entry[spec.id_field] = item_id
                changed = True
            id_set.add(item_id)
        expanded = expand_includes(
            entry,
            config_dir=settings.CONFIG_DIR,
            base_path=settings.CONFIG_DIR / rel_path,
            warnings=warnings,
            resolve_templates=True,
            resolve_ha_includes=False,
        )
        fingerprint = _fingerprint(expanded, exclude_keys)
        items.append(
            ModuleItem(
                ha_id=item_id,
                data=entry,
                source=rel_path,
                order=idx,
                name=_item_name(expanded),
                fingerprint=fingerprint,
                expanded=expanded,
                line=line,
            )
        )
    return items, changed


def _parse_list_module_file(
    path: Path, spec: DomainSpec, warnings: list[str], used_ids: set[str] | None = None
) -> tuple[list[ModuleItem], list[Any], bool, bool]:
    data, lines, error = yaml_load(path)
    if error:
        warnings.append(error)
        return [], [], False, False
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    items, changed = _parse_list_items(data, lines, rel_path, spec, warnings, used_ids=used_ids)
    return items, data or [], changed, True


def _parse_mapping_module_file(
    path: Path, warnings: list[str], *, resolve_ha_includes: bool
) -> tuple[list[ModuleItem], dict[str, Any], bool, bool]:
    data, _lines, error = yaml_load(path)
    if error:
        warnings.append(error)
        return [], {}, False, False
    if data is None:
        data = {}
    if not isinstance(data, dict):
        warnings.append(f"{path.relative_to(settings.CONFIG_DIR)} is not a map.")
        return [], {}, False, True
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    items: list[ModuleItem] = []
    for idx, (key, value) in enumerate(data.items()):
        expanded = expand_includes(
            value,
            config_dir=settings.CONFIG_DIR,
            base_path=path,
            warnings=warnings,
            resolve_templates=True,
            resolve_ha_includes=resolve_ha_includes,
        )
        if expanded is SKIP:
            expanded = None
        name = _item_name(expanded)
        fingerprint = _fingerprint(expanded, set())
        items.append(
            ModuleItem(
                ha_id=str(key),
                data=value,
                source=rel_path,
                order=idx,
                name=name,
                fingerprint=fingerprint,
                expanded=expanded,
            )
        )
    return items, data, False, True


def _parse_list_domain(
    spec: DomainSpec, warnings: list[str], used_ids: set[str] | None = None
) -> tuple[list[ModuleItem], list[Any], bool, bool]:
    data, lines, error = yaml_load(spec.domain_file)
    if error:
        warnings.append(error)
        return [], [], False, False
    rel_path = spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix()
    items, changed = _parse_list_items(data, lines, rel_path, spec, warnings, used_ids=used_ids)
    return items, data or [], changed, True


def _parse_mapping_domain(
    spec: DomainSpec, warnings: list[str], *, resolve_ha_includes: bool
) -> tuple[list[ModuleItem], dict[str, Any], bool, bool]:
    data, _lines, error = yaml_load(spec.domain_file)
    if error:
        warnings.append(error)
        return [], {}, False, False
    if data is None:
        data = {}
    if not isinstance(data, dict):
        warnings.append(f"{spec.domain_file.relative_to(settings.CONFIG_DIR)} is not a map.")
        return [], {}, False, True
    rel_path = spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix()
    items: list[ModuleItem] = []
    for idx, (key, value) in enumerate(data.items()):
        expanded = expand_includes(
            value,
            config_dir=settings.CONFIG_DIR,
            base_path=spec.domain_file,
            warnings=warnings,
            resolve_templates=True,
            resolve_ha_includes=resolve_ha_includes,
        )
        if expanded is SKIP:
            expanded = None
        name = _item_name(expanded)
        fingerprint = _fingerprint(expanded, set())
        items.append(
            ModuleItem(
                ha_id=str(key),
                data=value,
                source=rel_path,
                order=idx,
                name=name,
                fingerprint=fingerprint,
                expanded=expanded,
            )
        )
    return items, data, False, True


def _parse_lovelace_module(path: Path, warnings: list[str]) -> LovelaceModule:
    data, lines, error = yaml_load(path)
    if error:
        warnings.append(error)
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        return LovelaceModule(
            path=path,
            rel_path=rel_path,
            shape="list",
            views=[],
            meta={},
            changed=False,
            valid=False,
        )
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    shape = "list"
    meta: dict[str, Any] = {}
    views_data: list[Any] = []
    if data is None:
        data = []
    if isinstance(data, list):
        views_data = data
    elif isinstance(data, dict):
        shape = "dict"
        views_data = data.get("views") or []
        if not isinstance(views_data, list):
            warnings.append(f"{rel_path} views is not a list.")
            views_data = []
        meta = {key: value for key, value in data.items() if key != "views"}
    else:
        warnings.append(f"{rel_path} is not a list or map.")
        views_data = []
    spec = next(domain for domain in YAML_MODULE_DOMAINS if domain.key == "lovelace")
    items, changed = _parse_list_items(views_data, lines, rel_path, spec, warnings)
    return LovelaceModule(
        path=path,
        rel_path=rel_path,
        shape=shape,
        views=items,
        meta=meta,
        changed=changed,
        valid=True,
    )


def _parse_lovelace_domain(
    spec: DomainSpec, warnings: list[str]
) -> tuple[list[ModuleItem], dict[str, Any], bool, bool]:
    data, lines, error = yaml_load(spec.domain_file)
    if error:
        warnings.append(error)
        return [], {}, False, False
    if data is None:
        data = {}
    if not isinstance(data, dict):
        warnings.append(f"{spec.domain_file.relative_to(settings.CONFIG_DIR)} is not a map.")
        data = {}
    views_data = data.get("views") or []
    if not isinstance(views_data, list):
        warnings.append(f"{spec.domain_file.relative_to(settings.CONFIG_DIR)} views is not a list.")
        views_data = []
    meta = {key: value for key, value in data.items() if key != "views"}
    rel_path = spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix()
    items, changed = _parse_list_items(views_data, lines, rel_path, spec, warnings)
    return items, meta, changed, True


def _decide_preference(
    has_state: bool,
    domain_changed: bool,
    modules_changed: bool,
    domain_exists: bool,
    modules_exist: bool,
) -> str:
    if not has_state:
        if modules_exist:
            return "modules"
        if domain_exists:
            return "domain"
        return "modules"
    if domain_changed and not modules_changed:
        return "domain"
    if modules_changed and not domain_changed:
        return "modules"
    if domain_changed and modules_changed:
        return "mixed"
    return "modules"


def _resolve_preference(preference_override: str | None, computed: str) -> str:
    if preference_override is None:
        return computed
    if preference_override not in {"modules", "domain", "mixed"}:
        raise ValueError("Unsupported preference override.")
    return preference_override


def _should_write_target(write_mode: str, target: str) -> bool:
    if write_mode == "all":
        return True
    if write_mode == "domain":
        return target == "domain"
    if write_mode == "modules":
        return target == "modules"
    raise ValueError("Unsupported write mode.")


def _needs_automation_marker_migration() -> bool:
    automations_yaml = settings.CONFIG_DIR / "automations.yaml"
    automations_dir = settings.CONFIG_DIR / "automations"
    if not automations_yaml.exists():
        return False
    if automations_dir.exists() and list(automations_dir.glob("*.y*ml")):
        return False
    if "# BEGIN automations/" not in read_text(automations_yaml):
        return False
    return True


def _maybe_migrate_automation_markers(warnings: list[str]) -> None:
    if not _needs_automation_marker_migration():
        return
    updated = update_source_from_markers()
    if updated:
        warnings.append("Migrated marker-based automations into module files.")


def _sync_list_domain(
    spec: DomainSpec,
    state: dict[str, Any],
    warnings: list[str],
    preview: dict[str, str] | None = None,
    preference_override: str | None = None,
    write_mode: str = "all",
) -> list[str]:
    changed_files: list[str] = []
    module_files = _list_module_files(spec)
    template_edits: list[TemplateEditCandidate] = []
    module_used_ids: set[str] | None = None
    if spec.key == "automation" and spec.id_field:
        module_used_ids = set()
        for path in module_files:
            data, _lines, error = yaml_load(path)
            if error:
                continue
            if data is None:
                continue
            if not isinstance(data, list):
                continue
            for entry in data:
                if isinstance(entry, dict) and entry.get(spec.id_field) is not None:
                    module_used_ids.add(str(entry.get(spec.id_field)))
    module_items_by_file: dict[str, list[ModuleItem]] = {}
    module_items_by_id: dict[str, ModuleItem] = {}
    modules_injected = False
    invalid_module_files: set[str] = set()

    for path in module_files:
        items, _data, injected, valid = _parse_list_module_file(
            path, spec, warnings, used_ids=module_used_ids
        )
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        if not valid:
            invalid_module_files.add(rel_path)
            continue
        module_items_by_file[rel_path] = items
        if injected:
            modules_injected = True
        for item in items:
            if item.ha_id in module_items_by_id:
                warnings.append(
                    f"Duplicate {spec.key} id {item.ha_id} in {rel_path}; keeping first."
                )
                continue
            module_items_by_id[item.ha_id] = item

    domain_items, _domain_data, domain_injected, domain_valid = _parse_list_domain(
        spec,
        warnings,
        used_ids=set(module_used_ids) if module_used_ids is not None else None,
    )
    domain_items_by_id: dict[str, ModuleItem] = {}
    if domain_valid:
        for item in domain_items:
            if item.ha_id in domain_items_by_id:
                warnings.append(
                    f"Duplicate {spec.key} id {item.ha_id} in {spec.domain_file.relative_to(settings.CONFIG_DIR)}."
                )
                continue
            domain_items_by_id[item.ha_id] = item
    else:
        domain_items = []

    if not domain_valid and not module_items_by_file:
        return changed_files

    unassigned_path = _ensure_unassigned_path(spec.module_dir, spec, warnings, preview)
    unassigned_rel = unassigned_path.relative_to(settings.CONFIG_DIR).as_posix()
    mapping, mapping_warnings = _load_mapping(spec.key, unassigned_rel)
    warnings.extend(mapping_warnings)

    mapping_index: dict[str, dict[str, Any]] = {}
    for entry in mapping.get("entries", []):
        key = _mapping_entry_key(entry)
        if not key or key == "None":
            continue
        mapping_index[key] = dict(entry)

    for item in module_items_by_id.values():
        mapping_index[item.ha_id] = {
            "id": item.ha_id,
            "source": item.source,
            "name": item.name,
            "fingerprint": item.fingerprint,
        }

    for item in domain_items_by_id.values():
        if item.ha_id in mapping_index:
            continue
        mapping_index[item.ha_id] = {"id": item.ha_id, "source": unassigned_rel}

    domain_hash = file_hash(spec.domain_file)
    modules_digest = modules_hash(module_files)
    domain_state = state.get("domains", {}).get(spec.key, {})
    stored_domain_hash = domain_state.get("domain_hash")
    stored_modules_hash = domain_state.get("modules_hash")
    has_state = stored_domain_hash is not None or stored_modules_hash is not None
    domain_changed = domain_valid and (domain_injected or (stored_domain_hash != domain_hash))
    modules_changed = modules_injected or (stored_modules_hash != modules_digest)
    preference = _decide_preference(
        has_state,
        domain_changed,
        modules_changed,
        spec.domain_file.exists() and domain_valid,
        bool(module_files),
    )
    preference = _resolve_preference(preference_override, preference)
    write_modules = _should_write_target(write_mode, "modules")
    write_domain = _should_write_target(write_mode, "domain")
    exclude_keys = {spec.id_field} if spec.id_field else set()

    desired_items_by_file: dict[str, list[ModuleItem]] = {rel: [] for rel in module_items_by_file}
    for entry in mapping_index.values():
        source = entry.get("source") or unassigned_rel
        desired_items_by_file.setdefault(source, [])
        item_id = entry.get("id")
        if not item_id:
            continue
        module_item = module_items_by_id.get(item_id)
        domain_item = domain_items_by_id.get(item_id)

        if domain_item is None:
            if preference == "domain":
                continue
            if preference == "mixed" and source == unassigned_rel:
                continue
            if module_item:
                desired_items_by_file[source].append(module_item)
            continue

        if preference == "domain":
            if module_item and _contains_template_includes(module_item.data):
                include_site_path = settings.CONFIG_DIR / module_item.source
                merged_data = _merge_domain_value_preserving_templates(
                    module_item.data,
                    domain_item.data,
                    include_site_path=include_site_path,
                    include_site_rel=module_item.source,
                    domain_site_rel=domain_item.source,
                    domain_line=domain_item.line,
                    warnings=warnings,
                    edits=template_edits,
                )
                merged_expanded = expand_includes(
                    merged_data,
                    config_dir=settings.CONFIG_DIR,
                    base_path=include_site_path,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=False,
                )
                desired_items_by_file[source].append(
                    ModuleItem(
                        ha_id=domain_item.ha_id,
                        data=merged_data,
                        source=module_item.source,
                        order=domain_item.order,
                        name=_item_name(merged_expanded),
                        fingerprint=_fingerprint(merged_expanded, exclude_keys),
                        expanded=merged_expanded,
                        line=domain_item.line,
                    )
                )
            else:
                desired_items_by_file[source].append(domain_item)
        elif preference == "modules":
            if module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"{spec.key} {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)
        else:
            if source == unassigned_rel:
                if module_item and _contains_template_includes(module_item.data):
                    include_site_path = settings.CONFIG_DIR / module_item.source
                    merged_data = _merge_domain_value_preserving_templates(
                        module_item.data,
                        domain_item.data,
                        include_site_path=include_site_path,
                        include_site_rel=module_item.source,
                        domain_site_rel=domain_item.source,
                        domain_line=domain_item.line,
                        warnings=warnings,
                        edits=template_edits,
                    )
                    merged_expanded = expand_includes(
                        merged_data,
                        config_dir=settings.CONFIG_DIR,
                        base_path=include_site_path,
                        warnings=warnings,
                        resolve_templates=True,
                        resolve_ha_includes=False,
                    )
                    desired_items_by_file[source].append(
                        ModuleItem(
                            ha_id=domain_item.ha_id,
                            data=merged_data,
                            source=module_item.source,
                            order=domain_item.order,
                            name=_item_name(merged_expanded),
                            fingerprint=_fingerprint(merged_expanded, exclude_keys),
                            expanded=merged_expanded,
                            line=domain_item.line,
                        )
                    )
                else:
                    desired_items_by_file[source].append(domain_item)
            elif module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"{spec.key} {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)

    for rel_path, items in desired_items_by_file.items():
        if rel_path in invalid_module_files:
            continue
        payload = [item.data for item in sorted(items, key=lambda item: item.order)]
        if write_modules and _write_yaml(settings.CONFIG_DIR / rel_path, payload, preview):
            changed_files.append(rel_path)

    combined: list[Any] = []
    for rel_path in sorted(desired_items_by_file.keys()):
        items = desired_items_by_file[rel_path]
        for item in sorted(items, key=lambda item: item.order):
            if item.expanded is None or item.expanded is SKIP:
                warnings.append(
                    f"Skipping {spec.key} {item.ha_id} due to template expansion failure."
                )
                continue
            combined.append(item.expanded)
    if write_modules:
        changed_files.extend(_write_template_diffs(template_edits, warnings, preview))
    if write_domain and _write_domain_yaml(spec.domain_file, combined, preview):
        changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())

    entries: list[dict[str, Any]] = []
    for rel_path, items in desired_items_by_file.items():
        for item in sorted(items, key=lambda item: item.order):
            entry: dict[str, Any] = {"id": item.ha_id, "source": rel_path}
            if item.name:
                entry["name"] = item.name
            if item.fingerprint:
                entry["fingerprint"] = item.fingerprint
            entries.append(entry)
    entries.sort(key=lambda entry: entry.get("id") or "")
    mapping["entries"] = entries
    _save_mapping(spec.key, mapping, preview=preview is not None)

    module_hash_paths = {Path(path) for path in module_files}
    module_hash_paths.update(settings.CONFIG_DIR / rel for rel in desired_items_by_file)
    state.setdefault("domains", {})[spec.key] = {
        "domain_hash": file_hash(spec.domain_file),
        "modules_hash": modules_hash(sorted(module_hash_paths)),
    }
    return changed_files


def _sync_mapping_domain(
    spec: DomainSpec,
    state: dict[str, Any],
    warnings: list[str],
    preview: dict[str, str] | None = None,
    preference_override: str | None = None,
    write_mode: str = "all",
) -> list[str]:
    changed_files: list[str] = []
    module_files = _list_module_files(spec)
    template_edits: list[TemplateEditCandidate] = []
    resolve_ha_includes = spec.key == "group"
    module_items_by_file: dict[str, list[ModuleItem]] = {}
    module_items_by_id: dict[str, ModuleItem] = {}
    invalid_module_files: set[str] = set()

    for path in module_files:
        items, _data, _injected, valid = _parse_mapping_module_file(
            path, warnings, resolve_ha_includes=resolve_ha_includes
        )
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        if not valid:
            invalid_module_files.add(rel_path)
            continue
        module_items_by_file[rel_path] = items
        for item in items:
            if item.ha_id in module_items_by_id:
                warnings.append(
                    f"Duplicate {spec.key} id {item.ha_id} in {rel_path}; keeping first."
                )
                continue
            module_items_by_id[item.ha_id] = item

    domain_items, _domain_data, _domain_injected, domain_valid = _parse_mapping_domain(
        spec, warnings, resolve_ha_includes=resolve_ha_includes
    )
    domain_items_by_id: dict[str, ModuleItem] = {}
    if domain_valid:
        for item in domain_items:
            if item.ha_id in domain_items_by_id:
                warnings.append(
                    f"Duplicate {spec.key} id {item.ha_id} in {spec.domain_file.relative_to(settings.CONFIG_DIR)}."
                )
                continue
            domain_items_by_id[item.ha_id] = item

    if not domain_valid and not module_items_by_file:
        return changed_files

    unassigned_path = _ensure_unassigned_path(spec.module_dir, spec, warnings, preview)
    unassigned_rel = unassigned_path.relative_to(settings.CONFIG_DIR).as_posix()
    mapping, mapping_warnings = _load_mapping(spec.key, unassigned_rel)
    warnings.extend(mapping_warnings)

    mapping_index: dict[str, dict[str, Any]] = {}
    for entry in mapping.get("entries", []):
        key = _mapping_entry_key(entry)
        if not key or key == "None":
            continue
        mapping_index[key] = dict(entry)

    for item in module_items_by_id.values():
        mapping_index[item.ha_id] = {
            "id": item.ha_id,
            "source": item.source,
            "name": item.name,
            "fingerprint": item.fingerprint,
        }

    for item in domain_items_by_id.values():
        if item.ha_id in mapping_index:
            continue
        mapping_index[item.ha_id] = {"id": item.ha_id, "source": unassigned_rel}

    domain_hash = file_hash(spec.domain_file)
    modules_digest = modules_hash(module_files)
    domain_state = state.get("domains", {}).get(spec.key, {})
    stored_domain_hash = domain_state.get("domain_hash")
    stored_modules_hash = domain_state.get("modules_hash")
    has_state = stored_domain_hash is not None or stored_modules_hash is not None
    domain_changed = domain_valid and (stored_domain_hash != domain_hash)
    modules_changed = stored_modules_hash != modules_digest
    preference = _decide_preference(
        has_state,
        domain_changed,
        modules_changed,
        spec.domain_file.exists() and domain_valid,
        bool(module_files),
    )
    preference = _resolve_preference(preference_override, preference)
    write_modules = _should_write_target(write_mode, "modules")
    write_domain = _should_write_target(write_mode, "domain")
    exclude_keys: set[str] = set()

    desired_items_by_file: dict[str, list[ModuleItem]] = {rel: [] for rel in module_items_by_file}
    for entry in mapping_index.values():
        source = entry.get("source") or unassigned_rel
        desired_items_by_file.setdefault(source, [])
        item_id = entry.get("id")
        if not item_id:
            continue
        module_item = module_items_by_id.get(item_id)
        domain_item = domain_items_by_id.get(item_id)

        if domain_item is None:
            if preference == "domain":
                continue
            if preference == "mixed" and source == unassigned_rel:
                continue
            if module_item:
                desired_items_by_file[source].append(module_item)
            continue

        if preference == "domain":
            if module_item and _contains_template_includes(module_item.data):
                include_site_path = settings.CONFIG_DIR / module_item.source
                merged_data = _merge_domain_value_preserving_templates(
                    module_item.data,
                    domain_item.data,
                    include_site_path=include_site_path,
                    include_site_rel=module_item.source,
                    domain_site_rel=domain_item.source,
                    domain_line=None,
                    warnings=warnings,
                    edits=template_edits,
                )
                merged_expanded = expand_includes(
                    merged_data,
                    config_dir=settings.CONFIG_DIR,
                    base_path=include_site_path,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=False,
                )
                desired_items_by_file[source].append(
                    ModuleItem(
                        ha_id=domain_item.ha_id,
                        data=merged_data,
                        source=module_item.source,
                        order=domain_item.order,
                        name=_item_name(merged_expanded),
                        fingerprint=_fingerprint(merged_expanded, exclude_keys),
                        expanded=merged_expanded,
                    )
                )
            else:
                desired_items_by_file[source].append(domain_item)
        elif preference == "modules":
            if module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"{spec.key} {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)
        else:
            if source == unassigned_rel:
                if module_item and _contains_template_includes(module_item.data):
                    include_site_path = settings.CONFIG_DIR / module_item.source
                    merged_data = _merge_domain_value_preserving_templates(
                        module_item.data,
                        domain_item.data,
                        include_site_path=include_site_path,
                        include_site_rel=module_item.source,
                        domain_site_rel=domain_item.source,
                        domain_line=None,
                        warnings=warnings,
                        edits=template_edits,
                    )
                    merged_expanded = expand_includes(
                        merged_data,
                        config_dir=settings.CONFIG_DIR,
                        base_path=include_site_path,
                        warnings=warnings,
                        resolve_templates=True,
                        resolve_ha_includes=False,
                    )
                    desired_items_by_file[source].append(
                        ModuleItem(
                            ha_id=domain_item.ha_id,
                            data=merged_data,
                            source=module_item.source,
                            order=domain_item.order,
                            name=_item_name(merged_expanded),
                            fingerprint=_fingerprint(merged_expanded, exclude_keys),
                            expanded=merged_expanded,
                        )
                    )
                else:
                    desired_items_by_file[source].append(domain_item)
            elif module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"{spec.key} {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)

    for rel_path, items in desired_items_by_file.items():
        if rel_path in invalid_module_files:
            continue
        payload: dict[str, Any] = {
            item.ha_id: item.data for item in sorted(items, key=lambda item: item.order)
        }
        if write_modules and _write_yaml(settings.CONFIG_DIR / rel_path, payload, preview):
            changed_files.append(rel_path)

    combined: dict[str, Any] = {}
    for rel_path in sorted(desired_items_by_file.keys()):
        for item in sorted(desired_items_by_file[rel_path], key=lambda item: item.order):
            if item.ha_id in combined:
                warnings.append(
                    f"Duplicate {spec.key} id {item.ha_id} across modules; keeping first."
                )
                continue
            if item.expanded is None or item.expanded is SKIP:
                warnings.append(
                    f"Skipping {spec.key} {item.ha_id} due to template expansion failure."
                )
                continue
            combined[item.ha_id] = item.expanded
    if write_modules:
        changed_files.extend(_write_template_diffs(template_edits, warnings, preview))
    if write_domain and _write_domain_yaml(spec.domain_file, combined, preview):
        changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())

    entries: list[dict[str, Any]] = []
    for rel_path, items in desired_items_by_file.items():
        for item in sorted(items, key=lambda item: item.order):
            entry: dict[str, Any] = {"id": item.ha_id, "source": rel_path}
            if item.name:
                entry["name"] = item.name
            if item.fingerprint:
                entry["fingerprint"] = item.fingerprint
            entries.append(entry)
    entries.sort(key=lambda entry: entry.get("id") or "")
    mapping["entries"] = entries
    _save_mapping(spec.key, mapping, preview=preview is not None)

    module_hash_paths = {Path(path) for path in module_files}
    module_hash_paths.update(settings.CONFIG_DIR / rel for rel in desired_items_by_file)
    state.setdefault("domains", {})[spec.key] = {
        "domain_hash": file_hash(spec.domain_file),
        "modules_hash": modules_hash(sorted(module_hash_paths)),
    }
    return changed_files


def _sync_lovelace_domain(
    spec: DomainSpec,
    state: dict[str, Any],
    warnings: list[str],
    preview: dict[str, str] | None = None,
    preference_override: str | None = None,
    write_mode: str = "all",
) -> list[str]:
    changed_files: list[str] = []
    module_files = _list_module_files(spec)
    template_edits: list[TemplateEditCandidate] = []
    lovelace_modules: dict[str, LovelaceModule] = {}
    module_items_by_id: dict[str, ModuleItem] = {}
    modules_injected = False
    meta_source: str | None = None
    invalid_module_files: set[str] = set()

    for path in module_files:
        module = _parse_lovelace_module(path, warnings)
        if not module.valid:
            invalid_module_files.add(module.rel_path)
            continue
        lovelace_modules[module.rel_path] = module
        if module.changed:
            modules_injected = True
        if module.meta and not meta_source:
            meta_source = module.rel_path
        for item in module.views:
            if item.ha_id in module_items_by_id:
                warnings.append(
                    f"Duplicate lovelace view {item.ha_id} in {module.rel_path}; keeping first."
                )
                continue
            module_items_by_id[item.ha_id] = item

    domain_items, domain_meta, domain_injected, domain_valid = _parse_lovelace_domain(
        spec, warnings
    )
    domain_items_by_id: dict[str, ModuleItem] = {}
    if domain_valid:
        for item in domain_items:
            if item.ha_id in domain_items_by_id:
                warnings.append(
                    f"Duplicate lovelace view {item.ha_id} in {spec.domain_file.relative_to(settings.CONFIG_DIR)}."
                )
                continue
            domain_items_by_id[item.ha_id] = item

    if not domain_valid and not lovelace_modules:
        return changed_files

    unassigned_path = _ensure_unassigned_path(spec.module_dir, spec, warnings, preview)
    unassigned_rel = unassigned_path.relative_to(settings.CONFIG_DIR).as_posix()
    mapping, mapping_warnings = _load_mapping(spec.key, unassigned_rel)
    warnings.extend(mapping_warnings)

    mapping_index: dict[str, dict[str, Any]] = {}
    for entry in mapping.get("entries", []):
        key = _mapping_entry_key(entry)
        if not key or key == "None":
            continue
        mapping_index[key] = dict(entry)

    for item in module_items_by_id.values():
        mapping_index[item.ha_id] = {
            "id": item.ha_id,
            "source": item.source,
            "name": item.name,
            "fingerprint": item.fingerprint,
        }

    for item in domain_items_by_id.values():
        if item.ha_id in mapping_index:
            continue
        mapping_index[item.ha_id] = {"id": item.ha_id, "source": unassigned_rel}

    domain_hash = file_hash(spec.domain_file)
    modules_digest = modules_hash(module_files)
    domain_state = state.get("domains", {}).get(spec.key, {})
    stored_domain_hash = domain_state.get("domain_hash")
    stored_modules_hash = domain_state.get("modules_hash")
    has_state = stored_domain_hash is not None or stored_modules_hash is not None
    domain_changed = domain_valid and (domain_injected or (stored_domain_hash != domain_hash))
    modules_changed = modules_injected or (stored_modules_hash != modules_digest)
    preference = _decide_preference(
        has_state,
        domain_changed,
        modules_changed,
        spec.domain_file.exists() and domain_valid,
        bool(module_files),
    )
    preference = _resolve_preference(preference_override, preference)
    write_modules = _should_write_target(write_mode, "modules")
    write_domain = _should_write_target(write_mode, "domain")
    exclude_keys = {spec.id_field} if spec.id_field else set()

    desired_items_by_file: dict[str, list[ModuleItem]] = {rel: [] for rel in lovelace_modules}
    for entry in mapping_index.values():
        source = entry.get("source") or unassigned_rel
        desired_items_by_file.setdefault(source, [])
        item_id = entry.get("id")
        if not item_id:
            continue
        module_item = module_items_by_id.get(item_id)
        domain_item = domain_items_by_id.get(item_id)

        if domain_item is None:
            if preference == "domain":
                continue
            if preference == "mixed" and source == unassigned_rel:
                continue
            if module_item:
                desired_items_by_file[source].append(module_item)
            continue

        if preference == "domain":
            if module_item and _contains_template_includes(module_item.data):
                include_site_path = settings.CONFIG_DIR / module_item.source
                merged_data = _merge_domain_value_preserving_templates(
                    module_item.data,
                    domain_item.data,
                    include_site_path=include_site_path,
                    include_site_rel=module_item.source,
                    domain_site_rel=domain_item.source,
                    domain_line=domain_item.line,
                    warnings=warnings,
                    edits=template_edits,
                )
                merged_expanded = expand_includes(
                    merged_data,
                    config_dir=settings.CONFIG_DIR,
                    base_path=include_site_path,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=False,
                )
                desired_items_by_file[source].append(
                    ModuleItem(
                        ha_id=domain_item.ha_id,
                        data=merged_data,
                        source=module_item.source,
                        order=domain_item.order,
                        name=_item_name(merged_expanded),
                        fingerprint=_fingerprint(merged_expanded, exclude_keys),
                        expanded=merged_expanded,
                        line=domain_item.line,
                    )
                )
            else:
                desired_items_by_file[source].append(domain_item)
        elif preference == "modules":
            if module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"lovelace view {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)
        else:
            if source == unassigned_rel:
                if module_item and _contains_template_includes(module_item.data):
                    include_site_path = settings.CONFIG_DIR / module_item.source
                    merged_data = _merge_domain_value_preserving_templates(
                        module_item.data,
                        domain_item.data,
                        include_site_path=include_site_path,
                        include_site_rel=module_item.source,
                        domain_site_rel=domain_item.source,
                        domain_line=domain_item.line,
                        warnings=warnings,
                        edits=template_edits,
                    )
                    merged_expanded = expand_includes(
                        merged_data,
                        config_dir=settings.CONFIG_DIR,
                        base_path=include_site_path,
                        warnings=warnings,
                        resolve_templates=True,
                        resolve_ha_includes=False,
                    )
                    desired_items_by_file[source].append(
                        ModuleItem(
                            ha_id=domain_item.ha_id,
                            data=merged_data,
                            source=module_item.source,
                            order=domain_item.order,
                            name=_item_name(merged_expanded),
                            fingerprint=_fingerprint(merged_expanded, exclude_keys),
                            expanded=merged_expanded,
                            line=domain_item.line,
                        )
                    )
                else:
                    desired_items_by_file[source].append(domain_item)
            elif module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"lovelace view {item_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)

    meta_target = meta_source or unassigned_rel
    meta_payload = {}
    if preference == "domain":
        meta_payload = domain_meta
    elif preference == "modules":
        if meta_source and meta_source in lovelace_modules:
            meta_payload = lovelace_modules[meta_source].meta
        else:
            meta_payload = domain_meta
    else:
        if meta_source and meta_source in lovelace_modules:
            meta_payload = lovelace_modules[meta_source].meta
        else:
            meta_payload = domain_meta

    for rel_path, items in desired_items_by_file.items():
        if rel_path in invalid_module_files:
            continue
        module = lovelace_modules.get(rel_path)
        shape = module.shape if module else "dict"
        views_payload = [item.data for item in sorted(items, key=lambda item: item.order)]
        if rel_path == meta_target:
            payload = {"views": views_payload, **meta_payload}
            shape = "dict"
        elif shape == "dict":
            payload = {"views": views_payload}
        else:
            payload = views_payload
        if write_modules and _write_yaml(settings.CONFIG_DIR / rel_path, payload, preview):
            changed_files.append(rel_path)

    combined_views: list[Any] = []
    for rel_path in sorted(desired_items_by_file.keys()):
        items = desired_items_by_file[rel_path]
        for item in sorted(items, key=lambda item: item.order):
            if item.expanded is None or item.expanded is SKIP:
                warnings.append(
                    f"Skipping lovelace view {item.ha_id} due to template expansion failure."
                )
                continue
            combined_views.append(item.expanded)
    domain_payload: dict[str, Any] = {"views": combined_views, **meta_payload}
    if write_modules:
        changed_files.extend(_write_template_diffs(template_edits, warnings, preview))
    if write_domain and _write_domain_yaml(spec.domain_file, domain_payload, preview):
        changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())

    entries: list[dict[str, Any]] = []
    for rel_path, items in desired_items_by_file.items():
        for item in sorted(items, key=lambda item: item.order):
            entry: dict[str, Any] = {"id": item.ha_id, "source": rel_path}
            if item.name:
                entry["name"] = item.name
            if item.fingerprint:
                entry["fingerprint"] = item.fingerprint
            entries.append(entry)
    entries.sort(key=lambda entry: entry.get("id") or "")
    mapping["entries"] = entries
    _save_mapping(spec.key, mapping, preview=preview is not None)

    module_hash_paths = {Path(path) for path in module_files}
    module_hash_paths.update(settings.CONFIG_DIR / rel for rel in desired_items_by_file)
    state.setdefault("domains", {})[spec.key] = {
        "domain_hash": file_hash(spec.domain_file),
        "modules_hash": modules_hash(sorted(module_hash_paths)),
    }
    return changed_files


def _sync_helpers(
    state: dict[str, Any],
    warnings: list[str],
    preview: dict[str, str] | None = None,
    preference_override: str | None = None,
    write_mode: str = "all",
) -> list[str]:
    changed_files: list[str] = []
    template_edits: list[TemplateEditCandidate] = []
    module_files: list[Path] = []
    if settings.PACKAGES_DIR.exists():
        for package_dir in sorted(settings.PACKAGES_DIR.iterdir()):
            if not package_dir.is_dir():
                continue
            candidate = package_dir / "helpers.yaml"
            if candidate.exists():
                module_files.append(candidate)
    helpers_dir = settings.CONFIG_DIR / "helpers"
    if helpers_dir.exists():
        module_files.extend(sorted(helpers_dir.glob("*.y*ml")))

    module_items_by_file: dict[str, list[ModuleItem]] = {}
    module_items_by_id: dict[str, ModuleItem] = {}
    invalid_module_files: set[str] = set()

    for path in module_files:
        data, _lines, error = yaml_load(path)
        if error:
            warnings.append(error)
            invalid_module_files.add(path.relative_to(settings.CONFIG_DIR).as_posix())
            continue
        if data is None:
            data = {}
        if not isinstance(data, dict):
            warnings.append(f"{path.relative_to(settings.CONFIG_DIR)} is not a map.")
            invalid_module_files.add(path.relative_to(settings.CONFIG_DIR).as_posix())
            continue
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        items: list[ModuleItem] = []
        for helper_type, helper_values in data.items():
            if helper_type not in HELPER_TYPES:
                continue
            if not isinstance(helper_values, dict):
                warnings.append(f"{rel_path} {helper_type} is not a map.")
                continue
            for idx, (key, value) in enumerate(helper_values.items()):
                item_id = str(key)
                expanded = expand_includes(
                    value,
                    config_dir=settings.CONFIG_DIR,
                    base_path=path,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=False,
                )
                if expanded is SKIP:
                    expanded = None
                name = _item_name(expanded)
                fingerprint = _fingerprint(expanded, set())
                item = ModuleItem(
                    ha_id=item_id,
                    data=value,
                    source=rel_path,
                    order=idx,
                    name=name,
                    fingerprint=fingerprint,
                    helper_type=helper_type,
                    expanded=expanded,
                )
                items.append(item)
                composite_id = f"{helper_type}:{item_id}"
                if composite_id in module_items_by_id:
                    warnings.append(
                        f"Duplicate helper {composite_id} in {rel_path}; keeping first."
                    )
                    continue
                module_items_by_id[composite_id] = item
        module_items_by_file[rel_path] = items

    domain_items_by_id: dict[str, ModuleItem] = {}
    for helper_type in HELPER_TYPES:
        path = settings.CONFIG_DIR / f"{helper_type}.yaml"
        data, _lines, error = yaml_load(path)
        if error:
            warnings.append(error)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            warnings.append(f"{path.relative_to(settings.CONFIG_DIR)} is not a map.")
            continue
        for idx, (key, value) in enumerate(data.items()):
            item_id = str(key)
            expanded = expand_includes(
                value,
                config_dir=settings.CONFIG_DIR,
                base_path=path,
                warnings=warnings,
                resolve_templates=True,
                resolve_ha_includes=False,
            )
            if expanded is SKIP:
                expanded = None
            item = ModuleItem(
                ha_id=item_id,
                data=value,
                source=path.relative_to(settings.CONFIG_DIR).as_posix(),
                order=idx,
                name=_item_name(expanded),
                fingerprint=_fingerprint(expanded, set()),
                helper_type=helper_type,
                expanded=expanded,
            )
            composite_id = f"{helper_type}:{item_id}"
            if composite_id in domain_items_by_id:
                warnings.append(
                    f"Duplicate helper {composite_id} in {path.relative_to(settings.CONFIG_DIR)}."
                )
                continue
            domain_items_by_id[composite_id] = item

    unassigned_path = _ensure_unassigned_path(helpers_dir, None, warnings, preview)
    unassigned_rel = unassigned_path.relative_to(settings.CONFIG_DIR).as_posix()
    mapping, mapping_warnings = _load_mapping(HELPERS_DOMAIN_KEY, unassigned_rel)
    warnings.extend(mapping_warnings)

    mapping_index: dict[str, dict[str, Any]] = {}
    for entry in mapping.get("entries", []):
        key = _mapping_entry_key(entry)
        if not key or key == "None":
            continue
        mapping_index[key] = dict(entry)

    for item in module_items_by_id.values():
        composite_id = f"{item.helper_type}:{item.ha_id}"
        mapping_index[composite_id] = {
            "id": item.ha_id,
            "helper_type": item.helper_type,
            "source": item.source,
            "name": item.name,
            "fingerprint": item.fingerprint,
        }

    for composite_id, item in domain_items_by_id.items():
        if composite_id in mapping_index:
            continue
        mapping_index[composite_id] = {
            "id": item.ha_id,
            "helper_type": item.helper_type,
            "source": unassigned_rel,
        }

    domain_hash = modules_hash([settings.CONFIG_DIR / f"{helper}.yaml" for helper in HELPER_TYPES])
    modules_digest = modules_hash(module_files)
    domain_state = state.get("domains", {}).get(HELPERS_DOMAIN_KEY, {})
    stored_domain_hash = domain_state.get("domain_hash")
    stored_modules_hash = domain_state.get("modules_hash")
    has_state = stored_domain_hash is not None or stored_modules_hash is not None
    domain_changed = stored_domain_hash != domain_hash
    modules_changed = stored_modules_hash != modules_digest
    preference = _decide_preference(
        has_state,
        domain_changed,
        modules_changed,
        any((settings.CONFIG_DIR / f"{helper}.yaml").exists() for helper in HELPER_TYPES),
        bool(module_files),
    )
    preference = _resolve_preference(preference_override, preference)
    write_modules = _should_write_target(write_mode, "modules")
    write_domain = _should_write_target(write_mode, "domain")
    exclude_keys: set[str] = set()

    desired_items_by_file: dict[str, list[ModuleItem]] = {rel: [] for rel in module_items_by_file}
    for composite_id, entry in mapping_index.items():
        source = entry.get("source") or unassigned_rel
        desired_items_by_file.setdefault(source, [])
        helper_type = entry.get("helper_type")
        item_id = entry.get("id")
        if not helper_type or not item_id:
            continue
        module_item = module_items_by_id.get(composite_id)
        domain_item = domain_items_by_id.get(composite_id)

        if domain_item is None:
            if preference == "domain":
                continue
            if preference == "mixed" and source == unassigned_rel:
                continue
            if module_item:
                desired_items_by_file[source].append(module_item)
            continue

        if preference == "domain":
            if module_item and _contains_template_includes(module_item.data):
                include_site_path = settings.CONFIG_DIR / module_item.source
                merged_data = _merge_domain_value_preserving_templates(
                    module_item.data,
                    domain_item.data,
                    include_site_path=include_site_path,
                    include_site_rel=module_item.source,
                    domain_site_rel=domain_item.source,
                    domain_line=None,
                    warnings=warnings,
                    edits=template_edits,
                )
                merged_expanded = expand_includes(
                    merged_data,
                    config_dir=settings.CONFIG_DIR,
                    base_path=include_site_path,
                    warnings=warnings,
                    resolve_templates=True,
                    resolve_ha_includes=False,
                )
                desired_items_by_file[source].append(
                    ModuleItem(
                        ha_id=domain_item.ha_id,
                        data=merged_data,
                        source=module_item.source,
                        order=domain_item.order,
                        name=_item_name(merged_expanded),
                        fingerprint=_fingerprint(merged_expanded, exclude_keys),
                        helper_type=domain_item.helper_type,
                        expanded=merged_expanded,
                    )
                )
            else:
                desired_items_by_file[source].append(domain_item)
        elif preference == "modules":
            if module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"helper {composite_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)
        else:
            if source == unassigned_rel:
                if module_item and _contains_template_includes(module_item.data):
                    include_site_path = settings.CONFIG_DIR / module_item.source
                    merged_data = _merge_domain_value_preserving_templates(
                        module_item.data,
                        domain_item.data,
                        include_site_path=include_site_path,
                        include_site_rel=module_item.source,
                        domain_site_rel=domain_item.source,
                        domain_line=None,
                        warnings=warnings,
                        edits=template_edits,
                    )
                    merged_expanded = expand_includes(
                        merged_data,
                        config_dir=settings.CONFIG_DIR,
                        base_path=include_site_path,
                        warnings=warnings,
                        resolve_templates=True,
                        resolve_ha_includes=False,
                    )
                    desired_items_by_file[source].append(
                        ModuleItem(
                            ha_id=domain_item.ha_id,
                            data=merged_data,
                            source=module_item.source,
                            order=domain_item.order,
                            name=_item_name(merged_expanded),
                            fingerprint=_fingerprint(merged_expanded, exclude_keys),
                            helper_type=domain_item.helper_type,
                            expanded=merged_expanded,
                        )
                    )
                else:
                    desired_items_by_file[source].append(domain_item)
            elif module_item:
                desired_items_by_file[source].append(module_item)
            else:
                warnings.append(
                    f"helper {composite_id} missing from modules; keeping domain version."
                )
                desired_items_by_file[source].append(domain_item)

    if write_modules:
        changed_files.extend(_write_template_diffs(template_edits, warnings, preview))

    for rel_path, items in desired_items_by_file.items():
        if rel_path in invalid_module_files:
            continue
        payload: dict[str, Any] = {}
        for helper_type in HELPER_TYPES:
            entries = [item for item in items if item.helper_type == helper_type]
            if not entries:
                continue
            payload[helper_type] = {
                item.ha_id: item.data for item in sorted(entries, key=lambda item: item.order)
            }
        if write_modules and _write_yaml(settings.CONFIG_DIR / rel_path, payload, preview):
            changed_files.append(rel_path)

    for helper_type in HELPER_TYPES:
        combined: dict[str, Any] = {}
        for rel_path in sorted(desired_items_by_file.keys()):
            entries = [
                item for item in desired_items_by_file[rel_path] if item.helper_type == helper_type
            ]
            for item in sorted(entries, key=lambda item: item.order):
                if item.ha_id in combined:
                    warnings.append(
                        f"Duplicate helper {helper_type}:{item.ha_id} across modules; keeping first."
                    )
                    continue
                if item.expanded is None or item.expanded is SKIP:
                    warnings.append(
                        f"Skipping helper {helper_type}:{item.ha_id} due to template expansion failure."
                    )
                    continue
                combined[item.ha_id] = item.expanded
        domain_path = settings.CONFIG_DIR / f"{helper_type}.yaml"
        if write_domain and _write_domain_yaml(domain_path, combined, preview):
            changed_files.append(domain_path.relative_to(settings.CONFIG_DIR).as_posix())

    entries: list[dict[str, Any]] = []
    for rel_path, items in desired_items_by_file.items():
        for item in sorted(items, key=lambda item: item.order):
            entry: dict[str, Any] = {
                "id": item.ha_id,
                "source": rel_path,
                "helper_type": item.helper_type,
            }
            if item.name:
                entry["name"] = item.name
            if item.fingerprint:
                entry["fingerprint"] = item.fingerprint
            entries.append(entry)
    entries.sort(key=lambda entry: (entry.get("helper_type") or "", entry.get("id") or ""))
    mapping["entries"] = entries
    _save_mapping(HELPERS_DOMAIN_KEY, mapping, preview=preview is not None)

    module_hash_paths = {Path(path) for path in module_files}
    module_hash_paths.update(settings.CONFIG_DIR / rel for rel in desired_items_by_file)
    state.setdefault("domains", {})[HELPERS_DOMAIN_KEY] = {
        "domain_hash": modules_hash([settings.CONFIG_DIR / f"{helper}.yaml" for helper in HELPER_TYPES]),
        "modules_hash": modules_hash(sorted(module_hash_paths)),
    }
    return changed_files


def reconcile_automation_ids() -> dict[str, Any]:
    """Align module automation IDs to HA-written IDs using fingerprint matching."""
    warnings: list[str] = []
    changed_files: list[str] = []
    reconciled: list[dict[str, str]] = []

    spec = next(domain for domain in YAML_MODULE_DOMAINS if domain.key == "automation")
    if not spec.id_field:
        return {
            "status": "skipped",
            "reason": "Automation domain has no id field.",
            "changed_files": [],
            "warnings": warnings,
            "reconciled_ids": reconciled,
        }

    module_files = _list_module_files(spec)
    if not module_files:
        return {
            "status": "skipped",
            "reason": "No automation module files found.",
            "changed_files": [],
            "warnings": warnings,
            "reconciled_ids": reconciled,
        }

    module_items_by_file: dict[str, list[ModuleItem]] = {}
    module_items: list[ModuleItem] = []
    for path in module_files:
        items, _data, _injected, valid = _parse_list_module_file(path, spec, warnings)
        if not valid:
            continue
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        module_items_by_file[rel_path] = items
        module_items.extend(items)

    domain_items, _domain_data, _domain_injected, domain_valid = _parse_list_domain(
        spec, warnings
    )
    if not domain_valid:
        return {
            "status": "skipped",
            "reason": "automations.yaml is invalid.",
            "changed_files": [],
            "warnings": warnings,
            "reconciled_ids": reconciled,
        }

    module_by_fp: dict[str, list[ModuleItem]] = {}
    for item in module_items:
        if not item.fingerprint:
            continue
        module_by_fp.setdefault(item.fingerprint, []).append(item)

    domain_by_fp: dict[str, list[ModuleItem]] = {}
    for item in domain_items:
        if not item.fingerprint:
            continue
        domain_by_fp.setdefault(item.fingerprint, []).append(item)

    for fingerprint, module_matches in module_by_fp.items():
        domain_matches = domain_by_fp.get(fingerprint, [])
        if len(module_matches) == 1 and len(domain_matches) == 1:
            module_item = module_matches[0]
            domain_item = domain_matches[0]
            if module_item.ha_id != domain_item.ha_id:
                old_id = module_item.ha_id
                module_item.data[spec.id_field] = domain_item.ha_id
                module_item.ha_id = domain_item.ha_id
                reconciled.append(
                    {
                        "old_id": old_id,
                        "new_id": domain_item.ha_id,
                        "source": module_item.source,
                        "name": module_item.name or "",
                    }
                )
            continue
        if domain_matches and module_matches:
            warnings.append(
                "Ambiguous automation ID reconciliation for fingerprint "
                f"{fingerprint}; skipping."
            )

    for rel_path, items in module_items_by_file.items():
        payload = [item.data for item in sorted(items, key=lambda item: item.order)]
        if write_yaml_if_changed(settings.CONFIG_DIR / rel_path, payload):
            changed_files.append(rel_path)

    status = "reconciled" if reconciled else "no_changes"
    return {
        "status": status,
        "changed_files": changed_files,
        "warnings": warnings,
        "reconciled_ids": reconciled,
    }


def _sync_yaml_modules_state(
    state: dict[str, Any],
    warnings: list[str],
    preview: dict[str, str] | None = None,
    preference_override: str | None = None,
    write_mode: str = "all",
) -> list[str]:
    changed_files: list[str] = []
    for spec in YAML_MODULE_DOMAINS:
        if spec.kind == "list":
            changed_files.extend(
                _sync_list_domain(
                    spec,
                    state,
                    warnings,
                    preview=preview,
                    preference_override=preference_override,
                    write_mode=write_mode,
                )
            )
        elif spec.kind == "mapping":
            changed_files.extend(
                _sync_mapping_domain(
                    spec,
                    state,
                    warnings,
                    preview=preview,
                    preference_override=preference_override,
                    write_mode=write_mode,
                )
            )
        elif spec.kind == "lovelace":
            changed_files.extend(
                _sync_lovelace_domain(
                    spec,
                    state,
                    warnings,
                    preview=preview,
                    preference_override=preference_override,
                    write_mode=write_mode,
                )
            )

    changed_files.extend(
        _sync_helpers(
            state,
            warnings,
            preview=preview,
            preference_override=preference_override,
            write_mode=write_mode,
        )
    )
    return changed_files


def sync_yaml_modules() -> dict[str, Any]:
    warnings: list[str] = []
    changed_files: list[str] = []
    _maybe_migrate_automation_markers(warnings)
    state, state_warnings = _load_sync_state()
    warnings.extend(state_warnings)
    changed_files.extend(_sync_yaml_modules_state(state, warnings))
    _save_sync_state(state)
    return {
        "status": "synced",
        "changed_files": sorted(set(changed_files)),
        "warnings": warnings,
    }


def build_yaml_modules() -> dict[str, Any]:
    """Build domain YAML from module files."""
    warnings: list[str] = []
    changed_files: list[str] = []
    _maybe_migrate_automation_markers(warnings)
    state, state_warnings = _load_sync_state()
    warnings.extend(state_warnings)
    changed_files.extend(
        _sync_yaml_modules_state(
            state,
            warnings,
            preference_override="modules",
            write_mode="domain",
        )
    )
    _save_sync_state(state)
    return {
        "status": "built",
        "changed_files": sorted(set(changed_files)),
        "warnings": warnings,
    }


def update_yaml_modules() -> dict[str, Any]:
    """Update module YAML from domain files."""
    warnings: list[str] = []
    changed_files: list[str] = []
    _maybe_migrate_automation_markers(warnings)
    state, state_warnings = _load_sync_state()
    warnings.extend(state_warnings)
    changed_files.extend(
        _sync_yaml_modules_state(
            state,
            warnings,
            preference_override="domain",
            write_mode="modules",
        )
    )
    _save_sync_state(state)
    return {
        "status": "updated",
        "changed_files": sorted(set(changed_files)),
        "warnings": warnings,
    }


def _domain_yaml_paths() -> set[str]:
    paths = {
        spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix()
        for spec in YAML_MODULE_DOMAINS
    }
    paths.update(f"{helper}.yaml" for helper in HELPER_TYPES)
    return paths


def _is_preview_path(rel_path: str) -> bool:
    if rel_path.startswith(".gitops/"):
        return False
    if rel_path.startswith("system/"):
        return False
    return rel_path.endswith((".yaml", ".yml", ".diff"))


def _build_preview_diff(rel_path: str, new_content: str) -> str:
    old_content = read_text(settings.CONFIG_DIR / rel_path)
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    diff_text = "\n".join(diff_lines)
    return f"diff --git a/{rel_path} b/{rel_path}\n{diff_text}\n"


def preview_yaml_modules() -> dict[str, Any]:
    """Return diffs for a YAML Modules sync without writing files."""
    warnings: list[str] = []
    preview_writes: dict[str, str] = {}
    if _needs_automation_marker_migration():
        warnings.append(
            "Preview skipped marker-based automation migration. Run sync to apply it."
        )
    state, state_warnings = _load_sync_state()
    warnings.extend(state_warnings)
    _sync_yaml_modules_state(state, warnings, preview=preview_writes)

    domain_paths = _domain_yaml_paths()
    build_diffs: list[dict[str, Any]] = []
    update_diffs: list[dict[str, Any]] = []
    for rel_path, new_content in preview_writes.items():
        if not _is_preview_path(rel_path):
            continue
        diff = _build_preview_diff(rel_path, new_content)
        if not diff.strip():
            continue
        entry = {"path": rel_path, "diff": diff}
        if rel_path in domain_paths:
            build_diffs.append(entry)
        else:
            update_diffs.append(entry)

    build_diffs.sort(key=lambda item: item["path"])
    update_diffs.sort(key=lambda item: item["path"])
    return {
        "status": "preview",
        "build_diffs": build_diffs,
        "update_diffs": update_diffs,
        "warnings": warnings,
    }


def _plan_yaml_modules(
    preference_override: str | None,
    write_mode: str,
) -> dict[str, Any]:
    warnings: list[str] = []
    preview_writes: dict[str, str] = {}
    if _needs_automation_marker_migration():
        warnings.append(
            "Preview skipped marker-based automation migration. Run sync to apply it."
        )
    state, state_warnings = _load_sync_state()
    warnings.extend(state_warnings)
    changed_files = _sync_yaml_modules_state(
        state,
        warnings,
        preview=preview_writes,
        preference_override=preference_override,
        write_mode=write_mode,
    )
    return {
        "changed_files": sorted(set(changed_files)),
        "warnings": warnings,
    }


def _dedupe_lines(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def validate_yaml_modules() -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "ok",
        "errors": [],
        "warnings": [],
        "domains": {},
        "build": {},
        "update": {},
        "summary": {"errors": 0, "warnings": 0},
    }

    state, state_warnings = _load_sync_state()
    if state_warnings:
        report["warnings"].extend([f"sync_state: {warning}" for warning in state_warnings])

    for spec in YAML_MODULE_DOMAINS:
        domain_warnings: list[str] = []
        domain_errors: list[str] = []
        preview: dict[str, str] = {}
        try:
            if spec.kind == "list":
                changed_files = _sync_list_domain(
                    spec,
                    state,
                    domain_warnings,
                    preview=preview,
                    write_mode="all",
                )
            elif spec.kind == "mapping":
                changed_files = _sync_mapping_domain(
                    spec,
                    state,
                    domain_warnings,
                    preview=preview,
                    write_mode="all",
                )
            elif spec.kind == "lovelace":
                changed_files = _sync_lovelace_domain(
                    spec,
                    state,
                    domain_warnings,
                    preview=preview,
                    write_mode="all",
                )
            else:
                changed_files = []
        except Exception as exc:
            domain_errors.append(str(exc))
            changed_files = []
        report["domains"][spec.key] = {
            "warnings": domain_warnings,
            "errors": domain_errors,
            "changed_files": sorted(set(changed_files)),
        }
        report["errors"].extend([f"{spec.key}: {error}" for error in domain_errors])
        report["warnings"].extend([f"{spec.key}: {warning}" for warning in domain_warnings])

    helpers_warnings: list[str] = []
    helpers_errors: list[str] = []
    helpers_preview: dict[str, str] = {}
    try:
        helpers_changed = _sync_helpers(
            state,
            helpers_warnings,
            preview=helpers_preview,
            write_mode="all",
        )
    except Exception as exc:
        helpers_errors.append(str(exc))
        helpers_changed = []

    report["domains"]["helpers"] = {
        "warnings": helpers_warnings,
        "errors": helpers_errors,
        "changed_files": sorted(set(helpers_changed)),
    }
    report["errors"].extend([f"helpers: {error}" for error in helpers_errors])
    report["warnings"].extend([f"helpers: {warning}" for warning in helpers_warnings])

    build_plan = _plan_yaml_modules("modules", "domain")
    update_plan = _plan_yaml_modules("domain", "modules")
    report["build"] = {
        "count": len(build_plan["changed_files"]),
        "paths": build_plan["changed_files"],
        "warnings": build_plan["warnings"],
    }
    report["update"] = {
        "count": len(update_plan["changed_files"]),
        "paths": update_plan["changed_files"],
        "warnings": update_plan["warnings"],
    }

    report["errors"] = _dedupe_lines(report["errors"])
    report["warnings"] = _dedupe_lines(report["warnings"])
    report["summary"] = {
        "errors": len(report["errors"]),
        "warnings": len(report["warnings"]),
    }
    if report["errors"] or report["warnings"]:
        report["status"] = "issues"
    return report


MODULE_BROWSER_DOMAINS = (
    "automations",
    "scripts",
    "groups",
    "scenes",
    "templates",
    "helpers",
    "lovelace",
)

MODULE_DOMAIN_MAP = {
    "automations": "automation",
    "scripts": "script",
    "groups": "group",
    "scenes": "scene",
    "templates": "template",
    "lovelace": "lovelace",
}


def _is_yaml_path(path: Path) -> bool:
    return path.suffix.lower() in settings.WATCH_EXTENSIONS


def _resolve_module_path(rel_path: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError("Module path must be a non-empty string.")
    candidate = Path(rel_path)
    if candidate.is_absolute():
        raise ValueError("Module path must be relative to the config directory.")
    if ".." in candidate.parts:
        raise ValueError("Module path cannot include parent directory segments.")
    if not _is_yaml_path(candidate):
        raise ValueError("Module path must point to a .yaml or .yml file.")
    if not candidate.parts or candidate.parts[0] not in {"packages", *MODULE_BROWSER_DOMAINS}:
        raise ValueError("Module path must live in packages or a YAML Modules domain folder.")
    resolved = (settings.CONFIG_DIR / candidate).resolve()
    try:
        resolved.relative_to(settings.CONFIG_DIR)
    except ValueError as exc:
        raise ValueError("Module path must stay within the config directory.") from exc
    return resolved


def _parse_item_yaml(payload: str) -> Any:
    try:
        return yaml.safe_load(payload)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc


def _select_list_item(
    items: list[ModuleItem], selector: dict[str, Any]
) -> tuple[int, ModuleItem]:
    target_id = selector.get("id")
    target_fp = selector.get("fingerprint")
    matches: list[tuple[int, ModuleItem]] = []
    for idx, item in enumerate(items):
        if target_id and item.ha_id != target_id:
            continue
        if target_fp and item.fingerprint != target_fp:
            continue
        matches.append((idx, item))
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("Item not found. Refresh the item list and try again.")
    raise ValueError("Item match is ambiguous. Refresh the item list and try again.")


def _list_items_from_helpers_file(
    path: Path, warnings: list[str]
) -> list[dict[str, Any]]:
    data, _lines, error = yaml_load(path)
    if error:
        warnings.append(error)
        return []
    if data is None:
        data = {}
    if not isinstance(data, dict):
        warnings.append(f"{path.relative_to(settings.CONFIG_DIR)} is not a map.")
        return []
    items: list[dict[str, Any]] = []
    for helper_type, helper_values in data.items():
        if helper_type not in HELPER_TYPES:
            continue
        if not isinstance(helper_values, dict):
            warnings.append(f"{path.relative_to(settings.CONFIG_DIR)} {helper_type} is not a map.")
            continue
        for key, value in helper_values.items():
            name = _item_name(value)
            fingerprint = _fingerprint(value, set())
            items.append(
                {
                    "selector": {
                        "type": "helper",
                        "helper_type": helper_type,
                        "key": str(key),
                    },
                    "id": str(key),
                    "name": name,
                    "fingerprint": fingerprint,
                    "helper_type": helper_type,
                }
            )
    return items


def list_module_items(rel_path: str) -> dict[str, Any]:
    path = _resolve_module_path(rel_path)
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    warnings: list[str] = []
    kind, spec = _module_file_context(path)

    if kind == "list" and spec:
        items, _data, _changed, valid = _parse_list_module_file(path, spec, warnings)
        if not valid:
            return {"path": rel_path, "file_kind": kind, "items": [], "warnings": warnings}
        payload = [
            {
                "selector": {
                    "type": "list_id",
                    "id": item.ha_id,
                    "fingerprint": item.fingerprint,
                },
                "id": item.ha_id,
                "name": item.name,
                "fingerprint": item.fingerprint,
            }
            for item in items
        ]
        return {"path": rel_path, "file_kind": kind, "items": payload, "warnings": warnings}

    if kind == "mapping" and spec:
        items, _data, _changed, valid = _parse_mapping_module_file(
            path, warnings, resolve_ha_includes=spec.key == "group"
        )
        if not valid:
            return {"path": rel_path, "file_kind": kind, "items": [], "warnings": warnings}
        payload = [
            {
                "selector": {"type": "map_key", "key": item.ha_id},
                "id": item.ha_id,
                "name": item.name,
                "fingerprint": item.fingerprint,
            }
            for item in items
        ]
        return {"path": rel_path, "file_kind": kind, "items": payload, "warnings": warnings}

    if kind == "lovelace":
        module = _parse_lovelace_module(path, warnings)
        if not module.valid:
            return {"path": rel_path, "file_kind": kind, "items": [], "warnings": warnings}
        payload = [
            {
                "selector": {
                    "type": "lovelace_view",
                    "id": item.ha_id,
                    "fingerprint": item.fingerprint,
                },
                "id": item.ha_id,
                "name": item.name,
                "fingerprint": item.fingerprint,
            }
            for item in module.views
        ]
        return {"path": rel_path, "file_kind": kind, "items": payload, "warnings": warnings}

    if kind == "helpers":
        return {
            "path": rel_path,
            "file_kind": kind,
            "items": _list_items_from_helpers_file(path, warnings),
            "warnings": warnings,
        }

    raise ValueError("Unsupported module file type.")


def read_module_item(rel_path: str, selector: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(selector, dict):
        raise ValueError("Selector must be an object.")
    path = _resolve_module_path(rel_path)
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    kind, spec = _module_file_context(path)

    if kind == "list" and spec:
        items, _data, _changed, valid = _parse_list_module_file(path, spec, [])
        if not valid:
            raise ValueError("Module file is not a valid list.")
        _idx, item = _select_list_item(items, selector)
        return {
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "yaml": yaml_dump(item.data),
        }

    if kind == "mapping" and spec:
        _items, data, _changed, valid = _parse_mapping_module_file(
            path, [], resolve_ha_includes=spec.key == "group"
        )
        if not valid:
            raise ValueError("Module file is not a valid map.")
        key = selector.get("key")
        if not key:
            raise ValueError("Selector key is required.")
        if key not in data:
            raise ValueError("Item not found. Refresh the item list and try again.")
        value = data[key]
        return {
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "yaml": yaml_dump(value),
        }

    if kind == "helpers":
        data, _lines, error = yaml_load(path)
        if error:
            raise ValueError(error)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Module file is not a valid helpers map.")
        helper_type = selector.get("helper_type")
        key = selector.get("key")
        if not helper_type or not key:
            raise ValueError("Selector helper_type and key are required.")
        helper_values = data.get(helper_type)
        if not isinstance(helper_values, dict) or key not in helper_values:
            raise ValueError("Item not found. Refresh the item list and try again.")
        return {
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "yaml": yaml_dump(helper_values[key]),
        }

    if kind == "lovelace":
        module = _parse_lovelace_module(path, [])
        if not module.valid:
            raise ValueError("Module file is not a valid lovelace module.")
        _idx, item = _select_list_item(module.views, selector)
        return {
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "yaml": yaml_dump(item.data),
        }

    raise ValueError("Unsupported module file type.")


def write_module_item(rel_path: str, selector: dict[str, Any], content: str) -> dict[str, Any]:
    if not isinstance(selector, dict):
        raise ValueError("Selector must be an object.")
    if not isinstance(content, str):
        raise ValueError("YAML content must be a string.")
    path = _resolve_module_path(rel_path)
    rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
    kind, spec = _module_file_context(path)

    item_data = _parse_item_yaml(content)
    if item_data is None:
        raise ValueError("YAML content is empty.")

    if kind == "list" and spec:
        if not isinstance(item_data, dict):
            raise ValueError("List items must be YAML maps.")
        data, _lines, error = yaml_load(path)
        if error:
            raise ValueError(error)
        if data is None:
            data = []
        if not isinstance(data, list):
            raise ValueError("Module file is not a list.")
        data_copy = copy.deepcopy(data)
        items, _changed = _parse_list_items(data_copy, None, rel_path, spec, [])
        index, _item = _select_list_item(items, selector)
        if spec.key == "automation" and spec.id_field:
            if not item_data.get(spec.id_field):
                candidate = _automation_alias_id(item_data)
                if not candidate:
                    candidate = _synthetic_id(rel_path, None, index)
                used_ids = {entry.ha_id for idx, entry in enumerate(items) if idx != index}
                fingerprint = _fingerprint(item_data, {spec.id_field})
                item_data[spec.id_field] = _ensure_unique_id(candidate, used_ids, fingerprint)
        data[index] = item_data
        _write_yaml(path, data, preview=None)
        return {
            "status": "saved",
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "fingerprint": _fingerprint(item_data, {spec.id_field} if spec.id_field else set()),
        }

    if kind == "mapping" and spec:
        if not isinstance(item_data, dict):
            raise ValueError("Map items must be YAML maps.")
        data, _lines, error = yaml_load(path)
        if error:
            raise ValueError(error)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Module file is not a map.")
        key = selector.get("key")
        if not key:
            raise ValueError("Selector key is required.")
        if key not in data:
            raise ValueError("Item not found. Refresh the item list and try again.")
        data[key] = item_data
        _write_yaml(path, data, preview=None)
        return {
            "status": "saved",
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "fingerprint": _fingerprint(item_data, set()),
        }

    if kind == "helpers":
        if not isinstance(item_data, dict):
            raise ValueError("Helper items must be YAML maps.")
        data, _lines, error = yaml_load(path)
        if error:
            raise ValueError(error)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("Module file is not a helpers map.")
        helper_type = selector.get("helper_type")
        key = selector.get("key")
        if not helper_type or not key:
            raise ValueError("Selector helper_type and key are required.")
        if helper_type not in HELPER_TYPES:
            raise ValueError("Unsupported helper type.")
        helper_values = data.get(helper_type)
        if helper_values is None:
            helper_values = {}
            data[helper_type] = helper_values
        if not isinstance(helper_values, dict):
            raise ValueError("Helper type is not a map.")
        if key not in helper_values:
            raise ValueError("Item not found. Refresh the item list and try again.")
        helper_values[key] = item_data
        _write_yaml(path, data, preview=None)
        return {
            "status": "saved",
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "fingerprint": _fingerprint(item_data, set()),
        }

    if kind == "lovelace":
        if not isinstance(item_data, dict):
            raise ValueError("Lovelace views must be YAML maps.")
        data, _lines, error = yaml_load(path)
        if error:
            raise ValueError(error)
        if data is None:
            data = []
        shape = "list"
        meta: dict[str, Any] = {}
        views: list[Any]
        if isinstance(data, list):
            views = data
        elif isinstance(data, dict):
            shape = "dict"
            views = data.get("views") or []
            if not isinstance(views, list):
                raise ValueError("Lovelace views are not a list.")
            meta = {key: value for key, value in data.items() if key != "views"}
        else:
            raise ValueError("Module file is not a valid lovelace module.")
        views_copy = copy.deepcopy(views)
        items, _changed = _parse_list_items(views_copy, None, rel_path, spec, [])
        index, _item = _select_list_item(items, selector)
        if spec and spec.id_field and not item_data.get(spec.id_field):
            selector_id = selector.get("id")
            if selector_id:
                item_data[spec.id_field] = selector_id
        views[index] = item_data
        payload = views if shape == "list" else {"views": views, **meta}
        _write_yaml(path, payload, preview=None)
        return {
            "status": "saved",
            "path": rel_path,
            "file_kind": kind,
            "selector": selector,
            "fingerprint": _fingerprint(item_data, {spec.id_field} if spec else set()),
        }

    raise ValueError("Unsupported module file type.")


def _selector_key(selector: dict[str, Any]) -> str:
    return json.dumps(selector, sort_keys=True)


def _select_list_item_flexible(
    items: list[ModuleItem], selector: dict[str, Any], allow_fingerprint_only: bool
) -> tuple[int, ModuleItem]:
    try:
        return _select_list_item(items, selector)
    except ValueError:
        if not allow_fingerprint_only:
            raise
    fingerprint = selector.get("fingerprint")
    if not fingerprint:
        raise ValueError("Item not found. Refresh the item list and try again.")
    matches = [(idx, item) for idx, item in enumerate(items) if item.fingerprint == fingerprint]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError("Item not found. Refresh the item list and try again.")
    raise ValueError("Item match is ambiguous. Refresh the item list and try again.")


def _remove_list_items(
    path: Path,
    spec: DomainSpec,
    selectors: list[dict[str, Any]],
    warnings: list[str],
    allow_fingerprint_only: bool,
) -> tuple[list[dict[str, Any]], list[Any]]:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ValueError("Module file is not a list.")
    data_copy = copy.deepcopy(data)
    items, _changed = _parse_list_items(data_copy, None, path.relative_to(settings.CONFIG_DIR).as_posix(), spec, warnings)
    removed: dict[str, dict[str, Any]] = {}
    indices: list[int] = []
    for selector in selectors:
        idx, item = _select_list_item_flexible(items, selector, allow_fingerprint_only)
        key = _selector_key(selector)
        removed[key] = {
            "data": data[idx],
            "id": item.ha_id,
            "fingerprint": item.fingerprint,
            "name": item.name,
            "selector": selector,
        }
        indices.append(idx)
    for idx in sorted(set(indices), reverse=True):
        data.pop(idx)
    ordered = [removed[_selector_key(selector)] for selector in selectors if _selector_key(selector) in removed]
    return ordered, data


def _remove_mapping_items(
    path: Path, selectors: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Module file is not a map.")
    removed: list[dict[str, Any]] = []
    for selector in selectors:
        key = selector.get("key")
        if not key:
            raise ValueError("Selector key is required.")
        if key not in data:
            raise ValueError("Item not found. Refresh the item list and try again.")
        removed.append(
            {
                "data": data[key],
                "id": str(key),
                "key": str(key),
                "selector": selector,
            }
        )
    for selector in selectors:
        key = selector.get("key")
        if key in data:
            data.pop(key)
    return removed, data


def _remove_helpers_items(
    path: Path, selectors: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Module file is not a helpers map.")
    removed: list[dict[str, Any]] = []
    for selector in selectors:
        helper_type = selector.get("helper_type")
        key = selector.get("key")
        if not helper_type or not key:
            raise ValueError("Selector helper_type and key are required.")
        helper_values = data.get(helper_type)
        if not isinstance(helper_values, dict) or key not in helper_values:
            raise ValueError("Item not found. Refresh the item list and try again.")
        removed.append(
            {
                "data": helper_values[key],
                "id": str(key),
                "key": str(key),
                "helper_type": helper_type,
                "selector": selector,
            }
        )
    for selector in selectors:
        helper_type = selector.get("helper_type")
        key = selector.get("key")
        helper_values = data.get(helper_type)
        if isinstance(helper_values, dict) and key in helper_values:
            helper_values.pop(key)
            if not helper_values:
                data.pop(helper_type, None)
    return removed, data


def _remove_lovelace_items(
    path: Path,
    spec: DomainSpec,
    selectors: list[dict[str, Any]],
    warnings: list[str],
    allow_fingerprint_only: bool,
) -> tuple[list[dict[str, Any]], Any]:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = []
    shape = "list"
    meta: dict[str, Any] = {}
    views: list[Any]
    if isinstance(data, list):
        views = data
    elif isinstance(data, dict):
        shape = "dict"
        views = data.get("views") or []
        if not isinstance(views, list):
            raise ValueError("Lovelace views are not a list.")
        meta = {key: value for key, value in data.items() if key != "views"}
    else:
        raise ValueError("Module file is not a valid lovelace module.")
    views_copy = copy.deepcopy(views)
    items, _changed = _parse_list_items(views_copy, None, path.relative_to(settings.CONFIG_DIR).as_posix(), spec, warnings)
    removed: dict[str, dict[str, Any]] = {}
    indices: list[int] = []
    for selector in selectors:
        idx, item = _select_list_item_flexible(items, selector, allow_fingerprint_only)
        key = _selector_key(selector)
        removed[key] = {
            "data": views[idx],
            "id": item.ha_id,
            "fingerprint": item.fingerprint,
            "name": item.name,
            "selector": selector,
        }
        indices.append(idx)
    for idx in sorted(set(indices), reverse=True):
        views.pop(idx)
    payload = views if shape == "list" else {"views": views, **meta}
    ordered = [removed[_selector_key(selector)] for selector in selectors if _selector_key(selector) in removed]
    return ordered, payload


def _prepare_list_item_for_target(
    item_data: dict[str, Any],
    spec: DomainSpec,
    used_ids: set[str],
    rel_path: str,
    index: int,
) -> dict[str, Any]:
    if spec.id_field:
        item_id = _extract_item_id(item_data, spec.id_field)
        if item_id and item_id in used_ids:
            raise ValueError(f"{spec.key} id {item_id} already exists in destination.")
        if not item_id and spec.auto_id:
            if spec.key == "automation":
                candidate = _automation_alias_id(item_data)
            else:
                candidate = None
            if not candidate:
                candidate = _synthetic_id(rel_path, None, index)
                if spec.key == "lovelace":
                    candidate = _sanitize_lovelace_path(candidate)
            fingerprint = _fingerprint(item_data, {spec.id_field})
            item_id = _ensure_unique_id(candidate, used_ids, fingerprint)
            item_data[spec.id_field] = item_id
        if item_id:
            used_ids.add(str(item_id))
    return item_data


def _append_items_to_list_file(
    path: Path,
    spec: DomainSpec,
    items: list[dict[str, Any]],
) -> None:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ValueError("Destination file is not a list.")
    used_ids: set[str] = set()
    if spec.id_field:
        for entry in data:
            if isinstance(entry, dict) and entry.get(spec.id_field) is not None:
                used_ids.add(str(entry.get(spec.id_field)))
    for idx, item in enumerate(items):
        payload = dict(item["data"])
        payload = _prepare_list_item_for_target(
            payload, spec, used_ids, path.relative_to(settings.CONFIG_DIR).as_posix(), len(data) + idx
        )
        data.append(payload)
    _write_yaml(path, data, preview=None)


def _append_items_to_mapping_file(path: Path, items: list[dict[str, Any]]) -> None:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Destination file is not a map.")
    for item in items:
        key = item.get("key") or item.get("id")
        if not key:
            raise ValueError("Item key is required for mapping destinations.")
        if key in data:
            raise ValueError(f"Item key {key} already exists in destination.")
        data[key] = item["data"]
    _write_yaml(path, data, preview=None)


def _append_items_to_helpers_file(path: Path, items: list[dict[str, Any]]) -> None:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("Destination file is not a helpers map.")
    for item in items:
        helper_type = item.get("helper_type")
        key = item.get("key") or item.get("id")
        if not helper_type or not key:
            raise ValueError("Helper item must include helper_type and key.")
        if helper_type not in HELPER_TYPES:
            raise ValueError("Unsupported helper type.")
        helper_values = data.setdefault(helper_type, {})
        if not isinstance(helper_values, dict):
            raise ValueError("Helper type is not a map.")
        if key in helper_values:
            raise ValueError(f"Helper key {key} already exists in destination.")
        helper_values[key] = item["data"]
    _write_yaml(path, data, preview=None)


def _append_items_to_lovelace_file(
    path: Path, spec: DomainSpec, items: list[dict[str, Any]]
) -> None:
    data, _lines, error = yaml_load(path)
    if error:
        raise ValueError(error)
    if data is None:
        data = []
    shape = "list"
    meta: dict[str, Any] = {}
    views: list[Any]
    if isinstance(data, list):
        views = data
    elif isinstance(data, dict):
        shape = "dict"
        views = data.get("views") or []
        if not isinstance(views, list):
            raise ValueError("Lovelace views are not a list.")
        meta = {key: value for key, value in data.items() if key != "views"}
    else:
        raise ValueError("Destination file is not a valid lovelace module.")
    used_ids: set[str] = set()
    if spec.id_field:
        for entry in views:
            if isinstance(entry, dict) and entry.get(spec.id_field) is not None:
                used_ids.add(str(entry.get(spec.id_field)))
    for idx, item in enumerate(items):
        payload = dict(item["data"])
        payload = _prepare_list_item_for_target(
            payload, spec, used_ids, path.relative_to(settings.CONFIG_DIR).as_posix(), len(views) + idx
        )
        views.append(payload)
    final_payload = views if shape == "list" else {"views": views, **meta}
    _write_yaml(path, final_payload, preview=None)


def _ensure_yaml_filename(name: str) -> str:
    if "/" in name or "\\" in name:
        raise ValueError("One-off filename must be a simple filename.")
    candidate = name.strip()
    if not candidate:
        raise ValueError("Filename is required.")
    if not Path(candidate).suffix:
        candidate = f"{candidate}.yaml"
    if not _is_yaml_path(Path(candidate)):
        raise ValueError("Filename must end with .yaml or .yml.")
    return candidate


def _resolve_destination_path(
    operation: str,
    source_path: Path,
    kind: str,
    spec: DomainSpec | None,
    move_target: dict[str, Any] | None,
) -> Path | None:
    if operation == "delete":
        return None
    if operation == "unassign":
        if kind == "helpers":
            module_dir = settings.CONFIG_DIR / "helpers"
        elif spec:
            module_dir = spec.module_dir
        else:
            raise ValueError("Unsupported module type for unassign.")
        return _unassigned_module_path(module_dir)
    if not move_target or not isinstance(move_target, dict):
        raise ValueError("move_target is required for move operations.")
    target_type = move_target.get("type")
    if target_type in {"existing_package", "new_package"}:
        package_name = move_target.get("package_name")
        if not isinstance(package_name, str) or not package_name.strip():
            raise ValueError("package_name is required.")
        if package_name.strip() == "unassigned":
            raise ValueError("Package name 'unassigned' is reserved.")
        package_dir = settings.PACKAGES_DIR / package_name.strip()
        if target_type == "existing_package" and not package_dir.exists():
            raise ValueError("Package does not exist.")
        package_dir.mkdir(parents=True, exist_ok=True)
        if kind == "helpers":
            filename = "helpers.yaml"
        elif spec:
            filename = spec.package_filename
        else:
            raise ValueError("Unsupported module type for package destination.")
        return package_dir / filename
    if target_type == "one_off":
        filename = _ensure_yaml_filename(move_target.get("one_off_filename", ""))
        if kind == "helpers":
            module_dir = settings.CONFIG_DIR / "helpers"
        elif spec:
            module_dir = spec.module_dir
        else:
            raise ValueError("Unsupported module type for one-off destination.")
        return module_dir / filename
    raise ValueError("Unsupported move target type.")


def operate_module_items(
    operation: str,
    items: list[dict[str, Any]],
    move_target: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if operation not in {"move", "delete", "unassign"}:
        raise ValueError("Unsupported operation.")
    if not items:
        raise ValueError("At least one item is required.")

    warnings: list[str] = []
    changed_files: list[str] = []
    items_by_source: dict[str, list[dict[str, Any]]] = {}
    ordered_items: list[tuple[str, dict[str, Any]]] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("Each item must be an object.")
        path = entry.get("path")
        selector = entry.get("selector")
        if not isinstance(path, str) or not path:
            raise ValueError("Item path is required.")
        if not isinstance(selector, dict):
            raise ValueError("Item selector is required.")
        items_by_source.setdefault(path, []).append(selector)
        ordered_items.append((path, selector))

    removed_items_by_source: dict[str, list[dict[str, Any]]] = {}
    source_context: dict[str, tuple[str, DomainSpec | None]] = {}
    for rel_path, selectors in items_by_source.items():
        path = _resolve_module_path(rel_path)
        kind, spec = _module_file_context(path)
        source_context[rel_path] = (kind, spec)
        if kind == "list" and spec:
            removed_items, updated = _remove_list_items(
                path, spec, selectors, warnings, allow_fingerprint_only=False
            )
        elif kind == "mapping" and spec:
            removed_items, updated = _remove_mapping_items(path, selectors)
        elif kind == "helpers":
            removed_items, updated = _remove_helpers_items(path, selectors)
        elif kind == "lovelace" and spec:
            removed_items, updated = _remove_lovelace_items(
                path, spec, selectors, warnings, allow_fingerprint_only=False
            )
        else:
            raise ValueError("Unsupported module file type.")

        _write_yaml(path, updated, preview=None)
        changed_files.append(path.relative_to(settings.CONFIG_DIR).as_posix())
        removed_items_by_source[rel_path] = removed_items

    if operation == "delete":
        for rel_path, selectors in items_by_source.items():
            kind, spec = source_context[rel_path]
            if kind == "list" and spec:
                domain_items, domain_updated = _remove_list_items(
                    spec.domain_file, spec, selectors, warnings, allow_fingerprint_only=True
                )
                _ = domain_items
                _write_domain_yaml(spec.domain_file, domain_updated, preview=None)
                changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())
            elif kind == "mapping" and spec:
                _removed, domain_updated = _remove_mapping_items(spec.domain_file, selectors)
                _write_domain_yaml(spec.domain_file, domain_updated, preview=None)
                changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())
            elif kind == "lovelace" and spec:
                _removed, domain_updated = _remove_lovelace_items(
                    spec.domain_file, spec, selectors, warnings, allow_fingerprint_only=True
                )
                _write_domain_yaml(spec.domain_file, domain_updated, preview=None)
                changed_files.append(spec.domain_file.relative_to(settings.CONFIG_DIR).as_posix())
            elif kind == "helpers":
                for selector in selectors:
                    helper_type = selector.get("helper_type")
                    key = selector.get("key")
                    if not helper_type or not key:
                        continue
                    domain_path = settings.CONFIG_DIR / f"{helper_type}.yaml"
                    data, _lines, error = yaml_load(domain_path)
                    if error:
                        warnings.append(error)
                        continue
                    if data is None:
                        data = {}
                    if not isinstance(data, dict):
                        warnings.append(
                            f"{domain_path.relative_to(settings.CONFIG_DIR)} is not a map."
                        )
                        continue
                    if key in data:
                        data.pop(key)
                        _write_yaml(domain_path, data, preview=None)
                        changed_files.append(
                            domain_path.relative_to(settings.CONFIG_DIR).as_posix()
                        )

    if operation in {"move", "unassign"}:
        items_by_destination: dict[str, dict[str, Any]] = {}
        for rel_path, _selectors in items_by_source.items():
            kind, spec = source_context[rel_path]
            source_path = _resolve_module_path(rel_path)
            destination = _resolve_destination_path(
                operation, source_path, kind, spec, move_target
            )
            if destination is None:
                continue
            if destination.resolve() == source_path.resolve():
                raise ValueError("Destination matches the source file.")
            dest_key = destination.relative_to(settings.CONFIG_DIR).as_posix()
            if dest_key not in items_by_destination:
                items_by_destination[dest_key] = {"kind": kind, "spec": spec, "items": []}
            else:
                existing = items_by_destination[dest_key]
                if existing["kind"] != kind or existing["spec"] != spec:
                    raise ValueError("Destination cannot mix different module types.")

        removed_by_source_key: dict[str, dict[str, dict[str, Any]]] = {}
        for rel_path, removed_items in removed_items_by_source.items():
            removed_by_source_key[rel_path] = {
                _selector_key(item["selector"]): item for item in removed_items if item.get("selector")
            }
        for rel_path, selector in ordered_items:
            kind, spec = source_context[rel_path]
            source_path = _resolve_module_path(rel_path)
            destination = _resolve_destination_path(
                operation, source_path, kind, spec, move_target
            )
            if destination is None:
                continue
            dest_key = destination.relative_to(settings.CONFIG_DIR).as_posix()
            removed_item = removed_by_source_key.get(rel_path, {}).get(_selector_key(selector))
            if not removed_item:
                raise ValueError("Selected item could not be resolved after removal.")
            items_by_destination[dest_key]["items"].append(removed_item)

        for dest_rel, payload in items_by_destination.items():
            dest_items = payload["items"]
            if not dest_items:
                continue
            dest_path = settings.CONFIG_DIR / dest_rel
            kind = payload["kind"]
            spec = payload["spec"]
            if kind == "list" and spec:
                _append_items_to_list_file(dest_path, spec, dest_items)
            elif kind == "mapping" and spec:
                _append_items_to_mapping_file(dest_path, dest_items)
            elif kind == "helpers":
                _append_items_to_helpers_file(dest_path, dest_items)
            elif kind == "lovelace" and spec:
                _append_items_to_lovelace_file(dest_path, spec, dest_items)
            else:
                raise ValueError("Unsupported destination type.")
            changed_files.append(dest_rel)

    sync_result = sync_yaml_modules()
    warnings.extend(sync_result.get("warnings", []))
    changed_files = sorted(set(changed_files + sync_result.get("changed_files", [])))
    return {
        "status": "ok",
        "changed_files": changed_files,
        "warnings": warnings,
    }


def _spec_by_key(key: str) -> DomainSpec | None:
    for spec in YAML_MODULE_DOMAINS:
        if spec.key == key:
            return spec
    return None


def _spec_by_package_filename(filename: str) -> DomainSpec | None:
    for spec in YAML_MODULE_DOMAINS:
        if spec.package_filename == filename:
            return spec
    return None


def _module_file_context(path: Path) -> tuple[str, DomainSpec | None]:
    rel_parts = path.relative_to(settings.CONFIG_DIR).parts
    if not rel_parts:
        raise ValueError("Module path is not within the config directory.")
    root = rel_parts[0]
    filename = path.name

    if root == "packages":
        if filename == "helpers.yaml":
            return "helpers", None
        spec = _spec_by_package_filename(filename)
        if not spec:
            raise ValueError("Unsupported package module filename.")
        if spec.key == "template":
            raise ValueError("Template modules are not supported yet.")
        return spec.kind, spec

    if root == "helpers":
        return "helpers", None
    if root == "lovelace":
        spec = _spec_by_key("lovelace")
        return "lovelace", spec
    if root in MODULE_DOMAIN_MAP:
        spec = _spec_by_key(MODULE_DOMAIN_MAP[root])
        if not spec:
            raise ValueError("Unsupported domain module.")
        if spec.key == "template":
            raise ValueError("Template modules are not supported yet.")
        return spec.kind, spec

    raise ValueError("Unsupported module path.")


def list_yaml_modules_index() -> dict[str, Any]:
    modules: dict[str, dict[str, Any]] = {}
    packages_dir = settings.PACKAGES_DIR
    if packages_dir.exists():
        for file_path in sorted(packages_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if not _is_yaml_path(file_path):
                continue
            rel_path = file_path.relative_to(settings.CONFIG_DIR)
            parts = rel_path.parts
            if len(parts) < 2:
                continue
            package_name = Path(parts[1]).stem if len(parts) == 2 else parts[1]
            if package_name == "unassigned":
                continue
            module = modules.setdefault(
                package_name,
                {
                    "id": f"package:{package_name}",
                    "name": package_name,
                    "kind": "package",
                    "files": [],
                },
            )
            module["files"].append(rel_path.as_posix())

    package_modules = list(modules.values())
    for module in package_modules:
        module["files"] = sorted(set(module["files"]))

    one_off_modules: list[dict[str, Any]] = []
    unassigned_modules: list[dict[str, Any]] = []
    unassigned_files_by_domain: dict[str, str] = {}
    unassigned_dir = settings.PACKAGES_DIR / "unassigned"
    if unassigned_dir.exists():
        for path in sorted(unassigned_dir.rglob("*")):
            if not path.is_file():
                continue
            if not _is_yaml_path(path):
                continue
            domain = None
            if path.name == "helpers.yaml":
                domain = "helpers"
            else:
                spec = _spec_by_package_filename(path.name)
                if spec:
                    domain = spec.module_dir.name
            if domain:
                unassigned_files_by_domain[domain] = path.relative_to(
                    settings.CONFIG_DIR
                ).as_posix()
    for domain in MODULE_BROWSER_DOMAINS:
        dir_path = settings.CONFIG_DIR / domain
        files: list[str] = []
        legacy_unassigned = _legacy_unassigned_module_path(dir_path).relative_to(
            settings.CONFIG_DIR
        ).as_posix()
        if dir_path.exists():
            files = sorted(
                path.relative_to(settings.CONFIG_DIR).as_posix()
                for path in dir_path.rglob("*")
                if path.is_file() and _is_yaml_path(path)
            )
        canonical_unassigned = unassigned_files_by_domain.get(domain)
        fallback_unassigned = legacy_unassigned if legacy_unassigned in files else None
        one_off_files = [path for path in files if path not in {legacy_unassigned}]
        if one_off_files:
            one_off_modules.append(
                {
                    "id": f"one_offs:{domain}",
                    "name": domain,
                    "kind": "one_offs",
                    "files": one_off_files,
                }
            )
        unassigned_path = canonical_unassigned or fallback_unassigned
        if unassigned_path:
            unassigned_modules.append(
                {
                    "id": f"unassigned:{domain}",
                    "name": domain,
                    "kind": "unassigned",
                    "files": [unassigned_path],
                }
            )

    package_modules.sort(key=lambda item: item["name"])
    one_off_modules.sort(key=lambda item: item["name"])
    unassigned_modules.sort(key=lambda item: item["name"])
    return {"modules": package_modules + one_off_modules + unassigned_modules}


def read_module_file(rel_path: str) -> dict[str, Any]:
    path = _resolve_module_path(rel_path)
    if not path.exists():
        raise FileNotFoundError("Module file not found.")
    content = read_text(path)
    return {
        "path": path.relative_to(settings.CONFIG_DIR).as_posix(),
        "content": content,
        "hash": file_hash(path),
    }


def write_module_file(rel_path: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ValueError("Module content must be a string.")
    path = _resolve_module_path(rel_path)
    if not path.parent.exists():
        raise FileNotFoundError("Module directory not found.")
    path.write_text(content, encoding="utf-8")
    return {
        "status": "saved",
        "path": path.relative_to(settings.CONFIG_DIR).as_posix(),
        "hash": file_hash(path),
    }


def delete_module_file(rel_path: str) -> dict[str, Any]:
    path = _resolve_module_path(rel_path)
    if not path.exists():
        raise FileNotFoundError("Module file not found.")
    path.unlink()
    return {
        "status": "deleted",
        "path": path.relative_to(settings.CONFIG_DIR).as_posix(),
    }

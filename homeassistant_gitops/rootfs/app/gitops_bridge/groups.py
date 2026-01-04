from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import settings, yaml_modules
from .config_store import ensure_gitops_dirs
from .fs_utils import modules_hash, read_text, write_yaml_if_changed, yaml_load, yaml_dump
from .yaml_tags import TaggedValue


GROUPS_CONFIG_PATH = settings.GITOPS_DIR / "groups.config.yaml"
GROUPS_RESTART_STATE_PATH = settings.GITOPS_DIR / "groups.restart-state.yaml"


class GroupsError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


def _default_groups_config() -> dict[str, Any]:
    return {"schema_version": 1, "ignored": {"entity_ids": []}}


def _normalize_entity_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GroupsError("ignored.entity_ids must be a list of strings.")
    cleaned: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            raise GroupsError("ignored.entity_ids must be a list of strings.")
        entity_id = entry.strip().lower()
        if entity_id and entity_id not in cleaned:
            cleaned.append(entity_id)
    return sorted(cleaned)


def _normalize_groups_config(payload: Any) -> dict[str, Any]:
    config = _default_groups_config()
    if payload is None:
        return config
    if not isinstance(payload, dict):
        raise GroupsError("Groups config must be a map.")
    schema_version = payload.get("schema_version", 1)
    if schema_version != 1:
        raise GroupsError("Unsupported groups.config.yaml schema_version.")
    ignored = payload.get("ignored") or {}
    if not isinstance(ignored, dict):
        raise GroupsError("ignored config must be a map.")
    config["ignored"]["entity_ids"] = _normalize_entity_ids(ignored.get("entity_ids"))
    return config


def load_groups_config() -> dict[str, Any]:
    if not GROUPS_CONFIG_PATH.exists():
        return _default_groups_config()
    try:
        data = yaml.safe_load(read_text(GROUPS_CONFIG_PATH))
    except yaml.YAMLError as exc:
        raise GroupsError(f"Invalid groups.config.yaml: {exc}") from exc
    return _normalize_groups_config(data)


def save_groups_config(payload: Any) -> dict[str, Any]:
    config = _normalize_groups_config(payload)
    ensure_gitops_dirs()
    GROUPS_CONFIG_PATH.write_text(yaml_dump(config), encoding="utf-8")
    return config


def _default_restart_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "last_groups_change_hash": "",
        "last_restart_ack_hash": "",
    }


def _normalize_restart_state(payload: Any) -> dict[str, Any]:
    state = _default_restart_state()
    if payload is None:
        return state
    if not isinstance(payload, dict):
        raise GroupsError("groups.restart-state.yaml must be a map.")
    schema_version = payload.get("schema_version", 1)
    if schema_version != 1:
        raise GroupsError("Unsupported groups.restart-state.yaml schema_version.")
    for key in ("last_groups_change_hash", "last_restart_ack_hash"):
        value = payload.get(key, "")
        state[key] = str(value) if value else ""
    return state


def _group_config_paths() -> list[Path]:
    paths: list[Path] = []
    domain_path = settings.CONFIG_DIR / "groups.yaml"
    if domain_path.exists():
        paths.append(domain_path)

    groups_dir = settings.CONFIG_DIR / "groups"
    if groups_dir.exists():
        paths.extend(sorted(path for path in groups_dir.rglob("*.y*ml") if path.is_file()))

    if settings.PACKAGES_DIR.exists():
        for package_dir in sorted(settings.PACKAGES_DIR.iterdir()):
            if not package_dir.is_dir():
                continue
            candidate = package_dir / "groups.yaml"
            if candidate.exists():
                paths.append(candidate)

    return paths


def _groups_config_hash() -> str:
    paths = _group_config_paths()
    if not paths:
        return ""
    return modules_hash(paths)


def load_restart_state() -> dict[str, Any]:
    if not GROUPS_RESTART_STATE_PATH.exists():
        return _default_restart_state()
    try:
        data = yaml.safe_load(read_text(GROUPS_RESTART_STATE_PATH))
    except yaml.YAMLError as exc:
        raise GroupsError(f"Invalid groups.restart-state.yaml: {exc}") from exc
    return _normalize_restart_state(data)


def _save_restart_state(state: dict[str, Any]) -> None:
    ensure_gitops_dirs()
    GROUPS_RESTART_STATE_PATH.write_text(yaml_dump(state), encoding="utf-8")


def restart_status() -> dict[str, Any]:
    """Return whether a Home Assistant restart is required for group changes."""

    state = load_restart_state()
    current_hash = _groups_config_hash()
    if state.get("last_groups_change_hash") != current_hash:
        state["last_groups_change_hash"] = current_hash
        _save_restart_state(state)

    ack_hash = state.get("last_restart_ack_hash") or ""
    restart_needed = bool(current_hash) and current_hash != ack_hash
    return {
        "restart_needed": restart_needed,
        "current_hash": current_hash,
        "ack_hash": ack_hash,
        "path": GROUPS_RESTART_STATE_PATH.relative_to(settings.CONFIG_DIR).as_posix(),
    }


def ack_restart() -> dict[str, Any]:
    status = restart_status()
    current_hash = status.get("current_hash") or ""
    state = load_restart_state()
    state["last_groups_change_hash"] = current_hash
    state["last_restart_ack_hash"] = current_hash
    _save_restart_state(state)
    status["restart_needed"] = False
    status["ack_hash"] = current_hash
    return status


def _require_supervisor_token() -> str:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise GroupsError("Supervisor token not available; cannot call Home Assistant.")
    return token


async def _ha_get_json(path: str) -> Any:
    token = _require_supervisor_token()
    url = f"http://supervisor/core/api{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise GroupsError("Home Assistant API unavailable.", status_code=502) from exc
    if response.status_code in {401, 403}:
        raise GroupsError("Supervisor token rejected by Home Assistant.", status_code=500)
    if response.status_code >= 400:
        raise GroupsError(
            f"Home Assistant API error ({response.status_code}).", status_code=502
        )
    try:
        return response.json()
    except ValueError as exc:
        raise GroupsError("Home Assistant API returned invalid JSON.", status_code=502) from exc


async def _fetch_states() -> list[dict[str, Any]]:
    data = await _ha_get_json("/states")
    if not isinstance(data, list):
        raise GroupsError("States response is not a list.", status_code=502)
    return [entry for entry in data if isinstance(entry, dict)]


def _load_group_mapping_entries() -> list[dict[str, Any]]:
    path = settings.MAPPINGS_DIR / "group.yaml"
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(read_text(path))
    except yaml.YAMLError:
        return []
    if not isinstance(data, dict):
        return []
    entries = data.get("entries") or []
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _load_groups_domain() -> dict[str, Any]:
    domain_path = settings.CONFIG_DIR / "groups.yaml"
    data, _lines, _error = yaml_load(domain_path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _groups_yaml_configuration_status() -> dict[str, Any]:
    """Best-effort check that Home Assistant is configured to load `groups.yaml`."""

    config_path = settings.CONFIG_DIR / "configuration.yaml"
    payload = {
        "path": config_path.relative_to(settings.CONFIG_DIR).as_posix(),
        "includes_groups_yaml": False,
        "warning": "",
    }
    if not config_path.exists():
        payload["warning"] = "configuration.yaml not found. Add `group: !include groups.yaml` to load groups."
        return payload

    data, _lines, error = yaml_load(config_path)
    if error:
        payload["warning"] = f"Unable to parse configuration.yaml ({error}). Ensure `group: !include groups.yaml` is configured."
        return payload
    if data is None or not isinstance(data, dict):
        payload["warning"] = "configuration.yaml is not a YAML map. Ensure `group: !include groups.yaml` is configured."
        return payload

    group_value = data.get("group")
    if isinstance(group_value, TaggedValue) and group_value.tag == "!include":
        include_target = str(group_value.value).strip()
        if include_target in {"groups.yaml", "groups.yml"}:
            payload["includes_groups_yaml"] = True
            payload["warning"] = ""
            return payload

    payload["warning"] = "configuration.yaml does not include `group: !include groups.yaml`. Home Assistant will ignore GitOps-managed groups until it is added."
    return payload


def _normalize_object_id(value: Any) -> str:
    if not isinstance(value, str):
        raise GroupsError("object_id must be a string.")
    object_id = value.strip().lower()
    if not object_id:
        raise GroupsError("object_id is required.")
    if not all(char.isalnum() or char == "_" for char in object_id):
        raise GroupsError("object_id must contain only letters, numbers, and underscores.")
    return object_id


def _normalize_members(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise GroupsError("members must be a list of entity IDs.")
    cleaned = sorted(
        {member.strip().lower() for member in value if isinstance(member, str) and member.strip()}
    )
    return cleaned


def _ensure_yaml_filename(value: Any) -> str:
    if not isinstance(value, str):
        raise GroupsError("Filename must be a string.")
    candidate = value.strip()
    if not candidate:
        raise GroupsError("Filename is required.")
    if "/" in candidate or "\\" in candidate:
        raise GroupsError("Filename must be a simple filename.")
    if "." not in candidate:
        candidate = f"{candidate}.yaml"
    if not candidate.lower().endswith((".yaml", ".yml")):
        raise GroupsError("Filename must end with .yaml or .yml.")
    return candidate


def _group_destination_path(payload: dict[str, Any]) -> Path:
    destination = payload.get("destination") or {}
    if not isinstance(destination, dict):
        raise GroupsError("destination must be a map.")
    dest_type = destination.get("type")
    if dest_type == "package":
        package_name = destination.get("package_name")
        if not isinstance(package_name, str) or not package_name.strip():
            raise GroupsError("destination.package_name is required.")
        package_dir = settings.PACKAGES_DIR / package_name.strip()
        package_dir.mkdir(parents=True, exist_ok=True)
        return package_dir / "groups.yaml"
    if dest_type == "one_off":
        filename = _ensure_yaml_filename(destination.get("filename"))
        groups_dir = settings.CONFIG_DIR / "groups"
        groups_dir.mkdir(parents=True, exist_ok=True)
        return groups_dir / filename
    raise GroupsError("destination.type must be 'package' or 'one_off'.")


def list_groups() -> dict[str, Any]:
    config = load_groups_config()
    ignored = set(config.get("ignored", {}).get("entity_ids", []))
    domain = _load_groups_domain()
    mapping_entries = _load_group_mapping_entries()

    configuration = _groups_yaml_configuration_status()

    managed: list[dict[str, Any]] = []
    managed_ids: set[str] = set()
    for entry in mapping_entries:
        object_id = entry.get("id")
        if not isinstance(object_id, str) or not object_id:
            continue
        managed_ids.add(object_id)
        group_def = domain.get(object_id) if isinstance(domain.get(object_id), dict) else {}
        name = group_def.get("name") if isinstance(group_def.get("name"), str) else ""
        entities = group_def.get("entities")
        members = [str(item) for item in entities] if isinstance(entities, list) else []
        managed.append(
            {
                "object_id": object_id,
                "entity_id": f"group.{object_id}",
                "name": name,
                "members": members,
                "member_count": len(members),
                "source": entry.get("source") or "",
                "ignored": f"group.{object_id}" in ignored,
            }
        )
    managed.sort(key=lambda row: row.get("entity_id", ""))

    return {
        "status": "ok",
        "configuration": configuration,
        "managed": managed,
        "ignored": sorted(ignored),
        "restart": restart_status(),
    }


async def list_unmanaged_groups() -> list[dict[str, Any]]:
    config = load_groups_config()
    ignored = set(config.get("ignored", {}).get("entity_ids", []))
    mapping_entries = _load_group_mapping_entries()
    managed_ids = {
        entry.get("id") for entry in mapping_entries if isinstance(entry.get("id"), str)
    }

    try:
        states = await _fetch_states()
    except GroupsError as exc:
        if exc.status_code == 400:
            return []
        raise
    rows: list[dict[str, Any]] = []
    for state in states:
        entity_id = state.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.startswith("group.") or "." not in entity_id:
            continue
        object_id = entity_id.split(".", 1)[1]
        if object_id in managed_ids:
            continue
        attrs = state.get("attributes")
        if not isinstance(attrs, dict):
            continue
        members = attrs.get("entity_id")
        if not isinstance(members, list):
            continue
        cleaned_members = sorted(
            {member.strip() for member in members if isinstance(member, str) and member.strip()}
        )
        rows.append(
            {
                "object_id": object_id,
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or "",
                "members": cleaned_members,
                "member_count": len(cleaned_members),
                "ignored": entity_id in ignored,
            }
        )
    rows.sort(key=lambda row: row.get("entity_id", ""))
    return rows


async def assert_no_unmanaged_group_collision(object_id: str) -> None:
    """Reject creating a GitOps-managed group that already exists in Home Assistant runtime.

    This is a best-effort safety check. If the Home Assistant API is unavailable (no supervisor
    token, or a transient error), GitOps Bridge cannot confirm collisions and will allow the write.
    """

    object_id = _normalize_object_id(object_id)
    mapping_entries = _load_group_mapping_entries()
    if any(entry.get("id") == object_id for entry in mapping_entries):
        return
    domain = _load_groups_domain()
    if object_id in domain:
        return
    try:
        states = await _fetch_states()
    except GroupsError:
        return
    entity_id = f"group.{object_id}"
    if any(state.get("entity_id") == entity_id for state in states if isinstance(state, dict)):
        raise GroupsError(
            f"{entity_id} already exists in Home Assistant. Import it or choose a different object_id.",
            status_code=409,
        )


def upsert_group(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GroupsError("Payload must be a map.")
    object_id = _normalize_object_id(payload.get("object_id"))
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise GroupsError("name is required.")
    members = _normalize_members(payload.get("members"))
    group_def = {"name": name.strip(), "entities": members}

    mapping_entries = _load_group_mapping_entries()
    existing = next(
        (entry for entry in mapping_entries if entry.get("id") == object_id and entry.get("source")),
        None,
    )
    if existing:
        dest_path = settings.CONFIG_DIR / str(existing.get("source"))
    else:
        dest_path = _group_destination_path(payload)

    data, _lines, error = yaml_load(dest_path)
    if error:
        raise GroupsError(error)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise GroupsError("Destination file must be a YAML map.")
    data[object_id] = group_def
    write_yaml_if_changed(dest_path, data)

    sync_result = yaml_modules.sync_yaml_modules()
    return {
        "status": "saved",
        "object_id": object_id,
        "sync": sync_result,
        "restart": restart_status(),
    }


def delete_group(object_id: str) -> dict[str, Any]:
    object_id = _normalize_object_id(object_id)
    mapping_entries = _load_group_mapping_entries()
    entry = next((row for row in mapping_entries if row.get("id") == object_id), None)
    if not entry or not entry.get("source"):
        raise GroupsError("Group not found in YAML Modules mapping.", status_code=404)
    source_rel = str(entry.get("source"))
    try:
        sync_result = yaml_modules.operate_module_items(
            "delete",
            items=[{"path": source_rel, "selector": {"type": "map_key", "key": object_id}}],
        )
    except ValueError as exc:
        raise GroupsError(str(exc)) from exc
    return {
        "status": "deleted",
        "object_id": object_id,
        "sync": sync_result,
        "restart": restart_status(),
    }


async def import_group(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GroupsError("Payload must be a map.")
    entity_id = payload.get("entity_id")
    if not isinstance(entity_id, str) or not entity_id.startswith("group."):
        raise GroupsError("entity_id must be a group.* entity id.")
    object_id = entity_id.split(".", 1)[1]
    destination_payload = dict(payload)
    destination_payload["object_id"] = object_id

    states = await _fetch_states()
    match = next((state for state in states if state.get("entity_id") == entity_id), None)
    if not match:
        raise GroupsError("Group not found in Home Assistant states.", status_code=404)
    attrs = match.get("attributes")
    if not isinstance(attrs, dict):
        raise GroupsError("Group state missing attributes.", status_code=502)
    members = attrs.get("entity_id")
    if not isinstance(members, list):
        raise GroupsError("Group state missing members.", status_code=502)

    destination_payload["name"] = attrs.get("friendly_name") or object_id
    destination_payload["members"] = [
        str(member) for member in members if isinstance(member, str) and str(member).strip()
    ]
    return upsert_group(destination_payload)


def set_group_ignored(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GroupsError("Payload must be a map.")
    entity_id = payload.get("entity_id")
    if not isinstance(entity_id, str) or "." not in entity_id:
        raise GroupsError("entity_id must be a valid entity id.")
    ignore = bool(payload.get("ignored"))
    config = load_groups_config()
    ignored = set(config.get("ignored", {}).get("entity_ids", []))
    normalized = entity_id.strip().lower()
    if ignore:
        ignored.add(normalized)
    else:
        ignored.discard(normalized)
    updated = {"schema_version": 1, "ignored": {"entity_ids": sorted(ignored)}}
    save_groups_config(updated)
    return {"status": "ok", "config": updated}

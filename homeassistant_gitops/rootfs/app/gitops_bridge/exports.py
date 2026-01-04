from __future__ import annotations

import csv
import io
import os
from typing import Any

import httpx
import yaml

from . import settings
from .config_store import ensure_gitops_dirs
from .fs_utils import read_text, yaml_dump


EXPORT_FILES = {
    "entities": "entities.csv",
    "areas": "areas.csv",
    "devices": "devices.csv",
    "groups": "groups.csv",
}

EXPORT_ENTITY_COLUMNS = [
    "entity_id",
    "name",
    "platform",
    "integration",
    "domain",
    "entity_category",
    "device_id",
    "device_name",
    "area_id",
    "area_name",
    "disabled",
    "hidden",
    "original_name",
    "icon",
    "unit_of_measurement",
]

EXPORT_AREA_COLUMNS = [
    "area_id",
    "name",
    "floor",
]

EXPORT_DEVICE_COLUMNS = [
    "device_id",
    "name",
    "manufacturer",
    "model",
    "area_id",
    "area_name",
]

EXPORT_GROUP_COLUMNS = [
    "entity_id",
    "name",
    "members",
    "member_count",
]


class ExportError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


def _default_exports_config() -> dict[str, Any]:
    return {"schema_version": 1, "entities": {"integration_blacklist": []}}


def _normalize_blacklist(raw: Any) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ExportError("integration_blacklist must be a list of strings.")
    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ExportError("integration_blacklist must be a list of strings.")
        value = entry.strip().lower()
        if value and value not in cleaned:
            cleaned.append(value)
    return sorted(cleaned)


def _normalize_exports_config(payload: Any) -> dict[str, Any]:
    config = _default_exports_config()
    if payload is None:
        return config
    if not isinstance(payload, dict):
        raise ExportError("Export config must be a map.")
    schema_version = payload.get("schema_version", 1)
    if schema_version != 1:
        raise ExportError("Unsupported exports.config.yaml schema_version.")
    entities = payload.get("entities", {})
    if entities is None:
        entities = {}
    if not isinstance(entities, dict):
        raise ExportError("entities config must be a map.")
    integration_blacklist = _normalize_blacklist(entities.get("integration_blacklist"))
    config["entities"]["integration_blacklist"] = integration_blacklist
    return config


def load_exports_config() -> dict[str, Any]:
    if not settings.EXPORTS_CONFIG_PATH.exists():
        return _default_exports_config()
    try:
        data = yaml.safe_load(read_text(settings.EXPORTS_CONFIG_PATH))
    except yaml.YAMLError as exc:
        raise ExportError(f"Invalid exports.config.yaml: {exc}") from exc
    return _normalize_exports_config(data)


def save_exports_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = _normalize_exports_config(payload)
    ensure_gitops_dirs()
    settings.EXPORTS_CONFIG_PATH.write_text(yaml_dump(config), encoding="utf-8")
    return config


def _require_supervisor_token() -> str:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise ExportError("Supervisor token not available; cannot call Home Assistant.")
    return token


def _exports_dir() -> Any:
    return settings.SYSTEM_EXPORTS_DIR


def _export_path(kind: str) -> Any:
    if kind not in EXPORT_FILES:
        raise ExportError("Unsupported export type.")
    return _exports_dir() / EXPORT_FILES[kind]


def _write_export_csv(kind: str, headers: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _format_cell(row.get(key)) for key in headers})
    _exports_dir().mkdir(parents=True, exist_ok=True)
    path = _export_path(kind)
    path.write_text(output.getvalue(), encoding="utf-8")
    return {
        "status": "ok",
        "path": path.relative_to(settings.CONFIG_DIR).as_posix(),
        "rows": len(rows),
        "columns": headers,
    }


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


async def _ha_get_json(path: str) -> Any:
    token = _require_supervisor_token()
    url = f"http://supervisor/core/api{path}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise ExportError("Home Assistant API unavailable.", status_code=502) from exc
    if response.status_code in {401, 403}:
        raise ExportError("Supervisor token rejected by Home Assistant.", status_code=500)
    if response.status_code >= 400:
        raise ExportError(
            f"Home Assistant API error ({response.status_code}).", status_code=502
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ExportError("Home Assistant API returned invalid JSON.", status_code=502) from exc


async def _fetch_area_registry() -> list[dict[str, Any]]:
    data = await _ha_get_json("/config/area_registry")
    if not isinstance(data, list):
        raise ExportError("Area registry response is not a list.", status_code=502)
    return [entry for entry in data if isinstance(entry, dict)]


async def _fetch_device_registry() -> list[dict[str, Any]]:
    data = await _ha_get_json("/config/device_registry")
    if not isinstance(data, list):
        raise ExportError("Device registry response is not a list.", status_code=502)
    return [entry for entry in data if isinstance(entry, dict)]


async def _fetch_entity_registry() -> list[dict[str, Any]]:
    data = await _ha_get_json("/config/entity_registry")
    if not isinstance(data, list):
        raise ExportError("Entity registry response is not a list.", status_code=502)
    return [entry for entry in data if isinstance(entry, dict)]


async def _fetch_states() -> list[dict[str, Any]]:
    data = await _ha_get_json("/states")
    if not isinstance(data, list):
        raise ExportError("States response is not a list.", status_code=502)
    return [entry for entry in data if isinstance(entry, dict)]


def _device_display_name(device: dict[str, Any] | None) -> str:
    if not device:
        return ""
    name = device.get("name_by_user") or device.get("name")
    return str(name) if name else ""


def _area_name(area: dict[str, Any] | None) -> str:
    if not area:
        return ""
    name = area.get("name")
    return str(name) if name else ""


def _entity_domain(entity_id: str) -> str:
    if not entity_id or "." not in entity_id:
        return ""
    return entity_id.split(".", 1)[0]


def _integration_name(entry: dict[str, Any]) -> str:
    platform = entry.get("platform")
    if isinstance(platform, str) and platform:
        return platform
    integration = entry.get("integration")
    if isinstance(integration, str) and integration:
        return integration
    entity_id = entry.get("entity_id")
    if isinstance(entity_id, str):
        return _entity_domain(entity_id)
    return ""


def _load_blacklist() -> set[str]:
    config = load_exports_config()
    entries = config.get("entities", {}).get("integration_blacklist", [])
    if not isinstance(entries, list):
        return set()
    return {str(entry).strip().lower() for entry in entries if str(entry).strip()}


def _normalize_unit_of_measurement(entry: dict[str, Any]) -> str:
    value = entry.get("unit_of_measurement")
    if isinstance(value, str) and value:
        return value
    capabilities = entry.get("capabilities")
    if isinstance(capabilities, dict):
        unit = capabilities.get("unit_of_measurement")
        if isinstance(unit, str) and unit:
            return unit
    return ""


async def export_entities() -> dict[str, Any]:
    blacklist = _load_blacklist()
    areas = await _fetch_area_registry()
    devices = await _fetch_device_registry()
    entities = await _fetch_entity_registry()

    areas_by_id = {
        str(area.get("area_id")): area
        for area in areas
        if isinstance(area.get("area_id"), str)
    }
    devices_by_id = {
        str(device.get("id")): device
        for device in devices
        if isinstance(device.get("id"), str)
    }

    rows: list[dict[str, Any]] = []
    for entry in entities:
        entity_id = entry.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id:
            continue
        integration = _integration_name(entry)
        if integration.strip().lower() in blacklist:
            continue
        platform = entry.get("platform") if isinstance(entry.get("platform"), str) else ""
        device_id = entry.get("device_id") if isinstance(entry.get("device_id"), str) else ""
        device = devices_by_id.get(device_id) if device_id else None
        area_id = entry.get("area_id") if isinstance(entry.get("area_id"), str) else ""
        if not area_id and device:
            area_id = device.get("area_id") if isinstance(device.get("area_id"), str) else ""
        area = areas_by_id.get(area_id) if area_id else None
        rows.append(
            {
                "entity_id": entity_id,
                "name": entry.get("name") or entry.get("original_name") or "",
                "platform": platform,
                "integration": integration,
                "domain": _entity_domain(entity_id),
                "entity_category": entry.get("entity_category") or "",
                "device_id": device_id,
                "device_name": _device_display_name(device),
                "area_id": area_id,
                "area_name": _area_name(area),
                "disabled": bool(entry.get("disabled_by")),
                "hidden": bool(entry.get("hidden_by")),
                "original_name": entry.get("original_name") or "",
                "icon": entry.get("icon") or "",
                "unit_of_measurement": _normalize_unit_of_measurement(entry),
            }
        )

    rows.sort(key=lambda row: row.get("entity_id", ""))
    return _write_export_csv("entities", EXPORT_ENTITY_COLUMNS, rows)


async def export_areas() -> dict[str, Any]:
    areas = await _fetch_area_registry()
    rows: list[dict[str, Any]] = []
    for entry in areas:
        area_id = entry.get("area_id")
        if not isinstance(area_id, str) or not area_id:
            continue
        rows.append(
            {
                "area_id": area_id,
                "name": entry.get("name") or "",
                "floor": entry.get("floor") or "",
            }
        )
    rows.sort(key=lambda row: row.get("area_id", ""))
    return _write_export_csv("areas", EXPORT_AREA_COLUMNS, rows)


async def export_devices() -> dict[str, Any]:
    areas = await _fetch_area_registry()
    devices = await _fetch_device_registry()
    areas_by_id = {
        str(area.get("area_id")): area
        for area in areas
        if isinstance(area.get("area_id"), str)
    }
    rows: list[dict[str, Any]] = []
    for entry in devices:
        device_id = entry.get("id")
        if not isinstance(device_id, str) or not device_id:
            continue
        area_id = entry.get("area_id") if isinstance(entry.get("area_id"), str) else ""
        area = areas_by_id.get(area_id) if area_id else None
        rows.append(
            {
                "device_id": device_id,
                "name": _device_display_name(entry),
                "manufacturer": entry.get("manufacturer") or "",
                "model": entry.get("model") or "",
                "area_id": area_id,
                "area_name": _area_name(area),
            }
        )
    rows.sort(key=lambda row: row.get("device_id", ""))
    return _write_export_csv("devices", EXPORT_DEVICE_COLUMNS, rows)


async def export_groups() -> dict[str, Any]:
    """Export group and group-like entities from `/api/states` into `system/groups.csv`."""

    allowed_domains = {"group", "sensor", "light"}
    states = await _fetch_states()
    rows: list[dict[str, Any]] = []
    for entry in states:
        entity_id = entry.get("entity_id")
        if not isinstance(entity_id, str) or "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain not in allowed_domains:
            continue
        attrs = entry.get("attributes")
        if not isinstance(attrs, dict):
            continue
        members = attrs.get("entity_id")
        if not isinstance(members, list):
            continue
        cleaned_members = sorted(
            {
                str(member).strip()
                for member in members
                if isinstance(member, str) and member.strip()
            }
        )
        rows.append(
            {
                "entity_id": entity_id,
                "name": attrs.get("friendly_name") or attrs.get("name") or "",
                "members": ";".join(cleaned_members),
                "member_count": len(cleaned_members),
            }
        )

    rows.sort(key=lambda row: row.get("entity_id", ""))
    return _write_export_csv("groups", EXPORT_GROUP_COLUMNS, rows)


async def run_export(kind: str) -> dict[str, Any]:
    if kind == "entities":
        return await export_entities()
    if kind == "areas":
        return await export_areas()
    if kind == "devices":
        return await export_devices()
    if kind == "groups":
        return await export_groups()
    raise ExportError("Unsupported export type.")


def read_export_file(kind: str) -> dict[str, Any]:
    path = _export_path(kind)
    if not path.exists():
        raise FileNotFoundError("Export file not found.")
    return {
        "path": path.relative_to(settings.CONFIG_DIR).as_posix(),
        "content": read_text(path),
    }

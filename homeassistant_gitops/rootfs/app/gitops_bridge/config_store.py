from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from . import settings
from .fs_utils import read_text
from .git_ops import get_git_config_value, get_origin_url


@dataclass
class Options:
    remote_url: str | None
    remote_branch: str
    notification_enabled: bool
    webhook_enabled: bool
    webhook_path: str
    poll_interval_minutes: int | None
    yaml_modules_enabled: bool
    ui_theme: str


CONFIG_KEYS = {
    "remote_url",
    "remote_branch",
    "notification_enabled",
    "webhook_enabled",
    "webhook_path",
    "poll_interval_minutes",
    "yaml_modules_enabled",
    "ui_theme",
}


def _parse_bool(value: str) -> bool | None:
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    return None


def load_gitops_config() -> dict[str, Any]:
    migrate_gitops_config()
    if not settings.GITOPS_CONFIG_PATH.exists():
        return {}
    data: dict[str, Any] = {}
    for line in read_text(settings.GITOPS_CONFIG_PATH).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if not key:
            continue
        if value.lower() in {"null", "none"}:
            data[key] = None
            continue
        parsed_bool = _parse_bool(value)
        if parsed_bool is not None:
            data[key] = parsed_bool
            continue
        if value.isdigit():
            data[key] = int(value)
            continue
        data[key] = value
    if "yaml_modules_enabled" not in data and "merge_automations" in data:
        data["yaml_modules_enabled"] = data["merge_automations"]
    return data


def ensure_gitops_dirs() -> None:
    settings.GITOPS_DIR.mkdir(parents=True, exist_ok=True)
    settings.MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)


def migrate_gitops_config() -> None:
    if settings.GITOPS_CONFIG_PATH.exists():
        return
    if not settings.LEGACY_GITOPS_CONFIG_PATH.exists():
        return
    ensure_gitops_dirs()
    legacy_content = read_text(settings.LEGACY_GITOPS_CONFIG_PATH)
    settings.GITOPS_CONFIG_PATH.write_text(legacy_content, encoding="utf-8")


def _quote_yaml(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_gitops_config(options: Options) -> str:
    lines = [
        "# Home Assistant GitOps Bridge configuration",
        f"remote_url: {_quote_yaml(options.remote_url or '')}",
        f"remote_branch: {_quote_yaml(options.remote_branch)}",
        f"notification_enabled: {'true' if options.notification_enabled else 'false'}",
        f"webhook_enabled: {'true' if options.webhook_enabled else 'false'}",
        f"webhook_path: {_quote_yaml(options.webhook_path)}",
        (
            "poll_interval_minutes: "
            f"{options.poll_interval_minutes if options.poll_interval_minutes is not None else 'null'}"
        ),
        f"yaml_modules_enabled: {'true' if options.yaml_modules_enabled else 'false'}",
        f"ui_theme: {_quote_yaml(options.ui_theme)}",
    ]
    return "\n".join(lines) + "\n"


def write_gitops_config(options: Options) -> None:
    ensure_gitops_dirs()
    content = render_gitops_config(options)
    settings.GITOPS_CONFIG_PATH.write_text(content, encoding="utf-8")


def _build_options(data: dict[str, Any]) -> Options:
    ui_theme = str(data.get("ui_theme", "system") or "system").lower()
    if ui_theme not in {"light", "dark", "system"}:
        ui_theme = "system"
    yaml_modules_enabled = data.get("yaml_modules_enabled")
    if yaml_modules_enabled is None:
        yaml_modules_enabled = data.get("merge_automations", True)
    return Options(
        remote_url=data.get("remote_url") or None,
        remote_branch=data.get("remote_branch", "main"),
        notification_enabled=bool(data.get("notification_enabled", True)),
        webhook_enabled=bool(data.get("webhook_enabled", False)),
        webhook_path=data.get("webhook_path", "pull"),
        poll_interval_minutes=data.get("poll_interval_minutes", 15),
        yaml_modules_enabled=bool(yaml_modules_enabled),
        ui_theme=ui_theme,
    )


def load_options() -> Options:
    if not settings.GITOPS_CONFIG_PATH.exists():
        seed: dict[str, Any] = {}
        if settings.OPTIONS_PATH.exists():
            seed = json.loads(read_text(settings.OPTIONS_PATH))
        write_gitops_config(_build_options(seed))
    data = load_gitops_config()
    if settings.GITOPS_CONFIG_PATH.exists():
        content = read_text(settings.GITOPS_CONFIG_PATH)
        if "merge_automations:" in content and "yaml_modules_enabled:" not in content:
            write_gitops_config(_build_options(data))
    origin_url = get_origin_url()
    if origin_url and data.get("remote_url") != origin_url:
        data["remote_url"] = origin_url
        write_gitops_config(_build_options(data))
    return _build_options(data)


def _coerce_config_value(key: str, value: Any) -> Any:
    if key in {"notification_enabled", "webhook_enabled", "yaml_modules_enabled"}:
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be true or false")
    if key in {"remote_url", "remote_branch", "webhook_path"}:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        raise ValueError(f"{key} must be a string")
    if key == "ui_theme":
        if isinstance(value, str) and value.lower() in {"light", "dark", "system"}:
            return value.lower()
        raise ValueError("ui_theme must be light, dark, or system")
    if key == "poll_interval_minutes":
        if value is None:
            return None
        if isinstance(value, int):
            return value
        raise ValueError("poll_interval_minutes must be an integer or null")
    raise ValueError(f"Unsupported config key: {key}")


def load_config_data() -> dict[str, Any]:
    if not settings.GITOPS_CONFIG_PATH.exists():
        write_gitops_config(OPTIONS)
    return load_gitops_config()


def load_full_config() -> dict[str, Any]:
    data = load_config_data()
    data["git_user_name"] = get_git_config_value("user.name")
    data["git_user_email"] = get_git_config_value("user.email")
    return data


def apply_config_update(payload: dict[str, Any]) -> dict[str, Any]:
    data = load_config_data()
    for key, value in payload.items():
        if key not in CONFIG_KEYS:
            raise ValueError(f"Unsupported config key: {key}")
        data[key] = _coerce_config_value(key, value)
    updated = _build_options(data)
    write_gitops_config(updated)
    return load_gitops_config()


def ensure_gitops_config() -> None:
    if settings.GITOPS_CONFIG_PATH.exists():
        return
    write_gitops_config(OPTIONS)


OPTIONS = load_options()

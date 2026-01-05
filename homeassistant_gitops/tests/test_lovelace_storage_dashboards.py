import importlib.machinery
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "homeassistant_gitops/rootfs/app/main.py"


def load_main(tmp_path: Path):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    options_path = tmp_path / "options.json"
    options_path.write_text(json.dumps({"yaml_modules_enabled": True}), encoding="utf-8")

    os.environ["HASS_CONFIG_DIR"] = str(config_dir)
    os.environ["HASS_OPTIONS_PATH"] = str(options_path)

    for module_name in list(sys.modules):
        if module_name.startswith("gitops_bridge"):
            sys.modules.pop(module_name, None)

    module_name = f"ha_gitops_main_{uuid.uuid4().hex}"
    loader = importlib.machinery.SourceFileLoader(module_name, str(APP_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module, config_dir


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_update_exports_storage_dashboards_to_unassigned(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    storage_dir = Path(os.environ["HASS_CONFIG_DIR"]) / ".storage"
    dashboards_path = storage_dir / "lovelace_dashboards"
    dashboard_id = "dashboard_test"

    dashboards_payload = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace_dashboards",
        "data": {
            "items": [
                {
                    "id": dashboard_id,
                    "title": "Test",
                    "icon": "mdi:test-tube",
                    "url_path": "dashboard-test",
                    "mode": "storage",
                    "require_admin": False,
                    "show_in_sidebar": True,
                }
            ]
        },
    }
    write_text(dashboards_path, json.dumps(dashboards_payload, indent=2))

    config = {"views": [{"title": "One", "path": "one", "cards": []}]}
    storage_payload = {
        "version": 1,
        "minor_version": 1,
        "key": f"lovelace.{dashboard_id}",
        "data": {"config": config},
    }
    write_text(storage_dir / f"lovelace.{dashboard_id}", json.dumps(storage_payload, indent=2))

    config_dir = Path(os.environ["HASS_CONFIG_DIR"])
    stale_path = config_dir / "packages/unassigned/lovelace.stale.unassigned.yaml"
    write_yaml(stale_path, {"views": []})

    result = yaml_modules.update_yaml_modules()
    exported_path = config_dir / f"packages/unassigned/lovelace.{dashboard_id}.unassigned.yaml"
    assert exported_path.exists()
    assert yaml.safe_load(exported_path.read_text(encoding="utf-8")) == config
    assert not stale_path.exists()
    assert (
        f"packages/unassigned/lovelace.{dashboard_id}.unassigned.yaml"
        in result.get("changed_files", [])
    )


def test_sync_exports_storage_dashboards_to_unassigned(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    config_dir = Path(os.environ["HASS_CONFIG_DIR"])
    storage_dir = config_dir / ".storage"
    dashboard_id = "dashboard_test"

    config = {"views": [{"title": "One", "path": "one", "cards": []}]}
    storage_payload = {
        "version": 1,
        "minor_version": 1,
        "key": f"lovelace.{dashboard_id}",
        "data": {"config": config},
    }
    write_text(storage_dir / f"lovelace.{dashboard_id}", json.dumps(storage_payload, indent=2))

    stale_path = config_dir / "packages/unassigned/lovelace.stale.unassigned.yaml"
    write_yaml(stale_path, {"views": []})

    result = yaml_modules.sync_yaml_modules()
    exported_path = config_dir / f"packages/unassigned/lovelace.{dashboard_id}.unassigned.yaml"
    assert exported_path.exists()
    assert yaml.safe_load(exported_path.read_text(encoding="utf-8")) == config
    assert stale_path.exists()
    assert (
        f"packages/unassigned/lovelace.{dashboard_id}.unassigned.yaml"
        in result.get("changed_files", [])
    )


def test_build_uses_first_package_dashboard_override(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    config_dir = Path(os.environ["HASS_CONFIG_DIR"])
    storage_dir = config_dir / ".storage"
    dashboards_path = storage_dir / "lovelace_dashboards"
    dashboard_id = "dashboard_test"

    dashboards_payload = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace_dashboards",
        "data": {"items": [{"id": dashboard_id, "mode": "storage"}]},
    }
    write_text(dashboards_path, json.dumps(dashboards_payload, indent=2))
    write_text(
        storage_dir / f"lovelace.{dashboard_id}",
        json.dumps(
            {
                "version": 1,
                "minor_version": 1,
                "key": f"lovelace.{dashboard_id}",
                "data": {"config": {"views": []}},
            },
            indent=2,
        ),
    )

    config_a = {"views": [{"title": "From A", "path": "a", "cards": []}]}
    config_b = {"views": [{"title": "From B", "path": "b", "cards": []}]}
    write_yaml(config_dir / f"packages/aaa/lovelace.{dashboard_id}.yaml", config_a)
    write_yaml(config_dir / f"packages/zzz/lovelace.{dashboard_id}.yaml", config_b)

    result = yaml_modules.build_yaml_modules()
    storage_payload = json.loads((storage_dir / f"lovelace.{dashboard_id}").read_text(encoding="utf-8"))
    assert storage_payload["data"]["config"] == config_a
    assert any(
        f"Duplicate lovelace dashboard {dashboard_id}" in warning
        for warning in result.get("warnings", [])
    )


def test_index_includes_unassigned_storage_dashboard_files(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    config_dir = Path(os.environ["HASS_CONFIG_DIR"])
    dashboard_path = config_dir / "packages/unassigned/lovelace.dashboard_test.unassigned.yaml"
    write_yaml(dashboard_path, {"views": []})

    legacy_path = config_dir / "lovelace/lovelace.unassigned.yaml"
    write_yaml(legacy_path, {"views": []})

    index = yaml_modules.list_yaml_modules_index()
    modules = {module["id"]: module for module in index.get("modules", [])}
    lovelace_unassigned = modules["unassigned:lovelace"]["files"]
    assert "packages/unassigned/lovelace.dashboard_test.unassigned.yaml" in lovelace_unassigned
    assert "lovelace/lovelace.unassigned.yaml" in lovelace_unassigned

    items = yaml_modules.list_module_items("packages/unassigned/lovelace.dashboard_test.unassigned.yaml")
    assert items["file_kind"] == "file"
    assert items["items"] == []

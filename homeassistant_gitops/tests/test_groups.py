import asyncio
import importlib.machinery
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_PATH = REPO_ROOT / "addons/homeassistant_gitops/rootfs/app/main.py"


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


def get_groups_module():
    return sys.modules["gitops_bridge.groups"]


def read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_groups_config_round_trip(tmp_path: Path) -> None:
    _main, config_dir = load_main(tmp_path)
    groups = get_groups_module()

    saved = groups.save_groups_config(
        {"schema_version": 1, "ignored": {"entity_ids": ["Group.Kitchen", " group.kitchen "]}}
    )
    assert saved["ignored"]["entity_ids"] == ["group.kitchen"]

    config_path = config_dir / ".gitops/groups.config.yaml"
    assert config_path.exists()
    loaded = groups.load_groups_config()
    assert loaded["ignored"]["entity_ids"] == ["group.kitchen"]


def test_upsert_group_creates_one_off_module_and_syncs(tmp_path: Path) -> None:
    _main, config_dir = load_main(tmp_path)
    groups = get_groups_module()

    result = groups.upsert_group(
        {
            "object_id": "kitchen",
            "name": "Kitchen",
            "members": ["light.a", "switch.b"],
            "destination": {"type": "one_off", "filename": "my_groups.yaml"},
        }
    )

    assert result["status"] == "saved"
    assert result["object_id"] == "kitchen"
    assert result["sync"]["status"] == "synced"
    assert result["restart"]["restart_needed"] is True

    one_off_path = config_dir / "groups/my_groups.yaml"
    domain_path = config_dir / "groups.yaml"
    mapping_path = config_dir / ".gitops/mappings/group.yaml"

    assert one_off_path.exists()
    assert domain_path.exists()
    assert mapping_path.exists()

    module_yaml = read_yaml(one_off_path)
    assert module_yaml["kitchen"]["name"] == "Kitchen"
    assert module_yaml["kitchen"]["entities"] == ["light.a", "switch.b"]

    domain_yaml = read_yaml(domain_path)
    assert domain_yaml["kitchen"]["entities"] == ["light.a", "switch.b"]

    mapping = read_yaml(mapping_path)
    assert any(
        entry.get("id") == "kitchen" and entry.get("source") == "groups/my_groups.yaml"
        for entry in mapping.get("entries", [])
    )


def test_delete_group_removes_definition(tmp_path: Path) -> None:
    _main, config_dir = load_main(tmp_path)
    groups = get_groups_module()

    groups.upsert_group(
        {
            "object_id": "kitchen",
            "name": "Kitchen",
            "members": ["light.a"],
            "destination": {"type": "one_off", "filename": "my_groups.yaml"},
        }
    )

    result = groups.delete_group("kitchen")
    assert result["status"] == "deleted"

    module_yaml = read_yaml(config_dir / "groups/my_groups.yaml")
    assert "kitchen" not in module_yaml

    domain_yaml = read_yaml(config_dir / "groups.yaml")
    assert "kitchen" not in domain_yaml


def test_restart_ack_tracks_changes(tmp_path: Path) -> None:
    _main, _config_dir = load_main(tmp_path)
    groups = get_groups_module()

    groups.upsert_group(
        {
            "object_id": "kitchen",
            "name": "Kitchen",
            "members": ["light.a"],
            "destination": {"type": "one_off", "filename": "my_groups.yaml"},
        }
    )

    status = groups.restart_status()
    assert status["restart_needed"] is True

    status = groups.ack_restart()
    assert status["restart_needed"] is False

    groups.upsert_group(
        {
            "object_id": "kitchen",
            "name": "Kitchen updated",
            "members": ["light.a"],
            "destination": {"type": "one_off", "filename": "my_groups.yaml"},
        }
    )
    status = groups.restart_status()
    assert status["restart_needed"] is True


def test_import_group_writes_yaml(tmp_path: Path, monkeypatch) -> None:
    _main, config_dir = load_main(tmp_path)
    groups = get_groups_module()

    async def fake_fetch_states():
        return [
            {
                "entity_id": "group.kitchen",
                "attributes": {
                    "friendly_name": "Kitchen group",
                    "entity_id": ["light.a", "switch.b"],
                },
            }
        ]

    monkeypatch.setattr(groups, "_fetch_states", fake_fetch_states)

    result = asyncio.run(
        groups.import_group(
            {
                "entity_id": "group.kitchen",
                "destination": {"type": "one_off", "filename": "imported.yaml"},
            }
        )
    )
    assert result["status"] == "saved"
    assert result["object_id"] == "kitchen"

    module_yaml = read_yaml(config_dir / "groups/imported.yaml")
    assert module_yaml["kitchen"]["name"] == "Kitchen group"
    assert module_yaml["kitchen"]["entities"] == ["light.a", "switch.b"]


def test_collision_check_rejects_unmanaged_group(tmp_path: Path, monkeypatch) -> None:
    load_main(tmp_path)
    groups = get_groups_module()

    async def fake_fetch_states():
        return [{"entity_id": "group.kitchen", "attributes": {"entity_id": []}}]

    monkeypatch.setattr(groups, "_fetch_states", fake_fetch_states)

    with pytest.raises(groups.GroupsError) as exc:
        asyncio.run(groups.assert_no_unmanaged_group_collision("kitchen"))

    assert exc.value.status_code == 409

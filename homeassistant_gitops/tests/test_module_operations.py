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


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def test_operate_move_to_existing_package_injects_id(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "automations/automations.unassigned.yaml",
        [{"alias": "Morning", "trigger": [], "action": []}],
    )
    write_yaml(
        config_dir / "packages/kitchen/automation.yaml",
        [{"alias": "Existing", "id": "Existing", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("automations/automations.unassigned.yaml")
    selector = listing["items"][0]["selector"]

    yaml_modules.operate_module_items(
        "move",
        [{"path": "automations/automations.unassigned.yaml", "selector": selector}],
        {"type": "existing_package", "package_name": "kitchen"},
    )

    package_items = yaml.safe_load(
        (config_dir / "packages/kitchen/automation.yaml").read_text(encoding="utf-8")
    )
    moved = next(item for item in package_items if item.get("alias") == "Morning")
    assert moved["id"] == "morning"

    unassigned = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    unassigned = unassigned or []
    assert not any(item.get("alias") == "Morning" for item in unassigned)

    domain_items = yaml.safe_load(
        (config_dir / "automations.yaml").read_text(encoding="utf-8")
    )
    assert any(item.get("alias") == "Morning" for item in domain_items)


def test_operate_move_to_one_off_creates_file(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "automations/automations.unassigned.yaml",
        [{"alias": "Laundry", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("automations/automations.unassigned.yaml")
    selector = listing["items"][0]["selector"]

    yaml_modules.operate_module_items(
        "move",
        [{"path": "automations/automations.unassigned.yaml", "selector": selector}],
        {"type": "one_off", "one_off_filename": "laundry.yaml"},
    )

    one_off_path = config_dir / "automations/laundry.yaml"
    assert one_off_path.exists()
    one_off_items = yaml.safe_load(one_off_path.read_text(encoding="utf-8"))
    assert any(item.get("alias") == "Laundry" for item in one_off_items)


def test_operate_unassign_helpers_moves_to_unassigned(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "packages/house/helpers.yaml",
        {"input_boolean": {"front_lights": {"name": "Front lights"}}},
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("packages/house/helpers.yaml")
    selector = listing["items"][0]["selector"]

    yaml_modules.operate_module_items(
        "unassign",
        [{"path": "packages/house/helpers.yaml", "selector": selector}],
    )

    helpers_data = yaml.safe_load(
        (config_dir / "packages/house/helpers.yaml").read_text(encoding="utf-8")
    )
    helpers_data = helpers_data or {}
    assert "front_lights" not in helpers_data.get("input_boolean", {})

    unassigned = yaml.safe_load(
        (config_dir / "helpers/helpers.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert "front_lights" in (unassigned or {}).get("input_boolean", {})


def test_operate_delete_removes_domain_item(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "packages/house/automation.yaml",
        [{"alias": "Remove me", "trigger": [], "action": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "Remove me", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("packages/house/automation.yaml")
    selector = listing["items"][0]["selector"]

    yaml_modules.operate_module_items(
        "delete",
        [{"path": "packages/house/automation.yaml", "selector": selector}],
    )

    module_items = yaml.safe_load(
        (config_dir / "packages/house/automation.yaml").read_text(encoding="utf-8")
    )
    module_items = module_items or []
    assert not any(item.get("alias") == "Remove me" for item in module_items)

    domain_items = yaml.safe_load(
        (config_dir / "automations.yaml").read_text(encoding="utf-8")
    )
    domain_items = domain_items or []
    assert not any(item.get("alias") == "Remove me" for item in domain_items)

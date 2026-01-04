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


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def test_list_read_write_list_item(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "packages/demo/automation.yaml",
        [{"alias": "Wake up", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("packages/demo/automation.yaml")
    assert listing["file_kind"] == "list"
    assert listing["items"][0]["id"] == "wake_up"

    selector = listing["items"][0]["selector"]
    read_payload = yaml_modules.read_module_item("packages/demo/automation.yaml", selector)
    assert "alias: Wake up" in read_payload["yaml"]

    updated_yaml = "alias: Wake up updated\ntrigger: []\naction: []\n"
    yaml_modules.write_module_item("packages/demo/automation.yaml", selector, updated_yaml)
    updated = yaml.safe_load(
        (config_dir / "packages/demo/automation.yaml").read_text(encoding="utf-8")
    )
    assert updated[0]["alias"] == "Wake up updated"


def test_list_read_write_mapping_item(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "scripts/turn_on.yaml",
        {"turn_on": {"alias": "Turn on", "sequence": []}},
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("scripts/turn_on.yaml")
    assert listing["file_kind"] == "mapping"
    selector = listing["items"][0]["selector"]

    read_payload = yaml_modules.read_module_item("scripts/turn_on.yaml", selector)
    assert "alias: Turn on" in read_payload["yaml"]

    updated_yaml = "alias: Updated\nsequence: []\n"
    yaml_modules.write_module_item("scripts/turn_on.yaml", selector, updated_yaml)
    updated = yaml.safe_load((config_dir / "scripts/turn_on.yaml").read_text(encoding="utf-8"))
    assert updated["turn_on"]["alias"] == "Updated"


def test_list_read_write_helper_item(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "helpers/mix.yaml",
        {"input_boolean": {"kitchen_motion": {"name": "Kitchen motion"}}},
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("helpers/mix.yaml")
    assert listing["file_kind"] == "helpers"
    selector = listing["items"][0]["selector"]

    read_payload = yaml_modules.read_module_item("helpers/mix.yaml", selector)
    assert "name: Kitchen motion" in read_payload["yaml"]

    updated_yaml = "name: Updated motion\n"
    yaml_modules.write_module_item("helpers/mix.yaml", selector, updated_yaml)
    updated = yaml.safe_load((config_dir / "helpers/mix.yaml").read_text(encoding="utf-8"))
    assert updated["input_boolean"]["kitchen_motion"]["name"] == "Updated motion"


def test_list_read_write_lovelace_item(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "lovelace/home.yaml",
        {"title": "My UI", "views": [{"title": "Home", "path": "home"}]},
    )

    yaml_modules = get_yaml_modules_module()
    listing = yaml_modules.list_module_items("lovelace/home.yaml")
    assert listing["file_kind"] == "lovelace"
    selector = listing["items"][0]["selector"]

    read_payload = yaml_modules.read_module_item("lovelace/home.yaml", selector)
    assert "title: Home" in read_payload["yaml"]

    updated_yaml = "title: Home updated\npath: home\n"
    yaml_modules.write_module_item("lovelace/home.yaml", selector, updated_yaml)
    updated = yaml.safe_load((config_dir / "lovelace/home.yaml").read_text(encoding="utf-8"))
    assert updated["title"] == "My UI"
    assert updated["views"][0]["title"] == "Home updated"


def test_templates_are_rejected(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "templates/demo.yaml",
        [{"trigger": [], "sensor": {"name": "Demo"}}],
    )

    yaml_modules = get_yaml_modules_module()
    with pytest.raises(ValueError):
        yaml_modules.list_module_items("templates/demo.yaml")

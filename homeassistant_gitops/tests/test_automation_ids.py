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


def test_automation_alias_used_for_id(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "packages/spike/automation.yaml",
        [{"alias": "Wake up", "trigger": [], "action": []}],
    )

    main.sync_yaml_modules()

    module_items = yaml.safe_load(
        (config_dir / "packages/spike/automation.yaml").read_text(encoding="utf-8")
    )
    assert module_items[0]["id"] == "wake_up"


def test_automation_duplicate_alias_ids_are_unique(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)
    write_yaml(
        config_dir / "packages/spike/automation.yaml",
        [
            {"alias": "Repeat", "trigger": [], "action": []},
            {"alias": "Repeat", "trigger": [], "action": []},
        ],
    )

    main.sync_yaml_modules()

    module_items = yaml.safe_load(
        (config_dir / "packages/spike/automation.yaml").read_text(encoding="utf-8")
    )
    ids = [item["id"] for item in module_items]
    assert len(set(ids)) == 2
    assert ids[0] == "repeat"
    assert ids[1] == "repeat_2"


def test_reconcile_automation_ids_updates_modules(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/spike/automation.yaml",
        [{"alias": "Kitchen", "id": "Kitchen", "trigger": [], "action": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "Kitchen", "id": "ha-123", "trigger": [], "action": []}],
    )

    yaml_modules = sys.modules["gitops_bridge.yaml_modules"]
    result = yaml_modules.reconcile_automation_ids()

    module_items = yaml.safe_load(
        (config_dir / "packages/spike/automation.yaml").read_text(encoding="utf-8")
    )
    assert module_items[0]["id"] == "ha-123"
    assert result["status"] == "reconciled"

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


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def test_validate_reports_parse_warnings(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    (config_dir / "automations.yaml").write_text(":- bad", encoding="utf-8")

    yaml_modules = get_yaml_modules_module()
    report = yaml_modules.validate_yaml_modules()

    assert report["summary"]["warnings"] >= 1
    assert any("automations.yaml" in warning for warning in report["warnings"])

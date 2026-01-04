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


def get_cli_installer_module():
    return sys.modules["gitops_bridge.cli_installer"]


def test_cli_install_writes_files(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    cli_installer = get_cli_installer_module()

    result = cli_installer.install_cli(overwrite=False)
    assert result["status"] == "installed"

    cli_dir = config_dir / ".gitops/cli"
    assert (cli_dir / "gitops_cli.py").exists()
    assert (cli_dir / "README.md").exists()


def test_cli_install_requires_overwrite(tmp_path: Path) -> None:
    load_main(tmp_path)
    cli_installer = get_cli_installer_module()
    cli_installer.install_cli(overwrite=False)

    with pytest.raises(cli_installer.CliInstallError) as exc:
        cli_installer.install_cli(overwrite=False)

    assert exc.value.status_code == 409


def test_cli_install_overwrite(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    cli_installer = get_cli_installer_module()

    cli_installer.install_cli(overwrite=False)
    (config_dir / ".gitops/cli/gitops_cli.py").write_text("stub", encoding="utf-8")

    result = cli_installer.install_cli(overwrite=True)
    assert result["status"] == "installed"
    content = (config_dir / ".gitops/cli/gitops_cli.py").read_text(encoding="utf-8")
    assert "validate" in content

import importlib.machinery
import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

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


def get_git_ops():
    return sys.modules["gitops_bridge.git_ops"]


def get_gitignore_ops():
    return sys.modules["gitops_bridge.gitignore_ops"]


def init_repo(git_ops):
    git_ops.run_git(["init", "-b", "main"])
    git_ops.run_git(["config", "user.name", "Test User"])
    git_ops.run_git(["config", "user.email", "test@example.com"])


def test_git_list_files_modes(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    git_ops = get_git_ops()

    init_repo(git_ops)
    (config_dir / "automations.yaml").write_text("one\n", encoding="utf-8")
    (config_dir / "scripts.yaml").write_text("base\n", encoding="utf-8")
    git_ops.run_git(["add", "-A"])
    git_ops.run_git(["commit", "-m", "init"])

    (config_dir / "automations.yaml").write_text("two\n", encoding="utf-8")
    git_ops.run_git(["add", "automations.yaml"])
    (config_dir / "automations.yaml").write_text("three\n", encoding="utf-8")
    (config_dir / "untracked.yaml").write_text("hello\n", encoding="utf-8")

    (config_dir / ".gitignore").write_text("ignored.log\n", encoding="utf-8")
    (config_dir / "ignored.log").write_text("ignored\n", encoding="utf-8")

    changed = git_ops.git_list_files("changed")
    changed_paths = {entry["path"]: entry for entry in changed}
    assert "automations.yaml" in changed_paths
    assert changed_paths["automations.yaml"]["staged"] is True
    assert changed_paths["automations.yaml"]["unstaged"] is True
    assert "untracked.yaml" in changed_paths
    assert changed_paths["untracked.yaml"]["untracked"] is True

    all_files = git_ops.git_list_files("all")
    all_paths = {entry["path"]: entry for entry in all_files}
    assert all_paths["scripts.yaml"]["clean"] is True
    assert all_paths["automations.yaml"]["clean"] is False
    assert all_paths["untracked.yaml"]["untracked"] is True
    assert "ignored.log" not in all_paths

    all_with_ignored = git_ops.git_list_files("all", include_ignored=True)
    assert any(entry["path"] == "ignored.log" and entry["ignored"] for entry in all_with_ignored)


def test_git_file_preview_head_and_binary(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    git_ops = get_git_ops()

    init_repo(git_ops)
    (config_dir / "text.txt").write_text("hello\n", encoding="utf-8")
    (config_dir / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
    git_ops.run_git(["add", "-A"])
    git_ops.run_git(["commit", "-m", "add files"])

    text_preview = git_ops.git_file_preview("text.txt", ref="head")
    assert text_preview["is_binary"] is False
    assert "hello" in text_preview["content"]

    binary_preview = git_ops.git_file_preview("binary.bin", ref="head")
    assert binary_preview["is_binary"] is True


def test_gitignore_override_and_path_validation(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    git_ops = get_git_ops()
    gitignore_ops = get_gitignore_ops()

    init_repo(git_ops)
    (config_dir / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (config_dir / "ignored.txt").write_text("secret\n", encoding="utf-8")

    assert git_ops.git_check_ignore("ignored.txt")["ignored"] is True
    changed = gitignore_ops.update_managed_block("ignored.txt", "override")
    assert changed is True
    assert "!ignored.txt" in (config_dir / ".gitignore").read_text(encoding="utf-8")
    assert git_ops.git_check_ignore("ignored.txt")["ignored"] is False

    with pytest.raises(ValueError):
        git_ops.normalize_repo_path("../secrets.yaml")

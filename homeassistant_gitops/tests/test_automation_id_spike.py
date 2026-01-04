import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = REPO_ROOT / "addons/homeassistant_gitops/rootfs/app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def load_spike_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HASS_CONFIG_DIR", str(tmp_path))
    for name in list(sys.modules):
        if name.startswith("gitops_bridge"):
            sys.modules.pop(name, None)
    return importlib.import_module("gitops_bridge.spikes.automation_id_spike")


def test_snapshot_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spike = load_spike_module(tmp_path, monkeypatch)
    target = tmp_path / "automations.yaml"
    target.write_text("alias: test\n", encoding="utf-8")

    output_dir = tmp_path / "out"
    output_path = spike.snapshot("my label", ["automations.yaml"], output_dir=output_dir)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["label"] == "my label"
    assert payload["files"][0]["path"] == "automations.yaml"
    assert payload["files"][0]["content"] == "alias: test\n"


def test_snapshot_rejects_absolute_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spike = load_spike_module(tmp_path, monkeypatch)
    absolute_path = tmp_path / "automations.yaml"

    with pytest.raises(ValueError):
        spike.snapshot("abs", [str(absolute_path)], output_dir=tmp_path / "out")


def test_snapshot_rejects_parent_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spike = load_spike_module(tmp_path, monkeypatch)

    with pytest.raises(ValueError):
        spike.snapshot("parent", ["../secrets.yaml"], output_dir=tmp_path / "out")

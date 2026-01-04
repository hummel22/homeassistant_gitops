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


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_yaml_modules_module():
    return sys.modules["gitops_bridge.yaml_modules"]


def test_list_yaml_modules_index_includes_packages_one_offs_and_unassigned(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/kitchen/automations.yaml",
        [{"alias": "Kitchen automation", "trigger": []}],
    )
    write_yaml(config_dir / "packages/bedroom.yaml", {"sensor": {"bedroom_temp": {}}})
    write_yaml(
        config_dir / "automations/oneoff.yaml",
        [{"alias": "One-off", "trigger": []}],
    )
    write_yaml(config_dir / "scripts/turn_on.yaml", {"alias": "Turn on"})
    write_yaml(
        config_dir / "automations/automations.unassigned.yaml",
        [{"alias": "Unassigned", "trigger": []}],
    )

    yaml_modules = get_yaml_modules_module()
    index = yaml_modules.list_yaml_modules_index()
    modules = {module["id"]: module for module in index["modules"]}

    assert "package:kitchen" in modules
    assert "package:bedroom" in modules
    assert "one_offs:automations" in modules
    assert "one_offs:scripts" in modules
    assert "unassigned:automations" in modules
    assert "packages/kitchen/automations.yaml" in modules["package:kitchen"]["files"]
    assert "packages/bedroom.yaml" in modules["package:bedroom"]["files"]
    assert "automations/oneoff.yaml" in modules["one_offs:automations"]["files"]
    assert "scripts/turn_on.yaml" in modules["one_offs:scripts"]["files"]
    assert (
        "automations/automations.unassigned.yaml"
        in modules["unassigned:automations"]["files"]
    )


def test_module_file_round_trip(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)
    target = config_dir / "automations/demo.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("alias: demo\n", encoding="utf-8")

    yaml_modules = get_yaml_modules_module()
    payload = yaml_modules.read_module_file("automations/demo.yaml")
    assert "alias: demo" in payload["content"]

    yaml_modules.write_module_file("automations/demo.yaml", "alias: updated\n")
    assert target.read_text(encoding="utf-8") == "alias: updated\n"

    yaml_modules.delete_module_file("automations/demo.yaml")
    assert not target.exists()


def test_module_file_rejects_invalid_path(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()

    with pytest.raises(ValueError):
        yaml_modules.read_module_file("../secrets.yaml")


def test_sync_builds_domain_and_unassigned(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations/dishwasher.yaml",
        [{"alias": "Dishwasher", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    result = main.sync_yaml_modules()
    assert result["status"] == "synced"

    domain_items = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    assert len(domain_items) == 3
    assert all("id" in item for item in domain_items)
    aliases = {item.get("alias") for item in domain_items}
    assert {"Wake up", "Dishwasher", "UI only"} <= aliases

    unassigned = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned[0]["alias"] == "UI only"

    mapping = yaml.safe_load(
        (config_dir / ".gitops/mappings/automation.yaml").read_text(encoding="utf-8")
    )
    assert len(mapping["entries"]) == 3


def test_sync_updates_from_domain_changes(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    main.sync_yaml_modules()

    domain_items = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    for item in domain_items:
        if item.get("alias") == "Wake up":
            item["alias"] = "Wake up updated"
        if item.get("alias") == "UI only":
            item["alias"] = "UI updated"
    write_yaml(config_dir / "automations.yaml", domain_items)

    main.sync_yaml_modules()

    module_items = yaml.safe_load(
        (config_dir / "packages/wakeup/automation.yaml").read_text(encoding="utf-8")
    )
    assert module_items[0]["alias"] == "Wake up updated"

    unassigned_items = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned_items[0]["alias"] == "UI updated"


def test_sync_prefers_modules_for_assigned_when_both_change(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": []}],
    )

    main.sync_yaml_modules()

    module_path = config_dir / "packages/wakeup/automation.yaml"
    module_items = yaml.safe_load(module_path.read_text(encoding="utf-8"))
    module_items[0]["alias"] = "Module wins"
    write_yaml(module_path, module_items)

    domain_path = config_dir / "automations.yaml"
    domain_items = yaml.safe_load(domain_path.read_text(encoding="utf-8"))
    for item in domain_items:
        if item.get("alias") == "Wake up":
            item["alias"] = "Domain loses"
        if item.get("alias") == "UI only":
            item["alias"] = "UI wins"
    write_yaml(domain_path, domain_items)

    main.sync_yaml_modules()

    module_items = yaml.safe_load(module_path.read_text(encoding="utf-8"))
    assert module_items[0]["alias"] == "Module wins"

    unassigned_items = yaml.safe_load(
        (config_dir / "automations/automations.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert unassigned_items[0]["alias"] == "UI wins"


def test_sync_helpers_split_to_domain_files(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/helpers.yaml",
        {
            "input_boolean": {"kitchen_motion": {"name": "Kitchen motion"}},
            "input_datetime": {"wake_time": {"name": "Wake time"}},
        },
    )

    main.sync_yaml_modules()

    input_boolean = yaml.safe_load(
        (config_dir / "input_boolean.yaml").read_text(encoding="utf-8")
    )
    input_datetime = yaml.safe_load(
        (config_dir / "input_datetime.yaml").read_text(encoding="utf-8")
    )
    assert "kitchen_motion" in input_boolean
    assert "wake_time" in input_datetime


def test_template_includes_expand_into_domain_outputs(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_text(
        config_dir / "packages/common_actions.template.yaml",
        "- service: logbook.log\n  data:\n    name: From template\n",
    )
    write_text(
        config_dir / "packages/wakeup/automation.yaml",
        "- alias: Wake up\n"
        "  id: wake_up\n"
        "  trigger: []\n"
        "  action: !/packages/common_actions.template.yaml\n",
    )

    result = main.sync_yaml_modules()
    assert result["status"] == "synced"

    domain_items = yaml.safe_load((config_dir / "automations.yaml").read_text(encoding="utf-8"))
    wake_up = next(item for item in domain_items if item.get("id") == "wake_up")
    assert wake_up["action"][0]["service"] == "logbook.log"

    module_text = (config_dir / "packages/wakeup/automation.yaml").read_text(encoding="utf-8")
    assert "!/packages/common_actions.template.yaml" in module_text


def test_template_backed_domain_edits_generate_diff_and_preserve_module_tag(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_text(
        config_dir / "packages/common_actions.template.yaml",
        "- service: logbook.log\n  data:\n    name: From template\n",
    )
    write_text(
        config_dir / "packages/wakeup/automation.yaml",
        "- alias: Wake up\n"
        "  id: wake_up\n"
        "  trigger: []\n"
        "  action: !/packages/common_actions.template.yaml\n",
    )

    main.sync_yaml_modules()

    domain_path = config_dir / "automations.yaml"
    domain_items = yaml.safe_load(domain_path.read_text(encoding="utf-8"))
    for item in domain_items:
        if item.get("id") != "wake_up":
            continue
        item["alias"] = "Wake up updated"
        item["action"][0]["service"] = "logbook.write"
    write_yaml(domain_path, domain_items)

    main.sync_yaml_modules()

    module_text = (config_dir / "packages/wakeup/automation.yaml").read_text(encoding="utf-8")
    assert "Wake up updated" in module_text
    assert "!/packages/common_actions.template.yaml" in module_text

    diff_path = config_dir / "packages/common_actions.template.yaml.diff"
    diff_text = diff_path.read_text(encoding="utf-8")
    assert "automations.yaml" in diff_text
    assert "packages/wakeup/automation.yaml" in diff_text
    assert "diff --git a/packages/common_actions.template.yaml b/packages/common_actions.template.yaml" in diff_text

    domain_items_after = yaml.safe_load(domain_path.read_text(encoding="utf-8"))
    wake_up = next(item for item in domain_items_after if item.get("id") == "wake_up")
    assert wake_up["alias"] == "Wake up updated"
    assert wake_up["action"][0]["service"] == "logbook.log"


def test_template_fingerprints_change_when_template_changes(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    template_path = config_dir / "packages/common_actions.template.yaml"
    write_text(
        template_path,
        "- service: logbook.log\n  data:\n    name: From template\n",
    )
    write_text(
        config_dir / "packages/wakeup/automation.yaml",
        "- alias: Wake up\n"
        "  id: wake_up\n"
        "  trigger: []\n"
        "  action: !/packages/common_actions.template.yaml\n",
    )

    main.sync_yaml_modules()

    mapping_path = config_dir / ".gitops/mappings/automation.yaml"
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    first_fp = next(entry["fingerprint"] for entry in mapping["entries"] if entry["id"] == "wake_up")

    write_text(
        template_path,
        "- service: logbook.log\n  data:\n    name: From template v2\n",
    )
    main.sync_yaml_modules()

    mapping_after = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    second_fp = next(
        entry["fingerprint"] for entry in mapping_after["entries"] if entry["id"] == "wake_up"
    )
    assert first_fp != second_fp


def test_sync_groups_mapping_domain_round_trip(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/kitchen/groups.yaml",
        {"kitchen": {"name": "Kitchen", "entities": ["light.kitchen"]}},
    )

    main.sync_yaml_modules()

    groups_domain = yaml.safe_load((config_dir / "groups.yaml").read_text(encoding="utf-8"))
    assert "kitchen" in groups_domain

    groups_domain["ui_only"] = {"name": "UI only", "entities": ["light.ui"]}
    write_yaml(config_dir / "groups.yaml", groups_domain)

    main.sync_yaml_modules()

    unassigned = yaml.safe_load(
        (config_dir / "groups/groups.unassigned.yaml").read_text(encoding="utf-8")
    )
    assert "ui_only" in unassigned


def test_groups_resolve_include_tags_in_domain_output(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(config_dir / "groups/includes/members.yaml", ["light.a", "light.b"])
    write_text(
        config_dir / "groups/living_room.yaml",
        "living_room:\n"
        "  name: Living Room\n"
        "  entities: !include includes/members.yaml\n",
    )

    main.sync_yaml_modules()

    domain_text = (config_dir / "groups.yaml").read_text(encoding="utf-8")
    assert "!include" not in domain_text
    domain_data = yaml.safe_load(domain_text)
    assert domain_data["living_room"]["entities"] == ["light.a", "light.b"]


def test_modules_index_includes_groups_one_offs_and_unassigned(tmp_path: Path) -> None:
    load_main(tmp_path)
    yaml_modules = get_yaml_modules_module()
    config_dir = Path(os.environ["HASS_CONFIG_DIR"])

    write_yaml(
        config_dir / "groups/custom.yaml",
        {"demo": {"name": "Demo", "entities": ["light.a"]}},
    )
    write_yaml(
        config_dir / "groups/groups.unassigned.yaml",
        {"unassigned": {"name": "Unassigned", "entities": ["light.b"]}},
    )

    index = yaml_modules.list_yaml_modules_index()
    modules = {module["id"]: module for module in index["modules"]}

    assert "one_offs:groups" in modules
    assert "unassigned:groups" in modules
    assert "groups/custom.yaml" in modules["one_offs:groups"]["files"]
    assert "groups/groups.unassigned.yaml" in modules["unassigned:groups"]["files"]


def test_preview_yaml_modules_separates_build_and_update(tmp_path: Path) -> None:
    _, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/wakeup/automation.yaml",
        [{"alias": "Wake up", "trigger": [], "action": []}],
    )
    write_yaml(
        config_dir / "automations.yaml",
        [{"alias": "UI only", "trigger": [], "action": []}],
    )

    yaml_modules = get_yaml_modules_module()
    preview = yaml_modules.preview_yaml_modules()

    build_paths = {entry["path"] for entry in preview["build_diffs"]}
    update_paths = {entry["path"] for entry in preview["update_diffs"]}

    assert "automations.yaml" in build_paths
    assert "automations/automations.unassigned.yaml" in update_paths
    assert all(not path.startswith(".gitops/") for path in build_paths | update_paths)
    assert all(not path.startswith("system/") for path in build_paths | update_paths)


def test_automation_ids_are_normalized_and_unique(tmp_path: Path) -> None:
    main, config_dir = load_main(tmp_path)

    write_yaml(
        config_dir / "packages/a/automation.yaml",
        [{"alias": "KitchenLights", "trigger": []}],
    )
    write_yaml(
        config_dir / "packages/b/automation.yaml",
        [{"alias": "Kitchen Lights", "trigger": []}],
    )

    main.sync_yaml_modules()

    a_items = yaml.safe_load((config_dir / "packages/a/automation.yaml").read_text(encoding="utf-8"))
    b_items = yaml.safe_load((config_dir / "packages/b/automation.yaml").read_text(encoding="utf-8"))

    assert a_items[0]["id"] == "kitchen_lights"
    assert b_items[0]["id"] == "kitchen_lights_2"

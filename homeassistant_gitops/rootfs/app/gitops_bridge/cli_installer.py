from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from . import settings
from .config_store import ensure_gitops_dirs


CLI_DIRNAME = "cli"
CLI_FILES = {
    "gitops_cli.py": "CLI_SCRIPT",
    "README.md": "CLI_README",
}

CLI_SCRIPT = """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def detect_config_dir() -> Path:
    env_path = os.environ.get("HASS_CONFIG_DIR")
    if env_path:
        return Path(env_path)
    script_path = Path(__file__).resolve()
    candidate = script_path.parents[2]
    if (candidate / ".gitops").exists():
        return candidate
    cwd = Path.cwd()
    if (cwd / ".gitops").exists():
        return cwd
    return candidate


def inject_gitops_bridge(config_dir: Path) -> None:
    candidates = [
        Path("/app"),
        config_dir / "addons/homeassistant_gitops/rootfs/app",
    ]
    for candidate in candidates:
        if (candidate / "gitops_bridge").exists():
            sys.path.insert(0, str(candidate))
            return
    raise SystemExit(
        "gitops_bridge code not found. Run this CLI from a repo that includes the add-on "
        "or inside the add-on container."
    )


def load_yaml_modules():
    config_dir = detect_config_dir()
    os.environ.setdefault("HASS_CONFIG_DIR", str(config_dir))
    os.environ.setdefault("HASS_OPTIONS_PATH", str(config_dir / ".gitops/options.json"))
    inject_gitops_bridge(config_dir)
    from gitops_bridge import yaml_modules

    return yaml_modules


def format_report(report: dict) -> str:
    lines = [
        "Validation report",
        f"Status: {report.get('status')}",
        f"Errors: {report.get('summary', {}).get('errors', 0)}",
        f"Warnings: {report.get('summary', {}).get('warnings', 0)}",
        "",
    ]

    if report.get("errors"):
        lines.append("Errors:")
        for entry in report["errors"]:
            lines.append(f"- {entry}")
        lines.append("")

    if report.get("warnings"):
        lines.append("Warnings:")
        for entry in report["warnings"]:
            lines.append(f"- {entry}")
        lines.append("")

    lines.append("Domain checks:")
    for domain, info in report.get("domains", {}).items():
        errors = info.get("errors", [])
        warnings = info.get("warnings", [])
        changed = info.get("changed_files", [])
        lines.append(
            f"- {domain}: {len(errors)} errors, {len(warnings)} warnings, "
            f"{len(changed)} pending changes"
        )
        for entry in errors:
            lines.append(f"  error: {entry}")
        for entry in warnings:
            lines.append(f"  warning: {entry}")
    lines.append("")

    build = report.get("build", {})
    lines.append(f"Build changes ({build.get('count', 0)}):")
    for path in build.get("paths", []):
        lines.append(f"- {path}")
    if build.get("warnings"):
        for entry in build.get("warnings", []):
            lines.append(f"  warning: {entry}")
    lines.append("")

    update = report.get("update", {})
    lines.append(f"Update changes ({update.get('count', 0)}):")
    for path in update.get("paths", []):
        lines.append(f"- {path}")
    if update.get("warnings"):
        for entry in update.get("warnings", []):
            lines.append(f"  warning: {entry}")

    return "\n".join(lines)


def run_validate(args: argparse.Namespace) -> int:
    yaml_modules = load_yaml_modules()
    report = yaml_modules.validate_yaml_modules()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    if args.strict and report.get("summary", {}).get("errors"):
        return 1
    return 0


def run_build(_: argparse.Namespace) -> int:
    yaml_modules = load_yaml_modules()
    result = yaml_modules.build_yaml_modules()
    print("Build complete.")
    print(f"Changed files: {len(result.get('changed_files', []))}")
    for path in result.get("changed_files", []):
        print(f"- {path}")
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    return 0


def run_update(_: argparse.Namespace) -> int:
    yaml_modules = load_yaml_modules()
    result = yaml_modules.update_yaml_modules()
    print("Update complete.")
    print(f"Changed files: {len(result.get('changed_files', []))}")
    for path in result.get("changed_files", []):
        print(f"- {path}")
    for warning in result.get("warnings", []):
        print(f"warning: {warning}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Home Assistant GitOps CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate YAML modules")
    validate_parser.add_argument("--json", action="store_true", help="Output JSON report")
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if errors are present",
    )
    validate_parser.set_defaults(func=run_validate)

    build_parser = subparsers.add_parser("build", help="Build domain YAML from modules")
    build_parser.set_defaults(func=run_build)

    update_parser = subparsers.add_parser("update", help="Update modules from domain YAML")
    update_parser.set_defaults(func=run_update)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
"""

CLI_README = """# Home Assistant GitOps CLI

Run the CLI from the repo root (or inside the add-on container):

```
python3 .gitops/cli/gitops_cli.py validate
python3 .gitops/cli/gitops_cli.py validate --json
python3 .gitops/cli/gitops_cli.py validate --strict
python3 .gitops/cli/gitops_cli.py build
python3 .gitops/cli/gitops_cli.py update
```

Notes:
- `validate` collects warnings and errors without stopping at the first issue.
- `--strict` returns exit code 1 if errors are present.
- `build` writes domain YAML from module files.
- `update` writes module files from domain YAML.
"""


class CliInstallError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:
        return self.message


def _cli_dir() -> Path:
    return settings.GITOPS_DIR / CLI_DIRNAME


def _cli_paths() -> dict[str, Path]:
    return {
        name: _cli_dir() / name
        for name in CLI_FILES.keys()
    }


def install_cli(overwrite: bool = False) -> dict[str, Any]:
    ensure_gitops_dirs()
    cli_dir = _cli_dir()
    cli_dir.mkdir(parents=True, exist_ok=True)
    paths = _cli_paths()

    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise CliInstallError(
            "CLI already installed. Enable overwrite to replace existing files.",
            status_code=409,
        )

    (cli_dir / "gitops_cli.py").write_text(CLI_SCRIPT, encoding="utf-8")
    (cli_dir / "README.md").write_text(CLI_README, encoding="utf-8")

    try:
        os.chmod(cli_dir / "gitops_cli.py", 0o755)
    except OSError:
        pass

    return {
        "status": "installed",
        "path": cli_dir.relative_to(settings.CONFIG_DIR).as_posix(),
        "files": sorted(path.relative_to(settings.CONFIG_DIR).as_posix() for path in paths.values()),
    }

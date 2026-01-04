from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from gitops_bridge import settings
from gitops_bridge.fs_utils import read_text

SPIKE_DIR = settings.GITOPS_DIR / "spikes" / "automation-id"
LABEL_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    exists: bool
    content: str


def _sanitize_label(label: str) -> str:
    cleaned = LABEL_RE.sub("-", label.strip()).strip("-")
    return cleaned or "snapshot"


def _resolve_paths(raw_paths: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in raw_paths:
        if not raw or not raw.strip():
            continue
        candidate = Path(raw.strip())
        if candidate.is_absolute():
            raise ValueError("Paths must be relative to the Home Assistant config directory.")
        if ".." in candidate.parts:
            raise ValueError("Paths cannot include parent directory segments.")
        resolved = (settings.CONFIG_DIR / candidate).resolve()
        try:
            resolved.relative_to(settings.CONFIG_DIR)
        except ValueError as exc:
            raise ValueError("Paths must stay within the Home Assistant config directory.") from exc
        paths.append(resolved)
    if not paths:
        raise ValueError("At least one path is required.")
    return paths


def snapshot(label: str, raw_paths: list[str], output_dir: Path | None = None) -> Path:
    resolved_paths = _resolve_paths(raw_paths)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_label = _sanitize_label(label)
    payload = {
        "label": label,
        "timestamp": timestamp,
        "files": [],
    }
    for path in resolved_paths:
        rel_path = path.relative_to(settings.CONFIG_DIR).as_posix()
        payload["files"].append(
            SnapshotFile(
                path=rel_path,
                exists=path.exists(),
                content=read_text(path) if path.exists() else "",
            ).__dict__
        )

    target_dir = output_dir or SPIKE_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / f"{timestamp}-{safe_label}.json"
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture automation ID spike snapshots from Home Assistant config files."
    )
    parser.add_argument(
        "--label",
        required=True,
        help="Label for the snapshot (used in the output filename).",
    )
    parser.add_argument(
        "--path",
        action="append",
        dest="paths",
        required=True,
        help="Relative path to capture (repeatable).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Optional output directory (defaults to .gitops/spikes/automation-id).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else None
    output_path = snapshot(args.label, args.paths, output_dir=output_dir)
    print(output_path)


if __name__ == "__main__":
    main()

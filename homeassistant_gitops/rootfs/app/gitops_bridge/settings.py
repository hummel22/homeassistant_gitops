from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("HASS_CONFIG_DIR", "/config"))
OPTIONS_PATH = Path(os.environ.get("HASS_OPTIONS_PATH", "/data/options.json"))
GITOPS_DIR = CONFIG_DIR / ".gitops"
GITOPS_CONFIG_PATH = GITOPS_DIR / "config.yaml"
LEGACY_GITOPS_CONFIG_PATH = CONFIG_DIR / ".gitops.yaml"
MAPPINGS_DIR = GITOPS_DIR / "mappings"
SYNC_STATE_PATH = GITOPS_DIR / "sync-state.yaml"
EXPORTS_CONFIG_PATH = GITOPS_DIR / "exports.config.yaml"
SSH_DIR = CONFIG_DIR / ".ssh"
GITIGNORE_TEMPLATE = Path("/app/gitignore_example")
PACKAGES_DIR = CONFIG_DIR / "packages"
SYSTEM_EXPORTS_DIR = CONFIG_DIR / "system"
WATCH_EXTENSIONS = {".yaml", ".yml"}
DEBOUNCE_SECONDS = 0.6
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

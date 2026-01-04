from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from . import settings


def get_ssh_status() -> dict[str, Any]:
    key_path = settings.SSH_DIR / "id_ed25519"
    pub_path = settings.SSH_DIR / "id_ed25519.pub"
    ssh_keygen = shutil.which("ssh-keygen")
    ssh_client = shutil.which("ssh")
    ssh_add = shutil.which("ssh-add")
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if settings.SSH_DIR.exists():
        ssh_dir_writable = os.access(settings.SSH_DIR, os.W_OK)
    else:
        ssh_dir_writable = os.access(settings.CONFIG_DIR, os.W_OK)
    ssh_agent_available = ssh_add is not None and bool(ssh_auth_sock)
    ssh_key_loaded = False
    if ssh_agent_available and key_path.exists():
        list_result = subprocess.run(
            ["ssh-add", "-L"],
            capture_output=True,
            text=True,
            check=False,
        )
        if list_result.returncode == 0:
            ssh_key_loaded = key_path.name in list_result.stdout
    return {
        "ssh_dir": str(settings.SSH_DIR),
        "private_key_exists": key_path.exists(),
        "public_key_exists": pub_path.exists(),
        "ssh_dir_writable": ssh_dir_writable,
        "ssh_keygen_available": ssh_keygen is not None,
        "ssh_available": ssh_client is not None,
        "ssh_agent_available": ssh_agent_available,
        "ssh_key_loaded": ssh_key_loaded,
    }


def ensure_ssh_agent_key() -> None:
    key_path = settings.SSH_DIR / "id_ed25519"
    ssh_add = shutil.which("ssh-add")
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if not ssh_add or not ssh_auth_sock or not key_path.exists():
        return
    subprocess.run(
        ["ssh-add", str(key_path)],
        capture_output=True,
        text=True,
        check=False,
    )

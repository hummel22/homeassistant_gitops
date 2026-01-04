from __future__ import annotations

import os
from typing import Any

import httpx

from .config_store import OPTIONS


async def call_service(domain: str, service: str, data: dict[str, Any] | None = None) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    url = f"http://supervisor/core/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = data or {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, headers=headers, json=payload)


async def notify(title: str, message: str, notification_id: str) -> None:
    if not OPTIONS.notification_enabled:
        return
    await call_service(
        "persistent_notification",
        "create",
        {
            "title": title,
            "message": message,
            "notification_id": notification_id,
        },
    )

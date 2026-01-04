from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler

from . import settings
from .gitignore_ops import should_ignore


def create_tracker() -> dict[str, Any]:
    return {
        "pending": set(),
        "tasks": {},
        "lock": asyncio.Lock(),
        "loop": None,
    }


def set_tracker_loop(tracker: dict[str, Any], loop: asyncio.AbstractEventLoop) -> None:
    tracker["loop"] = loop


def schedule_path(tracker: dict[str, Any], rel_path: str) -> None:
    loop = tracker.get("loop")
    if loop is None:
        return

    def _schedule() -> None:
        existing = tracker["tasks"].get(rel_path)
        if existing:
            existing.cancel()
        tracker["tasks"][rel_path] = asyncio.create_task(_debounce_add(tracker, rel_path))

    loop.call_soon_threadsafe(_schedule)


async def _debounce_add(tracker: dict[str, Any], rel_path: str) -> None:
    await asyncio.sleep(settings.DEBOUNCE_SECONDS)
    async with tracker["lock"]:
        tracker["pending"].add(rel_path)
    tracker["tasks"].pop(rel_path, None)


async def flush_pending(tracker: dict[str, Any]) -> list[str]:
    async with tracker["lock"]:
        pending = sorted(tracker["pending"])
        tracker["pending"].clear()
    return pending


async def snapshot_pending(tracker: dict[str, Any]) -> list[str]:
    async with tracker["lock"]:
        return sorted(tracker["pending"])


class ConfigEventHandler(FileSystemEventHandler):
    def __init__(self, tracker: dict[str, Any]) -> None:
        self.tracker = tracker

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.is_relative_to(settings.CONFIG_DIR):
            rel = path.relative_to(settings.CONFIG_DIR)
        else:
            return
        if should_ignore(rel):
            return
        schedule_path(self.tracker, str(rel))

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle(event)

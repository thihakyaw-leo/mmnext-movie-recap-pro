"""Download control loop.

The controller owns the *policy* (what pause / resume / stop / retry mean)
and delegates the *mechanics* to a :class:`~mmnext.services.protocols.DownloadService`.

The stepping loop itself is meant to run on a worker thread. The controller
exposes a single :meth:`step` that a worker can call repeatedly, so the GUI
thread never blocks.
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from ..domain.enums import TaskState
from ..domain.models import DownloadItem, VideoSource
from ..services.protocols import DownloadService

__all__ = ["DownloadController", "DownloadEvent"]


class DownloadEvent:
    """A snapshot handed to the UI after each step."""

    __slots__ = ("item", "state")

    def __init__(self, item: DownloadItem, state: TaskState) -> None:
        self.item = item
        self.state = state


class DownloadController:
    """Drives a :class:`DownloadService` and reports state changes.

    The controller is touched from two threads: the GUI thread issues
    pause / resume / stop / retry, while a worker thread calls
    :meth:`step`. A re-entrant lock keeps those two sides from interleaving
    inside the service.
    """

    def __init__(self, service: DownloadService) -> None:
        self._service = service
        self._states: dict[str, TaskState] = {}
        self._listeners: list[Callable[[DownloadEvent], None]] = []
        self._lock = threading.RLock()

    def add_listener(self, callback: Callable[[DownloadEvent], None]) -> None:
        self._listeners.append(callback)

    def _emit(self, item: DownloadItem) -> None:
        previous = self._states.get(item.item_id)
        if previous is item.state:
            return
        self._states[item.item_id] = item.state
        for callback in list(self._listeners):
            callback(DownloadEvent(item=item, state=item.state))

    # -- commands ---------------------------------------------------------- #
    def enqueue(self, source: VideoSource, quality: str = "1080p") -> str:
        with self._lock:
            task_id = self._service.start(source, quality)
            self._states[task_id] = TaskState.QUEUED
            return task_id

    def pause(self, task_id: str) -> None:
        with self._lock:
            self._service.pause(task_id)
            self._refresh(task_id)

    def resume(self, task_id: str) -> None:
        with self._lock:
            self._service.resume(task_id)
            self._refresh(task_id)

    def stop(self, task_id: str) -> None:
        with self._lock:
            self._service.stop(task_id)
            self._refresh(task_id)

    def retry(self, task_id: str) -> None:
        with self._lock:
            self._service.retry(task_id)
            self._refresh(task_id)

    # -- stepping ---------------------------------------------------------- #
    def step(self, task_id: str) -> Optional[DownloadItem]:
        """Advance one chunk of a running download."""
        with self._lock:
            item = self._service.step(task_id)
            self._emit(item)
            return item

    def is_running(self, task_id: str) -> bool:
        with self._lock:
            item = self._service.get(task_id)
            return bool(item) and item.state is TaskState.RUNNING

    # -- inspection -------------------------------------------------------- #
    def items(self) -> list[DownloadItem]:
        with self._lock:
            return list(self._service.tasks)

    def get(self, task_id: str) -> Optional[DownloadItem]:
        with self._lock:
            return self._service.get(task_id)

    def _refresh(self, task_id: str) -> None:
        item = self._service.get(task_id)
        if item is not None:
            self._emit(item)

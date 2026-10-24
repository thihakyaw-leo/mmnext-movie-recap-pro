"""Deterministic demo service implementations.

The download service is *stepped* rather than self-driving: the caller asks
for one chunk at a time. That keeps the service pure and testable and lets
the application layer decide where the loop lives (on a worker thread, never
on the GUI thread).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...domain.enums import SourceType, TaskState
from ...domain.models import DownloadItem, SourceMetadata, VideoSource
from . import demo_data

__all__ = [
    "DemoMetadataService",
    "DemoDownloadService",
    "DEMO_TOTAL_BYTES",
    "CHUNK_PATTERN",
]

#: Total simulated download size: 508.7 MB.
DEMO_TOTAL_BYTES = demo_data.DEMO_TOTAL_BYTES

#: Deterministic per-step percentages, cycled forever. Sums to 100 after 8 steps.
CHUNK_PATTERN = demo_data.CHUNK_PATTERN


class DemoMetadataService:
    """Returns the fixed demo metadata record.

    It deliberately ignores the URL contents so the analyze screen behaves
    identically for any input the user types.
    """

    def __init__(self) -> None:
        self._cache: dict[str, SourceMetadata] = {}

    def analyze(self, source: VideoSource) -> SourceMetadata:
        key = source.location
        if key not in self._cache:
            self._cache[key] = demo_data.demo_metadata()
        return self._cache[key]


@dataclass
class _Task:
    item: DownloadItem
    step_index: int = 0
    partial_path: str = ""


class DemoDownloadService:
    """A simulated downloader with pause / resume / stop / retry.

    The byte schedule is a fixed pattern, so the same sequence of
    :meth:`step` calls always produces the same numbers.
    """

    def __init__(self, output_dir: str = "") -> None:
        self._tasks: dict[str, _Task] = {}
        self._counter = 0
        self._output_dir = output_dir or demo_data.DEMO_OUTPUT_FOLDER

    # -- lifecycle --------------------------------------------------------- #
    def start(self, source: VideoSource, quality: str = "1080p") -> str:
        self._counter += 1
        task_id = f"dl_{self._counter:03d}"
        item = DownloadItem(
            item_id=task_id,
            title=source.display_name or source.location,
            url=source.location,
            total_bytes=DEMO_TOTAL_BYTES,
            state=TaskState.QUEUED,
            quality_label=quality,
            output_path=(
                f"{self._output_dir}\\{source.name}.{quality}.mp4"
            ),
        )
        self._tasks[task_id] = _Task(item=item)
        return task_id

    def pause(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.item.state in (TaskState.QUEUED, TaskState.RUNNING):
            task.item.state = TaskState.PAUSED

    def resume(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.item.state.can_resume:
            task.item.state = TaskState.RUNNING

    def stop(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task and task.item.state not in (
            TaskState.COMPLETE,
            TaskState.FAILED,
            TaskState.CANCELLED,
        ):
            task.item.state = TaskState.STOPPED
            task.partial_path = self._partial_path(task)

    def retry(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.item.state in (TaskState.FAILED, TaskState.STOPPED, TaskState.CANCELLED):
            task.item.downloaded_bytes = 0
            task.item.speed_bps = 0.0
            task.item.error_message = ""
            task.step_index = 0
            task.item.state = TaskState.QUEUED

    def fail(self, task_id: str, message: str = "Simulated network error") -> None:
        """Force a failure - used to demonstrate the retry path."""
        task = self._tasks.get(task_id)
        if task:
            task.item.state = TaskState.FAILED
            task.item.error_message = message

    # -- stepping ---------------------------------------------------------- #
    def step(self, task_id: str) -> DownloadItem:
        """Advance one chunk. Returns the current item snapshot."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(task_id)

        item = task.item
        if item.state is TaskState.PAUSED or item.state is TaskState.STOPPED:
            return item

        if item.state is TaskState.QUEUED:
            item.state = TaskState.RUNNING

        if item.state is not TaskState.RUNNING:
            return item

        chunk_pct = CHUNK_PATTERN[task.step_index % len(CHUNK_PATTERN)]
        chunk = int(item.total_bytes * chunk_pct / 100)
        item.downloaded_bytes = min(item.total_bytes, item.downloaded_bytes + chunk)
        task.step_index += 1

        # Deterministic "network speed" - no randomness anywhere.
        item.speed_bps = 2_400_000 + (task.step_index % 5) * 180_000

        if item.downloaded_bytes >= item.total_bytes:
            item.downloaded_bytes = item.total_bytes
            item.state = TaskState.COMPLETE
            item.speed_bps = 0.0
        return item

    # -- inspection -------------------------------------------------------- #
    def get(self, task_id: str) -> Optional[DownloadItem]:
        task = self._tasks.get(task_id)
        return task.item if task else None

    @property
    def tasks(self) -> list[DownloadItem]:
        return [t.item for t in self._tasks.values()]

    def _partial_path(self, task: _Task) -> str:
        return f"{task.item.output_path}.partial"


def make_demo_download_service() -> DemoDownloadService:
    """Factory used by the bootstrap."""
    return DemoDownloadService()


def is_youtube(url: str) -> bool:
    """Very small URL sniff - enough for the import screen validation."""
    lowered = (url or "").strip().lower()
    return (
        SourceType.YOUTUBE.value in lowered
        or "youtu.be" in lowered
        or lowered.startswith("http")
        and ("watch" in lowered or "shorts" in lowered)
    )

"""Download queue tests.

These cover the download contract:

* enqueue creates a queued task with the selected quality;
* the simulated progress is deterministic (the same chunk pattern every
  time) so the UI can be tested without a network;
* pause / resume / stop / retry move the task through the right states;
* the progress card derives every button from the task state.
"""

from __future__ import annotations

import pytest

from mmnext.application.download_controller import DownloadController
from mmnext.domain.enums import TaskState
from mmnext.domain.models import VideoSource
from mmnext.services.demo import demo_data
from mmnext.services.demo.demo_providers import DemoDownloadService
from mmnext.ui.widgets.progress_card import DownloadProgressCard


@pytest.fixture()
def controller() -> DownloadController:
    return DownloadController(DemoDownloadService())


@pytest.fixture()
def source() -> VideoSource:
    return VideoSource.youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


# --------------------------------------------------------------------- #
# Service level
# --------------------------------------------------------------------- #
def test_enqueue_creates_a_queued_task(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source, "1080p")
    item = controller.get(task_id)
    assert item is not None
    assert item.state is TaskState.QUEUED
    assert item.quality_label == "1080p"
    assert item.total_bytes == demo_data.DEMO_TOTAL_BYTES


def test_stepping_moves_queued_to_running(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source)
    item = controller.step(task_id)
    assert item is not None
    assert item.state is TaskState.RUNNING
    assert item.downloaded_bytes > 0


def test_progress_is_deterministic(controller: DownloadController, source) -> None:
    """Two identical runs must produce identical byte counts."""
    first = controller.enqueue(source)
    second = controller.enqueue(source)
    for _ in range(4):
        a = controller.step(first)
        b = controller.step(second)
        assert a.downloaded_bytes == b.downloaded_bytes
        assert a.percent == b.percent


def test_chunk_pattern_is_a_fixed_cycle() -> None:
    """The chunk pattern is a deterministic cycle, not a random walk."""
    pattern = demo_data.CHUNK_PATTERN
    assert len(pattern) == 8
    assert all(0 < chunk < 100 for chunk in pattern)
    assert sum(pattern) == 36


def test_download_completes_after_a_fixed_number_of_chunks(
    controller: DownloadController, source
) -> None:
    """The simulated download must always reach 100% in a fixed step count."""
    task_id = controller.enqueue(source)
    item = None
    steps = 0
    while steps < 200:
        item = controller.step(task_id)
        steps += 1
        if item.state is TaskState.COMPLETE:
            break
    assert item is not None
    assert item.state is TaskState.COMPLETE
    assert item.percent == pytest.approx(100.0)
    assert steps == 23


def test_pause_stops_progress(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source)
    controller.step(task_id)
    controller.pause(task_id)
    before = controller.get(task_id).downloaded_bytes
    after = controller.step(task_id)
    assert after.downloaded_bytes == before
    assert after.state is TaskState.PAUSED


def test_resume_continues_from_the_same_point(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source)
    controller.step(task_id)
    controller.pause(task_id)
    before = controller.get(task_id).downloaded_bytes
    controller.resume(task_id)
    assert controller.get(task_id).state is TaskState.RUNNING
    after = controller.step(task_id)
    assert after.downloaded_bytes > before


def test_stop_freezes_the_task(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source)
    controller.step(task_id)
    controller.stop(task_id)
    assert controller.get(task_id).state is TaskState.STOPPED


def test_retry_resets_the_task(controller: DownloadController, source) -> None:
    task_id = controller.enqueue(source)
    controller.step(task_id)
    controller.stop(task_id)
    controller.retry(task_id)
    item = controller.get(task_id)
    assert item.state is TaskState.QUEUED
    assert item.downloaded_bytes == 0
    assert item.error_message == ""


def test_failure_can_be_simulated_and_retried(controller: DownloadController, source) -> None:
    service = controller._service  # the demo service is deterministic
    task_id = controller.enqueue(source)
    service.fail(task_id, "Simulated network error")
    controller._refresh(task_id)
    item = controller.get(task_id)
    assert item.state is TaskState.FAILED
    assert item.error_message == "Simulated network error"
    controller.retry(task_id)
    assert controller.get(task_id).state is TaskState.QUEUED


def test_state_changes_are_reported_once(controller: DownloadController, source) -> None:
    seen: list[tuple[str, TaskState]] = []
    controller.add_listener(lambda event: seen.append((event.item.item_id, event.state)))
    task_id = controller.enqueue(source)
    controller.step(task_id)
    controller.step(task_id)
    # Only the queued -> running change is a state change.
    assert seen == [(task_id, TaskState.RUNNING)]


# --------------------------------------------------------------------- #
# UI level: button availability per state
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "state, pause, resume, stop, retry, open_",
    [
        (TaskState.QUEUED, True, False, True, False, False),
        (TaskState.RUNNING, True, False, True, False, False),
        (TaskState.PAUSED, False, True, True, False, False),
        (TaskState.STOPPED, False, True, False, True, False),
        (TaskState.FAILED, False, False, False, True, False),
        (TaskState.COMPLETE, False, False, False, False, True),
        (TaskState.CANCELLED, False, False, False, True, False),
    ],
)
def test_button_availability_per_state(
    qapp, state, pause, resume, stop, retry, open_
) -> None:
    """Every button must be derived from the task state."""
    card = DownloadProgressCard()
    item = demo_data.demo_download_item()
    item.state = state
    card.apply(item)

    assert card.pause_button.isEnabled() is pause
    assert card.resume_button.isEnabled() is resume
    assert card.stop_button.isEnabled() is stop
    assert card.retry_button.isEnabled() is retry
    assert card.open_button.isEnabled() is open_


def test_card_shows_progress_metrics(qapp) -> None:
    card = DownloadProgressCard()
    item = demo_data.demo_download_item()
    card.apply(item)
    assert card.percent_label.text().endswith("%")
    assert "MB" in card.size_label.text()
    assert card.title_label.text() == item.title

"""Splitter worker-thread and UI wiring tests.

The splitter cuts real video, so everything heavy must run on a worker thread
while the context and the panel follow the run through their own signals.
"""

from __future__ import annotations

import shutil

import pytest
from PySide6.QtTest import QTest

from mmnext.services.adapters.splitter import (
    DemoSplitterPlanner,
    LegacySplitterRenderer,
)

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg/FFprobe are required for the splitter render",
)


def _wait_for(predicate, timeout_ms: int = 60000) -> bool:
    """Wait for a state the worker thread reaches.

    The poll interval is deliberately coarse.  A tight spin over the GUI event
    loop starves the worker thread of the GIL - on Windows each FFmpeg call
    spawns reader threads that all need it - and a coarse poll still delivers
    the queued signals.
    """
    waited = 0
    step = 200
    while waited < timeout_ms:
        if predicate():
            return True
        QTest.qWait(step)
        waited += step
    return False


@pytest.fixture()
def splitter_context(qapp, tmp_path):
    """A real AppContext with a REAL (non-demo) session ready to split."""
    from mmnext.domain.enums import AppMode
    from mmnext.domain.models import ProjectSession, TranscriptRow, VideoSource
    from mmnext.ui.app_context import AppContext

    context = AppContext(jobs_dir=str(tmp_path / "jobs"))
    parts = DemoSplitterPlanner().plan(4.0, 2.0)
    # The session has to exist before the working set can be populated.
    context.project.load(
        ProjectSession(
            source=VideoSource.local(str(tmp_path / "source.mp4")),
            output_folder=str(tmp_path),
            mode=AppMode.SPLITTER,
            is_demo=False,
        )
    )
    context.project.apply_transcript(
        [
            TranscriptRow("s0", 0.0, 2.0, "one"),
            TranscriptRow("s1", 2.0, 2.0, "two"),
        ]
    )
    context.project.set_split_parts(parts)
    yield context, tmp_path, parts
    context.jobs.clear()


def test_the_splitter_render_runs_off_the_gui_thread(splitter_context) -> None:
    """The heavy stages must never execute on the GUI thread."""
    import threading

    context, tmp_path, parts = splitter_context
    from tests.test_splitter_render import make_video

    video = make_video(tmp_path / "source.mp4", seconds=4.0)
    seen: list[int] = []

    # A non-demo session uses the REAL renderer, so that is the class to watch.
    original = LegacySplitterRenderer.render_part

    def _spy(self, video_path, part, output_path, settings):
        seen.append(threading.get_ident())
        return original(self, video_path, part, output_path, settings)

    LegacySplitterRenderer.render_part = _spy
    try:
        context.start_splitter_render(
            video_path=str(video), output_dir=str(tmp_path / "out")
        )
        assert _wait_for(lambda: context.splitter_state in {"done", "failed", "stopped"})
    finally:
        LegacySplitterRenderer.render_part = original

    assert seen, "the renderer was never called"
    assert all(ident != threading.get_ident() for ident in seen)
    assert context.splitter_state == "done", context.splitter_message


def test_a_second_splitter_run_is_refused(splitter_context) -> None:
    context, tmp_path, _ = splitter_context
    original = LegacySplitterRenderer.render_part

    def _slow(self, video_path, part, output_path, settings):
        QTest.qWait(150)
        return original(self, video_path, part, output_path, settings)

    LegacySplitterRenderer.render_part = _slow
    try:
        context.start_splitter_render(
            video_path=str(tmp_path / "source.mp4"),
            output_dir=str(tmp_path / "out"),
        )
        with pytest.raises(RuntimeError, match="already in progress"):
            context.start_splitter_render()
        assert _wait_for(lambda: context.splitter_state in {"done", "failed", "stopped"})
    finally:
        LegacySplitterRenderer.render_part = original


def test_the_stop_button_reports_a_stopping_state(splitter_context) -> None:
    context, tmp_path, _ = splitter_context
    original = LegacySplitterRenderer.render_part

    def _slow(self, video_path, part, output_path, settings):
        QTest.qWait(300)
        return original(self, video_path, part, output_path, settings)

    LegacySplitterRenderer.render_part = _slow
    try:
        context.start_splitter_render(
            video_path=str(tmp_path / "source.mp4"),
            output_dir=str(tmp_path / "out"),
        )
        assert _wait_for(lambda: context.splitter_running)
        context.stop_splitter_render()
        assert context.splitter_state == "stopping"
        assert _wait_for(
            lambda: context.splitter_state in {"stopped", "done", "failed"}
        )
    finally:
        LegacySplitterRenderer.render_part = original


def test_the_splitter_starts_idle_and_refuses_without_parts(tmp_path) -> None:
    from mmnext.domain.enums import AppMode
    from mmnext.domain.models import ProjectSession, VideoSource
    from mmnext.ui.app_context import AppContext

    context = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        assert context.splitter_running is False
        assert context.splitter_state == "idle"
        context.project.load(
            ProjectSession(
                source=VideoSource.local(str(tmp_path / "source.mp4")),
                output_folder=str(tmp_path),
                mode=AppMode.SPLITTER,
                is_demo=False,
            )
        )
        with pytest.raises(ValueError, match="No selected parts"):
            context.start_splitter_render()
        with pytest.raises(ValueError, match="No project session"):
            AppContext(jobs_dir=str(tmp_path / "jobs2")).start_splitter_render()
    finally:
        context.jobs.clear()


def test_planning_populates_the_parts(splitter_context) -> None:
    """Planning covers the source duration and hands the parts to the UI."""
    from mmnext.services.demo import demo_data

    context, tmp_path, _ = splitter_context
    demo = demo_data.build_demo_session()
    # A session whose duration comes from metadata, so planning has to ask the
    # session for it rather than inventing one.
    context.project.load(
        __import__("mmnext.domain.models", fromlist=["ProjectSession"]).ProjectSession(
            source=demo.source,
            metadata=demo.metadata,
            output_folder=str(tmp_path),
            is_demo=False,
        )
    )
    parts = context.plan_splitter(part_seconds=60.0)
    assert parts, "planning produced no parts"
    assert [p.number for p in parts] == list(range(1, len(parts) + 1))
    assert parts[0].start == pytest.approx(0.0)
    assert parts[-1].end == pytest.approx(demo.total_duration())
    # The same parts reach the working set the panel renders.
    assert [p.number for p in context.project.session.split_parts] == [p.number for p in parts]


@needs_ffmpeg
def test_a_real_splitter_run_reaches_a_terminal_state(splitter_context) -> None:
    """The real FFmpeg path through the worker thread finishes and reports."""
    context, tmp_path, _ = splitter_context
    from tests.test_splitter_render import make_video

    video = make_video(tmp_path / "source.mp4", seconds=4.0)

    context.start_splitter_render(
        video_path=str(video), output_dir=str(tmp_path / "out")
    )
    assert _wait_for(lambda: context.splitter_state in {"done", "failed"})
    assert context.splitter_state == "done", context.splitter_message
    assert (tmp_path / "out" / "part_1.mp4").is_file()
    assert (tmp_path / "out" / "part_2.mp4").is_file()

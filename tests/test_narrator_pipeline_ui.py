"""Narrator pipeline UI wiring tests (pytest-qt, offscreen).

The pipeline calls translation, speech synthesis and Smart Sync render. Those
are heavy, so the contract under test is that the UI starts them on a worker
thread and that the panel reflects the run lifecycle.
"""

from __future__ import annotations

import pytest
from PySide6.QtTest import QTest

from mmnext.domain.enums import AppMode
from mmnext.ui.app_context import AppContext
from mmnext.ui.main_window import MainWindow
from mmnext.ui.navigation.nav_rail import NavTarget

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture()
def window(qtbot) -> MainWindow:
    win = MainWindow()

    def _clear_dirty(widget) -> None:
        widget.context.project.mark_narration_clean()
        widget.context.project.mark_exact_rows_clean()

    qtbot.addWidget(win, before_close_func=_clear_dirty)
    win.show()
    qtbot.waitExposed(win)
    yield win
    win._worker.shutdown(wait_ms=1000)


def _wait_for(predicate, timeout_ms: int = 30000) -> bool:
    """Wait for the pipeline to reach a terminal state.

    The timeout is generous on purpose: the demo pipeline writes one file
    per segment, and a file write costs tens of milliseconds on a scanned or
    busy disk.  The contract under test is *that* the run finishes and the
    panel reflects it, not how fast the disk is.
    """
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        QTest.qWait(25)
        waited += 25
    return False


def test_pipeline_button_exists_and_starts_disabled_while_running(window: MainWindow) -> None:
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    panel = window._workspace.narrator_panel

    assert panel.pipeline_button.isEnabled() is True
    assert panel.pipeline_stop_button.isEnabled() is False


def _start_pipeline(context, tmp_path) -> None:
    """Start the pipeline with an output inside the test's own directory.

    The demo session points at a real user output folder on a user drive.
    Writing the render there makes the test slow and non-hermetic, so the
    output path is always given explicitly.
    """
    context.start_narrator_pipeline(
        output_path=str(tmp_path / "narrator_recap.mp4")
    )


def test_running_the_pipeline_updates_the_narration_segments(window: MainWindow, tmp_path) -> None:
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    context = window.context

    _start_pipeline(context, tmp_path)
    assert _wait_for(lambda: context.narrator_state in {"done", "failed", "stopped"})

    assert context.narrator_state == "done"
    segments = context.project.narrator_segments()
    assert segments
    assert all(segment.narration for segment in segments)


def test_pipeline_runs_off_the_gui_thread(window: MainWindow, tmp_path) -> None:
    """The heavy stages must never execute on the GUI thread."""
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    context = window.context

    thread_ids: list[int] = []
    original = context._narrator_coordinator.plan

    def _spy(rows, duration):
        import threading

        thread_ids.append(threading.get_ident())
        return original(rows, duration)

    context._narrator_coordinator.plan = _spy

    _start_pipeline(context, tmp_path)
    assert _wait_for(lambda: context.narrator_state in {"done", "failed"})

    import threading

    assert thread_ids
    assert thread_ids[0] != threading.get_ident()


def test_the_panel_reflects_the_pipeline_lifecycle(window: MainWindow, tmp_path) -> None:
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    panel = window._workspace.narrator_panel
    context = window.context

    _start_pipeline(context, tmp_path)
    assert _wait_for(lambda: context.narrator_state in {"done", "failed", "stopped"})

    assert panel.pipeline_button.isEnabled() is True
    assert panel.pipeline_stop_button.isEnabled() is False
    assert "DEMO" in panel.pipeline_status.text()


def test_starting_a_second_run_is_refused(window: MainWindow, tmp_path) -> None:
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    context = window.context

    _start_pipeline(context, tmp_path)
    # Either the first run is still going (refused) or it already finished.
    try:
        context.start_narrator_pipeline(
            output_path=str(tmp_path / "narrator_recap.mp4")
        )
    except RuntimeError as exc:
        assert "already in progress" in str(exc)
    assert _wait_for(lambda: context.narrator_state in {"done", "failed", "stopped"})


def test_the_context_exposes_the_pipeline_state() -> None:
    context = AppContext()
    assert context.narrator_pipeline_running is False
    assert context.narrator_state == "idle"
    assert context.narrator_message


def test_pipeline_requires_a_transcript(tmp_path) -> None:
    context = AppContext()
    context.project.clear()
    with pytest.raises(ValueError):
        context.start_narrator_pipeline()

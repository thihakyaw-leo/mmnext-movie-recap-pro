"""UI shell tests (pytest-qt, offscreen).

These exercise the milestone-1 acceptance criteria at the widget level:

* the shell builds and shows the seven screens;
* navigation works from the rail, the public API and the keyboard shortcuts;
* switching modes keeps narrator and exact dubbing apart;
* the selection is shared between the table, the timeline and the inspector;
* unsaved edits are tracked and can be saved;
* the download card advances without blocking the GUI thread;
* Myanmar text survives the round trip.
"""

from __future__ import annotations

import pytest

from mmnext.domain.enums import AppMode
from mmnext.ui.app_context import AppContext
from mmnext.ui.main_window import MainWindow
from mmnext.ui.navigation.nav_rail import NavTarget

pytestmark = pytest.mark.usefixtures("qapp")

MYANMAR_TEXT = "မြန်မာစာ ပြောင်းလဲမှု စမ်းသပ်ခြင်း"


@pytest.fixture()
def window(qtbot) -> MainWindow:
    win = MainWindow()

    def _clear_dirty(widget) -> None:
        """Close must never block on the modal confirmation.

        pytest-qt closes tracked widgets during teardown, and closing with
        unsaved edits opens the confirmation dialog. A test must never
        block on a modal, so the edits are cleared just before the close.
        """
        widget.context.project.mark_narration_clean()
        widget.context.project.mark_exact_rows_clean()

    qtbot.addWidget(win, before_close_func=_clear_dirty)
    # The window must be shown for key events to reach the shortcuts.
    win.show()
    qtbot.waitExposed(win)
    yield win
    win._worker.shutdown(wait_ms=1000)


@pytest.fixture()
def workspace(window: MainWindow):
    window.navigate_to(NavTarget.WORKSPACE)
    # The narration table is the one the selection assertions refer to.
    window.context.set_mode(AppMode.NARRATOR)
    return window._workspace


# --------------------------------------------------------------------- #
# Shell
# --------------------------------------------------------------------- #
def test_window_builds(window: MainWindow) -> None:
    assert window.windowTitle().startswith("MMNext Movie Recap Pro")
    assert window.stack.count() == 7


def test_all_screens_are_registered(window: MainWindow) -> None:
    assert set(window._screens) == {
        NavTarget.HOME,
        NavTarget.IMPORT,
        NavTarget.ANALYZE,
        NavTarget.DOWNLOADS,
        NavTarget.JOBS,
        NavTarget.WORKSPACE,
        NavTarget.SETTINGS,
    }


def test_top_bar_shows_the_demo_state(window: MainWindow) -> None:
    assert window.demo_badge.text() == "DEMO"
    assert "demo" in window.project_label.text().lower()
    assert window.save_chip.value() == "yes"


def test_unknown_navigation_target_falls_back_to_home(window: MainWindow) -> None:
    window.navigate_to("does-not-exist")
    assert window.nav.active_key == NavTarget.HOME


# --------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "target",
    [
        NavTarget.HOME,
        NavTarget.IMPORT,
        NavTarget.ANALYZE,
        NavTarget.DOWNLOADS,
        NavTarget.JOBS,
        NavTarget.WORKSPACE,
        NavTarget.SETTINGS,
    ],
)
def test_every_screen_can_be_opened(window: MainWindow, target: str) -> None:
    window.navigate_to(target)
    assert window.nav.active_key == target
    assert window.stack.currentWidget() is window._screens[target]


def test_navigation_from_the_rail(window: MainWindow) -> None:
    window.nav.navigate.emit(NavTarget.JOBS)
    assert window.nav.active_key == NavTarget.JOBS


def test_keyboard_shortcut_navigates(qtbot, window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    window.activateWindow()
    window.raise_()
    QTest.keyClick(window, Qt.Key_4, Qt.ControlModifier)
    assert window.nav.active_key == NavTarget.DOWNLOADS


def test_drawer_shortcut_toggles(qtbot, window: MainWindow) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    before = window.log_drawer.expanded
    window.activateWindow()
    QTest.keyClick(window, Qt.Key_J, Qt.ControlModifier)
    assert window.log_drawer.expanded is not before


# --------------------------------------------------------------------- #
# Mode switching
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", list(AppMode))
def test_every_mode_can_be_selected(window: MainWindow, mode: AppMode) -> None:
    window.context.set_mode(mode)
    assert window.context.mode is mode
    assert window._workspace._mode is mode


def test_mode_switcher_widget_matches_the_context(window: MainWindow) -> None:
    window.context.set_mode(AppMode.EXACT_DUBBING)
    assert window._workspace.mode_switcher.current_mode is AppMode.EXACT_DUBBING


def test_narrator_and_exact_dubbing_show_different_tables(
    window: MainWindow,
) -> None:
    window.context.set_mode(AppMode.NARRATOR)
    narrator_view = window._workspace.table.current_table()
    window.context.set_mode(AppMode.EXACT_DUBBING)
    exact_view = window._workspace.table.current_table()
    assert narrator_view is not exact_view
    assert narrator_view.model().rowCount() == 24
    assert exact_view.model().rowCount() == 24


def test_exact_dubbing_inspector_hides_the_narrator_editor(
    window: MainWindow,
) -> None:
    window.context.set_mode(AppMode.EXACT_DUBBING)
    inspector = window._workspace.inspector
    assert inspector.narrator_section.isVisibleTo(inspector) is False
    assert inspector.exact_section.isVisibleTo(inspector) is True


# --------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------- #
def test_selecting_a_row_updates_the_inspector(workspace) -> None:
    workspace.table.select_row(0)
    assert workspace.context.selection.row_id == "narr_001"
    assert workspace.inspector.narrator_source.text() != "-"


def test_selection_is_shared_with_the_context(workspace) -> None:
    workspace.context.selection.select("narr_005", "narration")
    assert workspace.table.selected_row_id() == "narr_005"


def test_selection_survives_a_data_refresh(workspace) -> None:
    """Re-binding the same rows must not lose the current selection."""
    workspace.table.select_row(3)
    selected = workspace.context.selection.row_id
    workspace._reload()
    assert workspace.context.selection.row_id == selected


def test_timeline_seek_moves_the_preview(workspace) -> None:
    workspace.timeline.seekRequested.emit(42.0)
    assert workspace.preview.position() == pytest.approx(42.0)


# --------------------------------------------------------------------- #
# Editing
# --------------------------------------------------------------------- #
def test_narration_edit_marks_the_project_dirty(window: MainWindow) -> None:
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)
    assert window.context.dirty.count(AppMode.NARRATOR) == 1


def test_save_clears_the_unsaved_indicator(window: MainWindow) -> None:
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)
    window._save_working_set()
    assert window.context.dirty.count(AppMode.NARRATOR) == 0
    assert window.save_chip.value() == "yes"


def test_myanmar_text_survives_the_round_trip(window: MainWindow) -> None:
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)
    assert segment.narration == MYANMAR_TEXT
    assert "မြန်မာ" in segment.narration


def test_exact_dubbing_edit_only_touches_the_translation(
    window: MainWindow,
) -> None:
    window.context.set_mode(AppMode.EXACT_DUBBING)
    row = window.context.project.exact_rows()[0]
    before = (row.row_id, row.original, row.start, row.duration)
    window.context.project.update_exact_row(row.row_id, burmese=MYANMAR_TEXT)
    after = (row.row_id, row.original, row.start, row.duration)
    assert before == after
    assert row.burmese == MYANMAR_TEXT


def test_exact_dubbing_gender_maps_to_a_voice(window: MainWindow) -> None:
    window.context.set_mode(AppMode.EXACT_DUBBING)
    row = window.context.project.exact_rows()[0]
    window.context.project.update_exact_row(row.row_id, gender="male")
    assert row.gender.value == "male"
    assert row.voice == "my-MM-ThihaNeural"


# --------------------------------------------------------------------- #
# Download queue
# --------------------------------------------------------------------- #
def test_download_progress_runs_on_a_worker_thread(window: MainWindow) -> None:
    """The download must advance without the GUI thread doing the work."""
    from mmnext.domain.models import VideoSource

    source = VideoSource.youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    task_id = window.context.enqueue_download(source, "1080p")
    assert task_id

    from PySide6.QtTest import QTest

    deadline = 40
    while deadline > 0:
        QTest.qWait(50)
        deadline -= 1
        item = window.context.downloads.get(task_id)
        if item is not None and item.downloaded_bytes > 0:
            break
    item = window.context.downloads.get(task_id)
    assert item is not None
    assert item.downloaded_bytes > 0
    assert item.state.value in {"running", "complete"}


def test_global_stop_button_is_disabled_when_idle(window: MainWindow) -> None:
    window._update_stop_state()
    assert window.stop_button.isEnabled() is False


def test_reset_demo_restores_the_pristine_project(
    monkeypatch, window: MainWindow
) -> None:
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)
    assert window.context.dirty.count(AppMode.NARRATOR) == 1

    _patch_message_box(monkeypatch, "Discard changes")
    window._reset_demo()
    assert window.context.dirty.count(AppMode.NARRATOR) == 0
    assert window.context.project.narrator_segments()[0].narration != MYANMAR_TEXT


# --------------------------------------------------------------------- #
# Unsaved-edit confirmation
# --------------------------------------------------------------------- #
def _patch_message_box(monkeypatch, label: str) -> None:
    """Make the confirmation dialog answer with ``label``.

    The dialog is modal, so the test has to pick the answer from inside
    ``exec`` instead of clicking a real button afterwards.
    """
    from PySide6.QtWidgets import QMessageBox, QPushButton

    def _exec(self):
        for button in self.buttons():
            if isinstance(button, QPushButton) and button.text() == label:
                button.click()
                break
        return 0

    monkeypatch.setattr(QMessageBox, "exec", _exec)


def test_unsaved_edits_prompt_before_a_destructive_reset(
    monkeypatch, window: MainWindow
) -> None:
    """Cancelling the prompt must leave the project untouched."""
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)

    _patch_message_box(monkeypatch, "Cancel")
    window._reset_demo()

    assert window.context.dirty.count(AppMode.NARRATOR) == 1
    assert window.context.project.narrator_segments()[0].narration == MYANMAR_TEXT


def test_reset_confirms_and_then_discards(monkeypatch, window: MainWindow) -> None:
    """Discarding has to be an explicit choice, and it works when confirmed."""
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)

    _patch_message_box(monkeypatch, "Discard changes")
    window._reset_demo()

    assert window.context.dirty.count(AppMode.NARRATOR) == 0
    assert window.context.project.narrator_segments()[0].narration != MYANMAR_TEXT


def test_no_prompt_when_there_is_nothing_to_discard(
    monkeypatch, window: MainWindow
) -> None:
    """Confirmations are for destructive actions only."""
    from PySide6.QtWidgets import QMessageBox

    def _fail(self):
        raise AssertionError("the dialog must not open without unsaved edits")

    monkeypatch.setattr(QMessageBox, "exec", _fail)
    window._reset_demo()
    assert window.context.dirty.total_dirty() == 0


def test_the_prompt_counts_edits_in_every_working_set(
    monkeypatch, window: MainWindow
) -> None:
    """A reset wipes narrator *and* exact-dubbing edits, so both count."""
    seen: list[int] = []

    from mmnext.ui.widgets import confirm as confirm_module

    def _spy(parent, dirty_count, **kwargs):
        seen.append(dirty_count)
        return confirm_module.UnsavedChoice.CANCEL

    monkeypatch.setattr(confirm_module, "confirm_unsaved_changes", _spy)

    window.context.set_mode(AppMode.NARRATOR)
    narrator = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(narrator.segment_id, MYANMAR_TEXT)

    window.context.set_mode(AppMode.EXACT_DUBBING)
    row = window.context.project.exact_rows()[0]
    window.context.project.update_exact_row(row.row_id, burmese=MYANMAR_TEXT)

    window._reset_demo()
    assert seen == [2]


def test_closing_the_window_asks_before_discarding(
    monkeypatch, window: MainWindow
) -> None:
    """The window may not close while unsaved edits exist and the user cancels."""
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)

    _patch_message_box(monkeypatch, "Cancel")
    window.close()

    assert window.isVisible() is True
    assert window.context.dirty.count(AppMode.NARRATOR) == 1


def test_mode_switching_keeps_unsaved_edits(window: MainWindow) -> None:
    """Switching modes must not destroy anything.

    Narrator and exact dubbing are **separate working sets**, so switching
    discards nothing and therefore needs no confirmation at all.
    """
    window.context.set_mode(AppMode.NARRATOR)
    narrator = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(narrator.segment_id, MYANMAR_TEXT)

    window.context.set_mode(AppMode.EXACT_DUBBING)
    assert window.context.dirty.count(AppMode.NARRATOR) == 1
    assert window.context.project.narrator_segments()[0].narration == MYANMAR_TEXT

    window.context.set_mode(AppMode.NARRATOR)
    assert window.context.dirty.count(AppMode.NARRATOR) == 1
    assert window.context.dirty.count(AppMode.EXACT_DUBBING) == 0


def test_the_save_chip_follows_the_active_mode(window: MainWindow) -> None:
    """An exact-dubbing edit must not light up the narrator save chip."""
    window.context.set_mode(AppMode.NARRATOR)
    row = window.context.project.exact_rows()[0]
    window.context.project.update_exact_row(row.row_id, burmese=MYANMAR_TEXT)

    assert window.save_chip.value() == "yes"

    window.context.set_mode(AppMode.EXACT_DUBBING)
    assert "unsaved" in window.save_chip.value()


def test_saving_clears_the_count_for_the_active_mode(window: MainWindow) -> None:
    """The saved event has to refresh the cached count, not just the badge."""
    window.context.set_mode(AppMode.NARRATOR)
    segment = window.context.project.narrator_segments()[0]
    window.context.project.update_narration(segment.segment_id, MYANMAR_TEXT)
    assert window.context.dirty.count(AppMode.NARRATOR) == 1

    window.context.project.mark_narration_clean()
    assert window.context.dirty.count(AppMode.NARRATOR) == 0
    assert window.context.dirty.total_dirty() == 0


# --------------------------------------------------------------------- #
# Demo mode
# --------------------------------------------------------------------- #
def test_demo_mode_needs_no_api_key_or_network(
    monkeypatch, window: MainWindow
) -> None:
    """Nothing in the demo path may reach the network."""
    import socket

    def _blocked(*args, **kwargs):  # pragma: no cover - only runs on failure
        raise AssertionError("the demo mode must not open a socket")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    # The demo project is already loaded; re-running analyze must be offline.
    metadata = window.context.analyze()
    assert metadata.title


def test_context_uses_demo_services_only() -> None:
    from mmnext.services.demo.demo_providers import (
        DemoDownloadService,
        DemoMetadataService,
    )

    ctx = AppContext()
    assert isinstance(ctx.metadata_service, DemoMetadataService)
    assert isinstance(ctx.download_service, DemoDownloadService)

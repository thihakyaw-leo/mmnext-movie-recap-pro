"""Project controller and dirty-guard tests.

Covers the editing contract:

* narration edits and exact-dubbing edits mark their own rows dirty;
* the dirty count is per mode - switching mode does not lose edits;
* "save" clears the dirty flag for that mode only;
* validation runs the mode-specific contract;
* the mode switcher never leaks narrator data into exact dubbing.
"""

from __future__ import annotations

import pytest

from mmnext.application.project_controller import ProjectController
from mmnext.domain.enums import AppMode, Gender, Severity
from mmnext.services.demo import demo_data
from mmnext.services.demo.demo_providers import DemoMetadataService
from mmnext.ui.app_context import AppContext, DirtyGuard


@pytest.fixture()
def controller() -> ProjectController:
    controller = ProjectController(DemoMetadataService())
    controller.load(demo_data.build_demo_session())
    return controller


@pytest.fixture()
def context() -> AppContext:
    ctx = AppContext()
    ctx.load_demo_project()
    return ctx


# --------------------------------------------------------------------- #
# Session lifecycle
# --------------------------------------------------------------------- #
def test_load_reports_the_session(controller: ProjectController) -> None:
    assert controller.has_project
    assert controller.session is not None
    assert controller.session.is_demo is True


def test_load_notifies_listeners(controller: ProjectController) -> None:
    seen: list[str] = []
    controller.add_listener(seen.append)
    controller.load(demo_data.build_demo_session())
    assert "session_loaded" in seen


def test_clear_removes_the_session(controller: ProjectController) -> None:
    controller.clear()
    assert controller.has_project is False
    assert controller.session is None
    assert controller.dirty_count() == 0


# --------------------------------------------------------------------- #
# Mode
# --------------------------------------------------------------------- #
@pytest.mark.parametrize("mode", list(AppMode))
def test_every_mode_can_be_selected(controller: ProjectController, mode: AppMode) -> None:
    controller.set_mode(mode)
    assert controller.mode is mode


def test_setting_the_same_mode_is_a_noop(controller: ProjectController) -> None:
    seen: list[str] = []
    controller.add_listener(seen.append)
    controller.set_mode(AppMode.NARRATOR)
    controller.set_mode(AppMode.NARRATOR)
    assert seen.count("mode_changed") == 1


# --------------------------------------------------------------------- #
# Narration working set
# --------------------------------------------------------------------- #
def test_narration_edit_marks_one_segment_dirty(controller: ProjectController) -> None:
    controller.set_mode(AppMode.NARRATOR)
    segment = controller.narrator_segments()[0]
    before = controller.dirty_count(AppMode.NARRATOR)
    assert controller.update_narration(segment.segment_id, "အသစ်မှန်းစာသား")
    assert controller.dirty_count(AppMode.NARRATOR) == before + 1
    assert segment.dirty is True
    assert segment.narration == "အသစ်မှန်းစာသား"


def test_narration_edit_of_unknown_id_is_rejected(controller: ProjectController) -> None:
    controller.set_mode(AppMode.NARRATOR)
    assert controller.update_narration("nope_999", "x") is False


def test_saving_narration_clears_only_the_narration_dirty_flag(
    controller: ProjectController,
) -> None:
    controller.set_mode(AppMode.NARRATOR)
    segment = controller.narrator_segments()[0]
    controller.update_narration(segment.segment_id, "ပြင်ဆင်ချက်")

    # Dirty an exact-dubbing row too - the two must not interfere.
    row = controller.exact_rows()[0]
    controller.update_exact_row(row.row_id, burmese="မြန်မာဘာသာ")

    controller.mark_narration_clean()
    assert controller.dirty_count(AppMode.NARRATOR) == 0
    assert controller.dirty_count(AppMode.EXACT_DUBBING) == 1
    assert row.edited is True


# --------------------------------------------------------------------- #
# Exact dubbing working set
# --------------------------------------------------------------------- #
def test_exact_row_edit_marks_the_row_edited(controller: ProjectController) -> None:
    controller.set_mode(AppMode.EXACT_DUBBING)
    row = controller.exact_rows()[0]
    assert controller.update_exact_row(row.row_id, burmese="မြန်မာသာ")
    assert row.burmese == "မြန်မာသာ"
    assert row.edited is True
    assert controller.dirty_count(AppMode.EXACT_DUBBING) == 1


def test_exact_row_gender_can_be_edited(controller: ProjectController) -> None:
    controller.set_mode(AppMode.EXACT_DUBBING)
    row = controller.exact_rows()[0]
    assert controller.update_exact_row(row.row_id, gender=Gender.FEMALE.value)
    assert row.gender == Gender.FEMALE.value
    assert row.edited is True


def test_exact_row_edit_of_unknown_id_is_rejected(controller: ProjectController) -> None:
    assert controller.update_exact_row("nope_999", burmese="x") is False


def test_exact_rows_keep_their_identity_fields(controller: ProjectController) -> None:
    """Editing a translation must not touch id / original / start / duration."""
    controller.set_mode(AppMode.EXACT_DUBBING)
    row = controller.exact_rows()[0]
    before = (row.row_id, row.original, row.start, row.duration)
    controller.update_exact_row(row.row_id, burmese="ပြောင်းလဲမှု")
    after = (row.row_id, row.original, row.start, row.duration)
    assert before == after


def test_saving_exact_rows_clears_only_the_exact_dirty_flag(
    controller: ProjectController,
) -> None:
    controller.set_mode(AppMode.EXACT_DUBBING)
    row = controller.exact_rows()[0]
    controller.update_exact_row(row.row_id, burmese="မြန်မာသာ")

    segment = controller.narrator_segments()[0]
    controller.update_narration(segment.segment_id, "အသစ်")

    controller.mark_exact_rows_clean()
    assert controller.dirty_count(AppMode.EXACT_DUBBING) == 0
    assert controller.dirty_count(AppMode.NARRATOR) == 1


# --------------------------------------------------------------------- #
# Mode separation
# --------------------------------------------------------------------- #
def test_modes_keep_separate_working_sets(controller: ProjectController) -> None:
    """A narration edit must not show up as an exact-dubbing edit."""
    controller.set_mode(AppMode.NARRATOR)
    segment = controller.narrator_segments()[0]
    controller.update_narration(segment.segment_id, "အသစ်စာသား")
    assert controller.dirty_count(AppMode.EXACT_DUBBING) == 0
    assert controller.dirty_count(AppMode.NARRATOR) == 1

    controller.set_mode(AppMode.EXACT_DUBBING)
    assert controller.dirty_count(AppMode.EXACT_DUBBING) == 0
    assert controller.dirty_count(AppMode.NARRATOR) == 1


def test_common_editing_mode_has_no_dirty_count(controller: ProjectController) -> None:
    controller.set_mode(AppMode.COMMON_EDITING)
    assert controller.dirty_count() == 0
    assert controller.has_unsaved_changes() is False


# --------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------- #
def test_exact_dubbing_validation_reports_the_demo_broken_row(
    controller: ProjectController,
) -> None:
    controller.set_mode(AppMode.EXACT_DUBBING)
    report = controller.validate()
    codes = {issue.code for issue in report.issues}
    assert "missing_burmese" in codes
    assert any(issue.severity is Severity.ERROR for issue in report.issues)


def test_narration_validation_runs_the_narration_contract(
    controller: ProjectController,
) -> None:
    controller.set_mode(AppMode.NARRATOR)
    report = controller.validate()
    assert report.issues, "the demo narration contains a deliberate warning"
    assert all(
        issue.code in {"empty_narration", "narration_too_long", "missing_semantic_boundary"}
        for issue in report.issues
    )


def test_common_editing_mode_validates_nothing(controller: ProjectController) -> None:
    controller.set_mode(AppMode.COMMON_EDITING)
    assert controller.validate().issues == []


# --------------------------------------------------------------------- #
# Analyze / metadata
# --------------------------------------------------------------------- #
def test_analyze_attaches_metadata_and_notifies(controller: ProjectController) -> None:
    seen: list[str] = []
    controller.add_listener(seen.append)
    metadata = controller.analyze()
    assert metadata.title == demo_data.DEMO_TITLE
    assert controller.session.metadata is metadata
    assert "metadata_loaded" in seen


def test_analyze_is_deterministic(controller: ProjectController) -> None:
    first = controller.analyze()
    second = controller.analyze()
    assert first.title == second.title
    assert first.qualities == second.qualities


# --------------------------------------------------------------------- #
# Dirty guard
# --------------------------------------------------------------------- #
def test_dirty_guard_emits_on_edit(context: AppContext) -> None:
    seen: list[tuple[int, str]] = []
    context.dirty.dirtyChanged.connect(lambda count, mode: seen.append((count, mode)))
    context.set_mode(AppMode.NARRATOR)
    seen.clear()
    segment = context.project.narrator_segments()[0]
    context.project.update_narration(segment.segment_id, "အသစ်")
    assert seen
    assert seen[-1] == (1, AppMode.NARRATOR.value)


def test_dirty_guard_reports_unsaved_changes(context: AppContext) -> None:
    context.set_mode(AppMode.NARRATOR)
    assert context.dirty.has_unsaved(AppMode.NARRATOR) is False
    segment = context.project.narrator_segments()[0]
    context.project.update_narration(segment.segment_id, "အသစ်")
    assert context.dirty.has_unsaved(AppMode.NARRATOR) is True


def test_demo_sessions_do_not_share_mutable_rows() -> None:
    """Two demo sessions must not share the same row objects.

    Otherwise an edit in one session silently changes the other one - which
    is exactly what the "Reset demo" button has to undo.
    """
    first = demo_data.build_demo_session()
    second = demo_data.build_demo_session()
    assert first.narration_segments[0] is not second.narration_segments[0]
    assert first.exact_dubbing_rows[0] is not second.exact_dubbing_rows[0]

    first.narration_segments[0].narration = "ပြောင်းလဲမှု"
    first.exact_dubbing_rows[0].burmese = "ပြောင်းလဲမှု"
    assert second.narration_segments[0].narration != "ပြောင်းလဲမှု"
    assert second.exact_dubbing_rows[0].burmese != "ပြောင်းလဲမှု"


def test_demo_project_fixture_is_never_mutated() -> None:
    session = demo_data.build_demo_session()
    session.narration_segments[0].narration = "ပြောင်းလဲမှု"
    assert demo_data.DEMO_PROJECT.narration_segments[0].narration != "ပြောင်းလဲမှု"


def test_dirty_guard_tracks_each_mode_independently(context: AppContext) -> None:
    context.set_mode(AppMode.NARRATOR)
    segment = context.project.narrator_segments()[0]
    context.project.update_narration(segment.segment_id, "အသစ်")
    assert context.dirty.count(AppMode.NARRATOR) == 1
    assert context.dirty.count(AppMode.EXACT_DUBBING) == 0


def test_dirty_guard_survives_a_mode_switch(context: AppContext) -> None:
    context.set_mode(AppMode.NARRATOR)
    segment = context.project.narrator_segments()[0]
    context.project.update_narration(segment.segment_id, "အသစ်")
    context.set_mode(AppMode.EXACT_DUBBING)
    assert context.dirty.count(AppMode.NARRATOR) == 1
    context.set_mode(AppMode.NARRATOR)
    assert context.dirty.count(AppMode.NARRATOR) == 1

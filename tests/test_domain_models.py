"""Domain model and validation tests.

These cover the two contracts that matter most for MMNext:

* a narration segment and an exact-dubbing row are **different things**
  and must never be converted into one another;
* the exact-dubbing validator enforces the "one row per source line,
  nothing summarised, nothing reordered" rule.
"""

from __future__ import annotations

import pytest

from mmnext.domain.enums import AppMode, Gender, JobState, Severity, TaskState
from mmnext.domain.models import ExactDubbingRow, NarrationSegment
from mmnext.domain.validation import (
    is_burmese,
    validate_exact_dubbing,
    validate_narration,
    validate_source_duration,
)
from mmnext.services.demo import demo_data


# --------------------------------------------------------------------- #
# Mode separation
# --------------------------------------------------------------------- #
def test_narration_and_exact_rows_are_distinct_types() -> None:
    """The two working sets must not share a base class."""
    assert NarrationSegment is not ExactDubbingRow
    assert not issubclass(NarrationSegment, ExactDubbingRow)
    assert not issubclass(ExactDubbingRow, NarrationSegment)


def test_narration_segment_has_no_burmese_field() -> None:
    fields = set(NarrationSegment.__dataclass_fields__)
    assert "burmese" not in fields
    assert {"segment_id", "video_start", "video_end", "narration"} <= fields


def test_exact_row_keeps_original_dialogue() -> None:
    fields = set(ExactDubbingRow.__dataclass_fields__)
    assert {"row_id", "original", "burmese", "start", "duration"} <= fields


def test_exact_row_end_and_voice() -> None:
    row = ExactDubbingRow(
        row_id="r1",
        start=1.0,
        duration=2.5,
        original="Hello",
        burmese="မင်္ဂလာပါ",
        gender=Gender.MALE,
    )
    assert row.end == pytest.approx(3.5)
    assert row.voice


# --------------------------------------------------------------------- #
# Myanmar text
# --------------------------------------------------------------------- #
def test_is_burmese_detects_myanmar_codepoints() -> None:
    assert is_burmese("မင်္ဂလာပါ") is True
    assert is_burmese("Hello there") is False
    assert is_burmese("") is False


def test_demo_exact_rows_carry_myanmar() -> None:
    session = demo_data.build_demo_session()
    rows = session.exact_dubbing_rows
    assert rows
    broken_index = demo_data.BROKEN_EXACT_ROW_INDEX
    for index, row in enumerate(rows):
        if index == broken_index:
            continue
        assert is_burmese(row.burmese), f"{row.row_id} has no Myanmar text"


# --------------------------------------------------------------------- #
# Exact dubbing validation
# --------------------------------------------------------------------- #
def test_demo_exact_rows_have_one_broken_row() -> None:
    """The demo project ships with exactly one deliberately broken row."""
    session = demo_data.build_demo_session()
    report = validate_exact_dubbing(session.exact_dubbing_rows, session.transcript)
    assert report.errors, "the demo project must contain a validation error"
    broken = [r for r in session.exact_dubbing_rows if not is_burmese(r.burmese)]
    assert len(broken) == 1
    assert broken[0].row_id == session.exact_dubbing_rows[demo_data.BROKEN_EXACT_ROW_INDEX].row_id


def test_exact_validation_accepts_a_clean_project() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)
    for row in rows:
        if not is_burmese(row.burmese):
            row.burmese = "နောက်ဆုံးစာများ"
    report = validate_exact_dubbing(rows, session.transcript)
    assert report.ok, report.summary
    assert not report.errors


def test_exact_validation_catches_a_missing_row() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)[:-1]
    report = validate_exact_dubbing(rows, session.transcript)
    assert not report.ok
    assert any("row" in issue.message.lower() for issue in report.errors)


def test_exact_validation_catches_a_reordered_row() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)
    rows[0], rows[1] = rows[1], rows[0]
    report = validate_exact_dubbing(rows, session.transcript)
    assert not report.ok


def test_exact_validation_catches_english_in_the_burmese_column() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)
    rows[2].burmese = "this is english, not Burmese"
    report = validate_exact_dubbing(rows, session.transcript)
    assert not report.ok
    assert any(issue.code == "non_burmese" for issue in report.errors)


def test_exact_validation_catches_an_immutable_drift() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)
    rows[0].original = "a completely different line"
    report = validate_exact_dubbing(rows, session.transcript)
    assert not report.ok


def test_exact_validation_catches_a_timing_drift() -> None:
    session = demo_data.build_demo_session()
    rows = list(session.exact_dubbing_rows)
    rows[0].start = rows[0].start + 0.5
    report = validate_exact_dubbing(rows, session.transcript)
    assert not report.ok


# --------------------------------------------------------------------- #
# Narration validation
# --------------------------------------------------------------------- #
def test_narration_validation_flags_empty_text() -> None:
    session = demo_data.build_demo_session()
    segments = list(session.narration_segments)
    segments[0].narration = ""
    report = validate_narration(segments)
    assert report.warnings


def test_narration_validation_accepts_the_demo_project() -> None:
    session = demo_data.build_demo_session()
    report = validate_narration(session.narration_segments)
    assert not report.errors


# --------------------------------------------------------------------- #
# Source duration
# --------------------------------------------------------------------- #
def test_source_duration_drift_blocks_render() -> None:
    issue = validate_source_duration(100.0, 104.0)
    assert issue is not None
    assert issue.severity is Severity.ERROR
    assert issue.code == "source_duration_drift"


def test_source_duration_within_tolerance_is_fine() -> None:
    assert validate_source_duration(100.0, 100.01) is None


# --------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------- #
def test_the_four_modes_exist() -> None:
    assert {mode.value for mode in AppMode} == {
        "common_editing",
        "splitter",
        "narrator",
        "exact_dubbing",
    }
    assert all(mode.display_name for mode in AppMode)


def test_terminal_and_active_job_states() -> None:
    assert JobState.COMPLETE.is_terminal
    assert JobState.FAILED.is_terminal
    assert not JobState.RENDERING.is_terminal
    assert JobState.RENDERING.is_active
    assert TaskState.RUNNING.is_active
    assert TaskState.COMPLETE.is_terminal

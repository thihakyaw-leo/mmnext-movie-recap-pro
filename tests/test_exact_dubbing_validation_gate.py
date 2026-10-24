"""Tests for Exact Dubbing validation gate."""

from __future__ import annotations

import pytest

from mmnext.domain.enums import Gender, Severity
from mmnext.domain.models import ExactDubbingRow, TranscriptRow, ValidationReport, ValidationIssue
from mmnext.domain.validation import validate_exact_dubbing
from mmnext.ui.workspace.mode_panels.exact_dubbing_panel import ExactDubbingPanel


def _make_source(n):
    return [
        TranscriptRow(
            row_id=f"s{i}",
            text=f"original {i}",
            start=float(i),
            duration=1.0,
        )
        for i in range(n)
    ]


def _make_rows(source):
    rows = []
    for i, s in enumerate(source):
        rows.append(
            ExactDubbingRow(
                row_id=s.row_id,
                original=s.text,
                start=s.start,
                duration=s.duration,
                burmese="ကျေးဇူး" if i % 2 == 0 else "",
                gender=Gender.MALE if i % 2 == 0 else Gender.FEMALE,
                edited=False,
            )
        )
    return rows


def test_immutable_id():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].row_id = "changed"
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "id_changed" in codes


def test_immutable_original():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].original = "changed"
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "original_changed" in codes


def test_immutable_start():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].start = rows[0].start + 1.0
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "start_drift" in codes


def test_immutable_duration():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].duration = rows[0].duration + 1.0
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "duration_drift" in codes


def test_valid_burmese_translation():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].burmese = "မြန်မာ"
    report = validate_exact_dubbing(rows, source)
    errors = [i for i in report.issues if i.severity is Severity.ERROR]
    burmese_errors = [i for i in errors if i.code in {"missing_burmese", "non_burmese"}]
    assert not burmese_errors


def test_empty_burmese_rejected():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].burmese = ""
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "missing_burmese" in codes


def test_invalid_gender_rejected():
    source = _make_source(1)
    rows = _make_rows(source)
    # Inject invalid gender via direct attribute
    rows[0].gender = "invalid"  # type: ignore
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "invalid_gender" in codes


def test_missing_row_rejected():
    source = _make_source(2)
    rows = _make_rows(source)[:1]
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "row_count_mismatch" in codes


def test_duplicate_id_rejected():
    source = _make_source(2)
    rows = _make_rows(source)
    rows[1].row_id = rows[0].row_id
    report = validate_exact_dubbing(rows, source)
    # The validator will see id mismatch against source for row1
    codes = {i.code for i in report.issues}
    assert "id_changed" in codes


def test_reordered_row_rejected():
    source = _make_source(2)
    rows = _make_rows(source)
    rows[0], rows[1] = rows[1], rows[0]
    report = validate_exact_dubbing(rows, source)
    codes = {i.code for i in report.issues}
    assert "id_changed" in codes or "original_changed" in codes


def test_changed_original_rejected():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].original = "different"
    report = validate_exact_dubbing(rows, source)
    assert any(i.code == "original_changed" for i in report.issues)


def test_changed_start_rejected():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].start += 0.01
    report = validate_exact_dubbing(rows, source)
    assert any(i.code == "start_drift" for i in report.issues)


def test_changed_duration_rejected():
    source = _make_source(1)
    rows = _make_rows(source)
    rows[0].duration += 0.01
    report = validate_exact_dubbing(rows, source)
    assert any(i.code == "duration_drift" for i in report.issues)


def test_render_disabled_before_validation(qtbot):
    panel = ExactDubbingPanel()
    qtbot.addWidget(panel)
    assert not panel.render_button.isEnabled()


def test_render_disabled_with_errors(qtbot):
    panel = ExactDubbingPanel()
    qtbot.addWidget(panel)
    report = ValidationReport(
        issues=[
            ValidationIssue(code="missing_burmese", message="x", severity=Severity.ERROR, row_id="r1")
        ],
        checked_rows=1,
    )
    panel.update_validation(report)
    assert not panel.render_button.isEnabled()
    assert panel.validation_badge.text() == "1 error(s)"


def test_render_enabled_after_success(qtbot):
    panel = ExactDubbingPanel()
    qtbot.addWidget(panel)
    report = ValidationReport(issues=[], checked_rows=1)
    panel.update_validation(report)
    assert panel.render_button.isEnabled()
    assert panel.validation_badge.text() == "Validated OK"


def test_validation_status_persisted(qtbot):
    panel = ExactDubbingPanel()
    qtbot.addWidget(panel)
    report = ValidationReport(issues=[], checked_rows=1)
    panel.update_validation(report)
    # Simulate rows change resetting validation
    panel.set_rows([])
    assert panel.validation_badge.text() == "Not validated"
    assert not panel.render_button.isEnabled()


def test_exact_dubbing_source_duration_mismatch():
    from mmnext.domain.validation import validate_source_duration
    issue = validate_source_duration(10.0, 10.2)
    assert issue is not None
    assert issue.code == "source_duration_drift"

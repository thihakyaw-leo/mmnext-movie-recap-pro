from mmnext.domain.models import TranscriptRow
from mmnext.services.adapters.narrator import NarratorPlanningService


def _rows():
    return [
        TranscriptRow(row_id="r1", start=0.0, duration=2.0, text="hello world"),
        TranscriptRow(row_id="r2", start=2.0, duration=3.0, text="goodbye world"),
    ]


def test_narrator_planning_service_reports_unavailable_without_legacy_root():
    svc = NarratorPlanningService(legacy_root=None)
    assert svc.plan_available() is False
    assert svc.stage_progress()["stage"] == "idle"


def test_plan_units_fallback_covers_timeline():
    svc = NarratorPlanningService(legacy_root=None)
    units = svc.plan_units(_rows(), 12.0)
    assert len(units) == 2
    # Full coverage: units ordered, non-overlapping, last reaches duration.
    assert units[0]["start"] == 0.0
    assert units[0]["end"] <= units[1]["start"]
    assert units[-1]["end"] == 12.0
    for unit in units:
        assert unit["text"]
        assert unit["end"] > unit["start"]
        assert "source_segment_ids" in unit


def test_plan_units_blank_narration_segments_via_coordinator():
    from mmnext.application.narrator_coordinator import NarratorPlanCoordinator

    coord = NarratorPlanCoordinator(NarratorPlanningService(legacy_root=None))
    segments = coord.plan(_rows(), 12.0)
    assert len(segments) == 2
    assert segments[0].segment_id == "narr_00001"
    assert segments[0].narration == ""  # blank until translated/edited
    assert segments[0].source_text == "hello world"
    assert segments[0].video_start == 0.0
    assert segments[-1].video_end == 12.0
    # Strict ordering, no gaps in coverage.
    for left, right in zip(segments, segments[1:]):
        assert left.video_end <= right.video_start
    # Exact-dubbing contract untouched: coordinator never sees exact rows.

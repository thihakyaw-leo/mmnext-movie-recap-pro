from mmnext.domain.models import NarrationSegment


def test_coordinator_plan_returns_narration_segments():
    from mmnext.application.narrator_coordinator import NarratorPlanCoordinator
    from mmnext.services.adapters.narrator import NarratorPlanningService
    from mmnext.domain.models import TranscriptRow

    rows = [
        TranscriptRow(row_id="r1", start=0.0, duration=2.0, text="one"),
        TranscriptRow(row_id="r2", start=2.0, duration=1.0, text="two"),
    ]
    coord = NarratorPlanCoordinator(NarratorPlanningService(legacy_root=None))
    segments = coord.plan(rows, 6.0)

    assert isinstance(segments[0], NarrationSegment)
    assert segments[0].narration == ""
    assert segments[0].video_start >= 0.0
    assert segments[-1].video_end == 6.0  # full coverage
    ids = [s.segment_id for s in segments]
    assert ids == sorted(ids)  # stable ascending order


def test_context_plan_narration_keeps_exact_contract(context):
    before = len(context.project.exact_rows())
    segments = context.plan_narration()
    assert len(segments) > 0
    assert all(isinstance(s, NarrationSegment) and s.narration == "" for s in segments)
    # Exact-dubbing working set is untouched by narrator planning.
    assert len(context.project.exact_rows()) == before
    assert context.session.narration_segments == segments

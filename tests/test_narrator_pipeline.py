"""Tests for the narrator heavy integration pipeline and its UI wiring."""

from __future__ import annotations

import pytest

from mmnext.application.narrator_coordinator import NarratorPlanCoordinator
from mmnext.application.narrator_pipeline_coordinator import (
    NarratorPipelineCoordinator,
)
from mmnext.domain.enums import Stage
from mmnext.domain.models import TranscriptRow
from mmnext.services.adapters.narrator_render import (
    DemoSmartSyncRenderer,
    LegacySmartSyncRenderer,
)
from mmnext.services.adapters.narrator_translation import (
    DemoTranslationProvider,
    LegacyNarratorTranslationAdapter,
)
from mmnext.services.adapters.narrator_tts import (
    DemoSpeechSynthesizer,
    LegacyEdgeTtsAdapter,
)
from mmnext.services.protocols import (
    SmartSyncRenderer,
    SpeechSynthesizer,
    TranslationProvider,
)


def _transcript() -> list[TranscriptRow]:
    return [
        TranscriptRow(row_id="1", text="Hello", start=0.0, duration=1.0),
        TranscriptRow(row_id="2", text="world", start=1.0, duration=1.0),
    ]


def _demo_coordinator(**kwargs) -> NarratorPipelineCoordinator:
    return NarratorPipelineCoordinator(
        translator=DemoTranslationProvider(),
        tts=DemoSpeechSynthesizer(),
        renderer=DemoSmartSyncRenderer(),
        **kwargs,
    )


def _output(tmp_path) -> str:
    """The render output inside the test's own directory.

    A bare relative name makes the coordinator fall back to
    ``Path(output).parent / "narrator_tts"``, which for ``"out.mp4"`` is the
    current working directory - so the rendered file and the speech cache end
    up in the repository root.  The "never write job artefacts to the CWD"
    rule forbids that, and it also leaves stray files behind in a checkout.
    """
    return str(tmp_path / "narrator_recap.mp4")


# --------------------------------------------------------------------------- #
# Protocol conformance
# --------------------------------------------------------------------------- #


def test_demo_adapters_satisfy_the_protocols() -> None:
    assert isinstance(DemoTranslationProvider(), TranslationProvider)
    assert isinstance(DemoSpeechSynthesizer(), SpeechSynthesizer)
    assert isinstance(DemoSmartSyncRenderer(), SmartSyncRenderer)
    assert isinstance(LegacyNarratorTranslationAdapter(), TranslationProvider)
    assert isinstance(LegacyEdgeTtsAdapter(), SpeechSynthesizer)
    assert isinstance(LegacySmartSyncRenderer(), SmartSyncRenderer)


def test_demo_translation_is_deterministic_and_myanmar() -> None:
    provider = DemoTranslationProvider()
    from mmnext.domain.models import NarrationSegment

    segments = [
        NarrationSegment(
            segment_id="n1",
            source_segment_ids=["1"],
            source_text="Hello",
            narration="",
            video_start=0.0,
            video_end=1.0,
        )
    ]
    first = provider.translate_segments(segments)
    second = provider.translate_segments(segments)
    assert first == second
    assert first[0] == first[0]  # stable
    assert any("\u1000" <= ch <= "\u109f" for ch in first[0])


# --------------------------------------------------------------------------- #
# Pipeline behaviour
# --------------------------------------------------------------------------- #


def test_pipeline_runs_every_stage_and_reports_progress(tmp_path) -> None:
    coordinator = _demo_coordinator()
    events = []
    result = coordinator.run(
        _transcript(),
        "dummy.mp4",
        2.0,
        _output(tmp_path),
        {},
        sink=events.append,
    )
    assert result.ok is True
    assert result.stopped is False
    assert len(result.segments) == 2
    # Every segment carries the translated narration.
    assert all(segment.narration for segment in result.segments)
    stages = [event.stage for event in events]
    assert Stage.PREPARE in stages
    assert Stage.TRANSLATE in stages
    assert Stage.SYNTHESIZE in stages
    assert Stage.RENDER in stages
    assert events[-1].percent == 100.0


def test_pipeline_stop_before_start_is_a_no_op(tmp_path) -> None:
    coordinator = _demo_coordinator()
    coordinator.request_stop()
    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    assert result.ok is False
    assert result.stopped is True
    assert result.segments == []


def test_pipeline_stop_between_stages_keeps_partial_result(tmp_path) -> None:
    class _StopAfterPlan(DemoTranslationProvider):
        def translate_segments(self, segments, **kwargs):
            raise AssertionError("translation must not run after a stop request")

    class _StoppingPlanner:
        """Plan coordinator that requests a stop right after planning."""

        def __init__(self, coordinator: NarratorPipelineCoordinator) -> None:
            self._coordinator = coordinator
            self._inner = NarratorPlanCoordinator()

        def plan(self, transcript_rows, video_duration):
            segments = self._inner.plan(transcript_rows, video_duration)
            self._coordinator.request_stop()
            return segments

    coordinator = NarratorPipelineCoordinator(
        translator=_StopAfterPlan(),
        renderer=DemoSmartSyncRenderer(),
    )
    coordinator._plan = _StoppingPlanner(coordinator)

    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    assert result.ok is False
    assert result.stopped is True
    assert len(result.segments) == 2


def test_pipeline_without_renderer_still_completes(tmp_path) -> None:
    coordinator = NarratorPipelineCoordinator(translator=DemoTranslationProvider())
    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    assert result.ok is True
    assert result.message == "Pipeline complete"


def test_pipeline_reports_render_failure(tmp_path) -> None:
    class _FailingRenderer(DemoSmartSyncRenderer):
        def render(self, video_path, segments, output_path, settings):
            return False

    coordinator = NarratorPipelineCoordinator(renderer=_FailingRenderer())
    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    assert result.ok is False
    assert result.message == "Render failed"


def test_pipeline_never_touches_exact_dubbing_rows(tmp_path) -> None:
    coordinator = _demo_coordinator()
    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    # The result only carries narrator segments; there is no exact-row field.
    assert not hasattr(result, "exact_rows")
    assert all(hasattr(segment, "source_segment_ids") for segment in result.segments)


def test_the_pipeline_cache_stays_job_scoped(tmp_path) -> None:
    """Regression: a run must never drop artefacts into the repository root.

    The coordinator falls back to ``Path(output).parent / "narrator_tts"`` when
    no cache directory is configured, so a *relative* output path puts the
    speech cache in the current working directory.  That violates the
    "never write job artefacts to the CWD" rule and leaves stray files in a
    checkout, so the cache has to follow the (absolute) output location and be
    absent from the CWD.
    """
    import pathlib

    coordinator = _demo_coordinator()
    result = coordinator.run(_transcript(), "dummy.mp4", 2.0, _output(tmp_path), {})
    assert result.ok is True

    cwd = pathlib.Path.cwd()
    cache = pathlib.Path(tmp_path) / "narrator_tts"
    assert cache.is_dir(), "the speech cache must be created next to the output"
    assert list(cache.iterdir()), "the speech cache must hold the synthesised clips"
    for stray in ("narrator_tts", "narrator_recap.mp4", "out.mp4"):
        assert not (cwd / stray).exists(), f"{stray} leaked into the working directory"


# --------------------------------------------------------------------------- #
# Legacy adapters degrade honestly
# --------------------------------------------------------------------------- #


def test_legacy_translation_without_legacy_root_returns_empty() -> None:
    adapter = LegacyNarratorTranslationAdapter(legacy_root=None)
    assert adapter.available() is False
    assert adapter.translate_segments([]) == []


def test_legacy_renderer_without_legacy_root_reports_failure(tmp_path) -> None:
    renderer = LegacySmartSyncRenderer(legacy_root=None)
    assert renderer.available() is False
    assert renderer.render("v.mp4", [], _output(tmp_path), {}) is False


def test_legacy_tts_cache_key_is_stable() -> None:
    adapter = LegacyEdgeTtsAdapter()
    assert adapter.cache_key("မြန်မာ", "my-MM-ThihaNeural", 1.0) == adapter.cache_key(
        "မြန်မာ", "my-MM-ThihaNeural", 1.0
    )
    assert adapter.voice_discovery()

"""Tests for the narrator heavy integration pipeline and its UI wiring."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

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
from mmnext.ui.app_context import AppContext
def _wait_for(predicate, timeout_ms: int = 300000) -> bool:
    import time
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        time.sleep(0.25)
        waited += 250
    return False



needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg/FFprobe are required for real transcript/render tests",
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


# --------------------------------------------------------------------------- #
# Reuse, stop granularity, output validation
# --------------------------------------------------------------------------- #


def test_a_second_run_reuses_cached_speech(tmp_path) -> None:
    """An unchanged narration must not be synthesised twice."""
    calls: list[str] = []

    class _Counting(DemoSpeechSynthesizer):
        def synthesize_segment(self, text, voice="my-MM-ThihaNeural", rate=1.0, out_path=""):
            calls.append(text)
            return super().synthesize_segment(text, voice, rate, out_path)

    coordinator = NarratorPipelineCoordinator(
        translator=DemoTranslationProvider(),
        tts=_Counting(cache_dir=str(tmp_path / "tts")),
        is_demo=True,
    )
    cache_dir = str(tmp_path / "tts")
    settings = {"tts_cache_dir": cache_dir, "ratio": "Original"}

    first = coordinator.run(_transcript(), "video.mp4", 2.0, _output(tmp_path), settings)
    assert first.ok is True
    assert calls, "the first run must synthesise"
    assert first.reused_segments == 0

    second = coordinator.run(_transcript(), "video.mp4", 2.0, str(tmp_path / "b.mp4"), settings)
    assert second.ok is True
    assert len(calls) == 2, "a cached narration must not be synthesised again"
    assert second.reused_segments == 2
    assert any("reused" in warning.lower() for warning in second.warnings)


def test_a_changed_narration_invalidates_the_cache(tmp_path) -> None:
    """Editing one narration must re-synthesise only that segment."""
    calls: list[str] = []

    class _Counting(DemoSpeechSynthesizer):
        def synthesize_segment(self, text, voice="my-MM-ThihaNeural", rate=1.0, out_path=""):
            calls.append(text)
            return super().synthesize_segment(text, voice, rate, out_path)

    class _Echo(DemoTranslationProvider):
        """Narrations that track the source text, so an edit is visible."""

        def translate_segments(self, segments, **kwargs):
            return [segment.source_text for segment in segments]

    coordinator = NarratorPipelineCoordinator(
        translator=_Echo(),
        tts=_Counting(cache_dir=str(tmp_path / "tts")),
        is_demo=True,
    )
    settings = {"tts_cache_dir": str(tmp_path / "tts")}
    coordinator.run(_transcript(), "video.mp4", 2.0, _output(tmp_path), settings)
    assert len(calls) == 2

    edited = [
        TranscriptRow(row_id="1", text="Hello", start=0.0, duration=1.0),
        TranscriptRow(row_id="2", text="changed", start=1.0, duration=1.0),
    ]
    calls.clear()
    second = coordinator.run(edited, "video.mp4", 2.0, str(tmp_path / "c.mp4"), settings)
    assert second.ok is True
    # The unchanged unit is reused; only the edited one is synthesised again.
    assert len(calls) == 1, "only the changed narration may be re-synthesised"
    assert second.reused_segments == 1


def test_the_cached_audio_needs_no_network_on_the_second_run(tmp_path) -> None:
    """The cache is consulted before the synthesiser is called at all."""
    class _Exploding(DemoSpeechSynthesizer):
        def synthesize_segment(self, *args, **kwargs):
            raise AssertionError("synthesiser must not be called for a cached narration")

    first = NarratorPipelineCoordinator(
        translator=DemoTranslationProvider(),
        tts=DemoSpeechSynthesizer(),
        is_demo=True,
    ).run(_transcript(), "video.mp4", 2.0, _output(tmp_path),
          {"tts_cache_dir": str(tmp_path / "tts")})
    assert first.ok is True

    second = NarratorPipelineCoordinator(
        translator=DemoTranslationProvider(),
        tts=_Exploding(cache_dir=str(tmp_path / "tts")),
        is_demo=True,
    ).run(_transcript(), "video.mp4", 2.0, str(tmp_path / "d.mp4"),
          {"tts_cache_dir": str(tmp_path / "tts")})
    assert second.ok is True, second.message
    assert second.reused_segments == 2


def test_a_stop_during_translation_is_honoured_per_unit(tmp_path) -> None:
    """A stop arriving mid-batch stops after that unit, not after the batch."""
    class _Stopping(DemoTranslationProvider):
        def __init__(self, coordinator):
            super().__init__()
            self._coordinator = coordinator
            self._calls = 0

        def translate_segments(self, segments, **kwargs):
            self._calls += 1
            if self._calls == 1:
                # Ask for a stop while the batch is being translated.
                self._coordinator.request_stop()
            return super().translate_segments(segments, **kwargs)

    coordinator = NarratorPipelineCoordinator(is_demo=True)
    coordinator.translator = _Stopping(coordinator)
    result = coordinator.run(
        _transcript(), "video.mp4", 2.0, _output(tmp_path),
        {"translation_batch_size": 8, "tts_cache_dir": str(tmp_path / "tts")},
    )
    assert result.ok is False
    assert result.stopped is True
    # The stop is checked per unit, so the second unit never gets translated.
    assert result.segments[0].narration
    assert not result.segments[1].narration


def test_a_real_render_is_validated_before_it_is_published(tmp_path) -> None:
    """A REAL render cannot ship a file with no audio/video streams."""
    video = _make_video(tmp_path / "source.mp4", seconds=3.0)

    class _Writing(DemoSmartSyncRenderer):
        """Reports success but writes a file that is not media at all."""

        def render(self, video_path, segments, output_path, settings):
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"not media")
            return True

    coordinator = NarratorPipelineCoordinator(
        renderer=_Writing(), is_demo=False
    )
    result = coordinator.run(
        _transcript(), str(video), 3.0, _output(tmp_path),
        {"tts_cache_dir": str(tmp_path / "tts")},
    )
    assert result.ok is False, result.message
    assert "validation" in result.message.lower(), result.message
    assert result.output_path == "", "a refused render must not publish a path"
    assert not Path(_output(tmp_path)).exists(), "no final file may be left behind"
    # The partial it did write is not mistaken for a finished render either.
    assert not Path(_output(tmp_path)).with_suffix(".mp4.partial").exists()


def test_a_demo_render_is_not_validated(tmp_path) -> None:
    """A DEMO run writes its placeholder and keeps its honest label."""
    coordinator = NarratorPipelineCoordinator(
        renderer=DemoSmartSyncRenderer(), is_demo=True
    )
    result = coordinator.run(
        _transcript(), "video.mp4", 2.0, _output(tmp_path),
        {"tts_cache_dir": str(tmp_path / "tts")},
    )
    assert result.ok is True, result.message
    assert result.is_demo is True
    assert Path(result.output_path).is_file()


def _make_video(path, seconds: float = 3.0):
    import shutil
    import subprocess

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("FFmpeg/FFprobe are required for the validation test")
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=15",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-g", "15", "-c:a", "aac", str(path),
        ],
        check=True,
    )
    return path


@needs_ffmpeg
def test_a_real_transcript_run_produces_a_narrated_recap(tmp_path) -> None:
    """A successful REAL run writes completed Job metadata and rediscover by a
    fresh AppContext.

    Uses the approved local media fixture (harvard-full.mp4) and cached Whisper
    model.  The full pipeline runs: REAL transcribe via Whisper, then narrator
    pipeline (plan -> translate -> TTS -> Smart Sync render).  The resulting
    COMPLETE Job record is rediscoverable by a fresh AppContext via
    scan()["completed_real"].
    """
    import os
    media = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MEDIA")
    model = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MODEL")
    if not media or not model:
        pytest.skip(
            "Provide an approved media fixture and local cached Whisper model "
            "for real smoke"
        )
    if not Path(media).is_file() or not Path(model).is_dir():
        pytest.skip("Local media/model fixture unavailable")

    ctx = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        ctx.start_local_transcript(str(media))
        assert _wait_for(
            lambda: ctx.transcript_state in {"complete", "failed"},
            timeout_ms=120000,
        )
        assert ctx.transcript_state == "complete", ctx.transcript_message

        ctx.start_narrator_pipeline()
        assert _wait_for(
            lambda: ctx.transcript_state in {"done", "failed"},
            timeout_ms=300000,
        )
        assert ctx.transcript_state == "done", context.narrator_message

        # Verify the completed REAL job is registered and discoverable.
        scan = ctx._job_repository.scan()
        completed_real = scan.get("completed_real", [])
        assert len(completed_real) >= 1, "No completed REAL job discovered"

        job = completed_real[0][0]
        artifact_path = Path(job.artifact_path)
        assert artifact_path.is_file(), f"Artifact missing: {artifact_path}"

        info = probe(artifact_path)
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        assert any(s["codec_type"] == "video" for s in info["streams"])

        # Duration should match the source media within tolerance.
        src_info = probe(Path(media))
        assert abs(float(info["format"]["duration"]) - float(src_info["format"]["duration"])) <= 0.5

    finally:
        ctx.jobs.clear()


@needs_ffmpeg
def test_a_fresh_appcontext_rediscovers_completed_real_transcript_job(
    tmp_path,
) -> None:
    """A fresh AppContext rediscovers a completed REAL transcript job via
    scan()["completed_real"] and reopens it through start_reopen_transcript.

    This proves restart-to-Workspace works end to end for the Narrator pipeline.
    """
    import os
    media = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MEDIA")
    model = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MODEL")
    if not media or not model:
        pytest.skip(
            "Provide an approved media fixture and local cached Whisper model "
            "for real smoke"
        )
    if not Path(media).is_file() or not Path(model).is_dir():
        pytest.skip("Local media/model fixture unavailable")

    ctx = AppContext(jobs_dir=str(tmp_path / "jobs"))
    fresh = None
    try:
        # 1. Successful REAL run: transcribe + narrate.
        ctx.start_local_transcript(str(media))
        assert _wait_for(
            lambda: ctx.transcript_state in {"complete", "failed"},
            timeout_ms=120000,
        )
        assert ctx.transcript_state == "complete", ctx.transcript_message

        ctx.start_narrator_pipeline()
        assert _wait_for(
            lambda: ctx.transcript_state in {"done", "failed"},
            timeout_ms=300000,
        )
        assert ctx.transcript_state == "done", context.narrator_message

        # 2. Fresh context rediscovers the completed REAL job.
        fresh = AppContext(jobs_dir=str(tmp_path / "jobs"))
        scan = fresh._job_repository.scan()
        completed_real = scan.get("completed_real", [])
        assert len(completed_real) >= 1, "Fresh context did not rediscover job"

        job = completed_real[0][0]
        assert job.state.name == "COMPLETE"
        assert job.is_demo is False
        assert Path(job.artifact_path).is_file()

        # 3. Explicit open path: reopen the transcript via the Jobs screen path.
        fresh.start_reopen_transcript(job.job_id, str(job.source.location))
        assert _wait_for(
            lambda: fresh.transcript_state in {"complete", "failed"},
            timeout_ms=300000,
        )
        assert fresh.transcript_state == "complete", fresh.transcript_message
        assert fresh.transcript_language, "No transcript language set"
    finally:
        ctx.jobs.clear()
        if fresh is not None:
            fresh.jobs.clear()

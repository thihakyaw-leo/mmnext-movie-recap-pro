"""Narrator heavy integration coordinator.

Orchestrates plan -> translate -> synthesise -> Smart Sync render as one
Qt-free unit.  The coordinator owns the *ordering* of the narrator stages and
the *stop* semantics; it never touches the exact-dubbing working set and it
never runs on the GUI thread (the UI wraps it in a ``QThread`` worker).

Progress is reported through a ``sink`` callback that receives
:class:`~mmnext.domain.events.ProgressEvent` objects, so the UI layer can
translate them into signals without the coordinator knowing about Qt.

Two behaviours matter beyond the ordering:

* **Reuse.** A narration whose text has not changed never gets synthesised
  again: the cache key is asked for first and a hit skips the synthesis call.
  The result carries a note per reused segment so the run never silently
  claims work it did not do.
* **Validation before publication.** A REAL render is validated with FFprobe
  before the ``.partial`` output is renamed into place, so a truncated or
  stream-less video is refused rather than shipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import Callable, Optional, Sequence

from ..domain.enums import Stage
from ..domain.events import ProgressEvent
from ..domain.models import NarrationSegment, TranscriptRow
from ..domain.paths import atomic_write_json, partial_path_for
from ..infrastructure.ffmpeg_tools import FfmpegTools
from ..services.protocols import (
    SmartSyncRenderer,
    SpeechSynthesizer,
    TranslationProvider,
)
from .narrator_coordinator import NarratorPlanCoordinator

__all__ = ["NarratorPipelineCoordinator", "NarratorPipelineResult"]


@dataclass(slots=True)
class NarratorPipelineResult:
    """Outcome of a narrator pipeline run."""

    ok: bool = False
    stopped: bool = False
    segments: list[NarrationSegment] = field(default_factory=list)
    output_path: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    is_demo: bool = True
    #: Segments whose speech was reused from the cache rather than synthesised.
    reused_segments: int = 0


class NarratorPipelineCoordinator:
    """Runs the narrator stages in order and stops between stages on request."""

    def __init__(
        self,
        plan_coordinator: Optional[NarratorPlanCoordinator] = None,
        translator: Optional[TranslationProvider] = None,
        tts: Optional[SpeechSynthesizer] = None,
        renderer: Optional[SmartSyncRenderer] = None,
        is_demo: bool = True,
        log: Optional[Callable[[str], None]] = None,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
    ) -> None:
        self._plan = plan_coordinator or NarratorPlanCoordinator()
        self.translator = translator
        self.tts = tts
        self.renderer = renderer
        self.is_demo = is_demo
        self.log = log or (lambda msg: None)
        self._stop_requested = False
        self._tools = FfmpegTools(ffmpeg=ffmpeg, ffprobe=ffprobe)

    # -- lifecycle --------------------------------------------------------- #
    def request_stop(self) -> None:
        """Ask the pipeline to stop at the next stage boundary."""
        self._stop_requested = True

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def reset(self) -> None:
        self._stop_requested = False

    # -- helpers ----------------------------------------------------------- #
    def _warn(self, warnings: list[str], message: str) -> None:
        """Surface a note to the user instead of hiding it in the log."""
        warnings.append(message)
        self.log(message)

    @staticmethod
    def _emit(
        sink: Optional[Callable[[ProgressEvent], None]],
        percent: float,
        stage: Stage,
        message: str,
    ) -> None:
        if sink is not None:
            sink(ProgressEvent(percent=percent, stage=stage, message=message))

    def _cached_audio(self, key: str, cache_root: Optional[Path]) -> Optional[Path]:
        """The cached audio file for ``key``.

        The synthesiser is asked first, because it owns the key derivation
        and may cache in a place of its own.  The coordinator then falls back
        to the cache root it was configured with, so reuse does not silently
        stop just because an adapter was built without its own cache
        directory.
        """
        finder = getattr(self.tts, "cache_hit", None)
        if finder is not None:
            try:
                hit = finder(key)
            except Exception:  # noqa: BLE001 - the synthesiser is authoritative
                hit = None
            if hit is not None and hit.is_file() and hit.stat().st_size > 0:
                return hit
        if cache_root is None:
            return None
        candidate = Path(cache_root) / f"{key}.audio"
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        except OSError:
            return None
        return None

    # -- main -------------------------------------------------------------- #
    def run(
        self,
        transcript: Sequence[TranscriptRow],
        video_path: str,
        video_duration: float,
        output_path: str,
        settings: Optional[dict] = None,
        sink: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> NarratorPipelineResult:
        """Run every configured narrator stage.

        Returns a :class:`NarratorPipelineResult`; the run is *not* an
        exception-driven flow, because a failed narrator stage is a product
        state the UI has to render, not a crash.
        """
        settings = settings or {}
        if self._stop_requested:
            return NarratorPipelineResult(stopped=True, message="Stopped before start")

        context = settings.get("context")
        glossary = settings.get("glossary")
        batch_size = max(1, int(settings.get("translation_batch_size", 8) or 8))
        checkpoint_path = settings.get("translation_checkpoint")
        warnings: list[str] = []
        reused = 0

        # -- stage 1: plan ---------------------------------------------------- #
        self.log("Narrator pipeline: planning")
        self._emit(sink, 0.0, Stage.PREPARE, "Planning narration units")
        segments = self._plan.plan(list(transcript), video_duration)
        if not segments:
            return NarratorPipelineResult(message="No narration units were produced")
        if self._stop_requested:
            return NarratorPipelineResult(
                stopped=True, segments=segments, message="Stopped after planning"
            )

        # -- stage 2: translate ----------------------------------------------- #
        if self.translator is not None:
            self.log("Narrator pipeline: translating")
            self._emit(sink, 15.0, Stage.TRANSLATE, "Translating narration units")
            language_code = settings.get("language_code")
            audit_warnings = []
            for start in range(0, len(segments), batch_size):
                if self._stop_requested:
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        stopped=True,
                        segments=segments,
                        warnings=warnings + audit_warnings,
                        reused_segments=reused,
                        message="Stopped during translation",
                    )
                batch = segments[start:start + batch_size]
                batch_id = f"batch_{start // batch_size + 1:04d}"
                translations = self.translator.translate_segments(
                    batch,
                    language_code=language_code,
                    context=context,
                    glossary=glossary,
                )
                if len(translations) != len(batch):
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        segments=segments,
                        warnings=warnings + audit_warnings,
                        reused_segments=reused,
                        message="Translation returned an unexpected number of units",
                    )
                for segment, translation in zip(batch, translations):
                    segment.translation = translation
                    segment.narration = translation
                    if self._stop_requested:
                        return NarratorPipelineResult(
                            is_demo=self.is_demo,
                            stopped=True,
                            segments=segments,
                            warnings=warnings + audit_warnings,
                            reused_segments=reused,
                            message="Stopped during translation",
                        )
                if self._stop_requested:
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        stopped=True,
                        segments=segments,
                        warnings=warnings + audit_warnings,
                        reused_segments=reused,
                        message="Stopped after translation",
                    )
                if checkpoint_path:
                    atomic_write_json(
                        checkpoint_path,
                        {
                            "batch_id": batch_id,
                            "completed": start + len(batch),
                            "total": len(segments),
                            "translations": [segment.narration for segment in batch],
                        },
                    )
            warnings.extend(audit_warnings)

        # -- stage 3: synthesise ---------------------------------------------- #
        if self.tts is not None:
            self.log("Narrator pipeline: synthesising")
            self._emit(sink, 45.0, Stage.SYNTHESIZE, "Synthesising Burmese narration")
            voice = str(settings.get("voice", "my-MM-ThihaNeural"))
            rate = float(settings.get("rate", 1.0))
            cache_dir = Path(
                settings.get("tts_cache_dir") or Path(output_path).parent / "narrator_tts"
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            for segment in segments:
                if self._stop_requested:
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        stopped=True,
                        segments=segments,
                        warnings=warnings,
                        reused_segments=reused,
                        message="Stopped during synthesis",
                    )
                if not segment.narration:
                    continue
                key = self.tts.cache_key(segment.narration, voice, rate)
                # Reuse before synthesis: an unchanged narration must not be
                # sent to the network again.
                cached = self._cached_audio(key, cache_dir)
                if cached is not None:
                    audio_path = cache_dir / f"{segment.segment_id}_{key[:16]}.audio"
                    audio_path.parent.mkdir(parents=True, exist_ok=True)
                    audio_path.write_bytes(cached.read_bytes())
                    reused += 1
                    self._warn(
                        warnings, f"{segment.segment_id}: reused cached speech (key={key[:8]})"
                    )
                    if self._stop_requested:
                        return NarratorPipelineResult(
                            is_demo=self.is_demo,
                            stopped=True,
                            segments=segments,
                            warnings=warnings,
                            reused_segments=reused,
                            message="Stopped during synthesis",
                        )
                    continue
                audio_path = cache_dir / f"{segment.segment_id}_{key[:16]}.audio"
                result_path = self.tts.synthesize_segment(
                    segment.narration, voice=voice, rate=rate, out_path=str(audio_path)
                )
                if (
                    not result_path
                    or not Path(result_path).is_file()
                    or Path(result_path).stat().st_size <= 0
                ):
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        segments=segments,
                        warnings=warnings,
                        reused_segments=reused,
                        message=f"Speech synthesis failed for {segment.segment_id}",
                    )
                # Store by key as well as by segment, so a later run can find
                # the audio even when the synthesiser keeps no cache itself.
                keyed = cache_dir / f"{key}.audio"
                if not keyed.exists():
                    try:
                        keyed.write_bytes(Path(result_path).read_bytes())
                    except OSError:
                        pass
                if self._stop_requested:
                    return NarratorPipelineResult(
                        is_demo=self.is_demo,
                        stopped=True,
                        segments=segments,
                        warnings=warnings,
                        reused_segments=reused,
                        message="Stopped during synthesis",
                    )
            if self._stop_requested:
                return NarratorPipelineResult(
                    is_demo=self.is_demo,
                    stopped=True,
                    segments=segments,
                    warnings=warnings,
                    reused_segments=reused,
                    message="Stopped after synthesis",
                )

        # -- stage 4: render --------------------------------------------------- #
        if self.renderer is None:
            self._emit(sink, 100.0, Stage.IDLE, "Narrator pipeline complete (no renderer configured)")
            return NarratorPipelineResult(
                is_demo=self.is_demo,
                ok=True,
                segments=segments,
                output_path=output_path,
                warnings=warnings,
                reused_segments=reused,
                message="Pipeline complete",
            )

        self.log("Narrator pipeline: rendering")
        self._emit(sink, 80.0, Stage.RENDER, "Rendering Smart Sync recap")
        partial_output = partial_path_for(output_path)
        Path(partial_output).parent.mkdir(parents=True, exist_ok=True)
        rendered = self.renderer.render(video_path, segments, str(partial_output), settings)
        if self._stop_requested:
            return NarratorPipelineResult(
                is_demo=self.is_demo,
                stopped=True,
                segments=segments,
                output_path=output_path,
                warnings=warnings,
                reused_segments=reused,
                message="Stopped after render",
            )
        if rendered:
            if not partial_output.is_file() or partial_output.stat().st_size <= 0:
                rendered = False
                message = "Rendered output is missing or empty"
            elif not self.is_demo and self._tools.available():
                # A REAL render is validated before it is published.  The demo
                # renderer writes a placeholder, so validating it would refuse
                # a run that is honestly labelled DEMO.
                try:
                    report = self._tools.validate_media(
                        partial_output, video_duration
                    )
                except (RuntimeError, OSError) as exc:
                    rendered = False
                    message = f"Rendered output failed validation: {exc}"
                    # A refused render must not leave a file behind that a
                    # later run could mistake for a finished one.
                    try:
                        partial_output.unlink()
                    except OSError:
                        pass
                else:
                    measured = report.get("duration", 0.0)
                    if video_duration > 0 and measured <= 0:
                        rendered = False
                        message = "Rendered output has no usable duration"
                    else:
                        os.replace(partial_output, output_path)
                        message = "Render complete"
            else:
                os.replace(partial_output, output_path)
                message = "Render complete"
        else:
            reason = str(getattr(self.renderer, "error", "") or "").strip()
            message = f"Render failed: {reason}" if reason else "Render failed"
        self._emit(sink, 100.0, Stage.RENDER, message)
        return NarratorPipelineResult(
            is_demo=self.is_demo,
            ok=bool(rendered),
            segments=segments,
            output_path=output_path if rendered else "",
            warnings=warnings,
            reused_segments=reused,
            message=message,
        )
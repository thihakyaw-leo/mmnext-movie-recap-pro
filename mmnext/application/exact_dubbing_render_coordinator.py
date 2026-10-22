"""Exact Dubbing render coordinator.

Runs TTS, speech fitting, and final render off the GUI thread. Source rows
are never reordered, merged, or retimed; speech is fitted to each locked
source duration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import subprocess
from typing import Callable, Optional, Sequence

from ..domain.enums import Stage
from ..domain.events import ProgressEvent
from ..domain.models import ExactDubbingRow
from ..domain.paths import partial_path_for
from ..services.protocols import ExactDubbingRenderer, SpeechSynthesizer


@dataclass(slots=True)
class ExactDubbingRenderResult:
    ok: bool = False
    stopped: bool = False
    output_path: str = ""
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    is_demo: bool = True


class ExactDubbingRenderCoordinator:
    def __init__(
        self,
        tts: Optional[SpeechSynthesizer] = None,
        renderer: Optional[ExactDubbingRenderer] = None,
        is_demo: bool = True,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.tts = tts
        self.renderer = renderer
        self.is_demo = is_demo
        self.log = log or (lambda msg: None)
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested

    def reset(self) -> None:
        self._stop_requested = False

    @staticmethod
    def _emit(
        sink: Optional[Callable[[ProgressEvent], None]],
        percent: float,
        stage: Stage,
        message: str,
    ) -> None:
        if sink is not None:
            sink(ProgressEvent(percent=percent, stage=stage, message=message))

    @staticmethod
    def _audio_duration(path: Path) -> Optional[float]:
        try:
            completed = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            value = completed.stdout.strip()
            if value:
                return float(value)
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        return None

    @staticmethod
    def _audio_stream_present(path: Path) -> bool:
        """Whether the rendered file really contains an audio stream."""
        try:
            completed = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "a:0",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
        return "audio" in (completed.stdout or "")

    def run(
        self,
        rows: Sequence[ExactDubbingRow],
        video_path: str,
        video_duration: float,
        output_path: str,
        settings: Optional[dict] = None,
        sink: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> ExactDubbingRenderResult:
        settings = settings or {}
        if self._stop_requested:
            return ExactDubbingRenderResult(stopped=True, message="Stopped before start")
        if not rows:
            return ExactDubbingRenderResult(message="No exact-dubbing rows to render")
        if any(not row.burmese.strip() for row in rows):
            return ExactDubbingRenderResult(message="Exact dubbing validation failed: missing Burmese text")

        warnings: list[str] = []
        voice_default = str(settings.get("voice", "my-MM-NilarNeural"))
        base_rate = float(settings.get("rate", 1.0))
        cache_dir = Path(settings.get("tts_cache_dir") or Path(output_path).parent / "exact_dubbing_tts")
        cache_dir.mkdir(parents=True, exist_ok=True)
        audio_paths: dict[str, str] = {}

        if self.tts is not None:
            self.log("Exact Dubbing: synthesising")
            self._emit(sink, 10.0, Stage.SYNTHESIZE, "Synthesising exact Burmese speech")
            total = len(rows)
            for index, row in enumerate(rows):
                if self._stop_requested:
                    return ExactDubbingRenderResult(
                        is_demo=self.is_demo,
                        stopped=True,
                        warnings=warnings,
                        message="Stopped during synthesis",
                    )
                voice = row.voice or voice_default
                key = self.tts.cache_key(row.burmese, voice, base_rate)
                audio_path = cache_dir / f"{row.row_id}_{key[:16]}.wav"
                result_path = self.tts.synthesize_segment(
                    row.burmese, voice=voice, rate=base_rate, out_path=str(audio_path)
                )
                if not result_path or not Path(result_path).is_file() or Path(result_path).stat().st_size <= 0:
                    return ExactDubbingRenderResult(
                        is_demo=self.is_demo,
                        warnings=warnings,
                        message=f"Speech synthesis failed for {row.row_id}",
                    )
                # The speech is fitted to the locked window by the renderer with
                # a pitch-preserving ``atempo`` chain.  The row's own timing is
                # never touched, so no re-synthesis at a different rate is
                # needed here.
                measured = self._audio_duration(Path(result_path))
                if measured is not None and row.duration > 0 and measured > row.duration * 1.35:
                    warnings.append(
                        f"{row.row_id}: speech is {measured / row.duration:.2f}x the source "
                        "window; consider a more concise faithful translation."
                    )
                audio_paths[row.row_id] = str(audio_path)
                self._emit(sink, 10.0 + (index + 1) / total * 35.0, Stage.SYNTHESIZE, f"Synthesised {index + 1}/{total}")

        if self._stop_requested:
            return ExactDubbingRenderResult(
                is_demo=self.is_demo,
                stopped=True,
                warnings=warnings,
                message="Stopped after synthesis",
            )

        if self.renderer is None:
            self._emit(sink, 100.0, Stage.IDLE, "Exact Dubbing render complete (no renderer configured)")
            return ExactDubbingRenderResult(
                is_demo=self.is_demo,
                ok=True,
                output_path=output_path,
                warnings=warnings,
                message="Render complete",
            )

        self.log("Exact Dubbing: rendering")
        self._emit(sink, 60.0, Stage.RENDER, "Rendering exact dubbing")
        render_settings = dict(settings)
        render_settings["audio_paths"] = audio_paths
        # The render report is written next to the *published* output.
        render_settings["report_path"] = str(
            Path(output_path).with_name(Path(output_path).stem + ".render_report.json")
        )
        partial_output = partial_path_for(output_path)
        Path(partial_output).parent.mkdir(parents=True, exist_ok=True)
        rendered = self.renderer.render(video_path, rows, str(partial_output), render_settings)
        if self._stop_requested:
            return ExactDubbingRenderResult(
                is_demo=self.is_demo,
                stopped=True,
                warnings=warnings,
                output_path=output_path,
                message="Stopped after render",
            )
        if rendered:
            if not partial_output.is_file() or partial_output.stat().st_size <= 0:
                rendered = False
                message = "Rendered output is missing or empty"
            else:
                measured_duration = self._audio_duration(partial_output)
                if measured_duration is not None and video_duration > 0:
                    tolerance = float(settings.get("duration_tolerance", 0.25))
                    if abs(measured_duration - video_duration) > tolerance:
                        rendered = False
                        message = f"Output duration {measured_duration:.3f}s differs from source {video_duration:.3f}s"
                if rendered and not self._audio_stream_present(partial_output):
                    rendered = False
                    message = "Rendered output has no audio stream"
                if rendered:
                    os.replace(partial_output, output_path)
                    message = "Render complete"
        else:
            message = "Render failed"
        self._emit(sink, 100.0, Stage.RENDER, message)
        return ExactDubbingRenderResult(
            is_demo=self.is_demo,
            ok=bool(rendered),
            output_path=output_path if rendered else "",
            warnings=warnings,
            message=message if rendered else ("Render failed" if not rendered else message),
        )

"""Exact Dubbing render coordinator.

Runs TTS, speech fitting, and final render off the GUI thread. Source rows
are never reordered, merged, or retimed; speech is fitted to each locked
source duration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
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
    def _probe_json(path: Path, ffprobe: str = "ffprobe") -> Optional[dict]:
        """Return the FFprobe document for ``path`` or ``None`` on failure."""
        try:
            completed = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return None
        if completed.returncode != 0:
            return None
        try:
            data = json.loads(completed.stdout or "{}")
        except (json.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _audio_duration(cls, path: Path, ffprobe: str = "ffprobe") -> Optional[float]:
        info = cls._probe_json(path, ffprobe)
        if info is None:
            return None
        try:
            value = info.get("format", {}).get("duration")
            return float(value) if value else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _audio_stream_duration(cls, path: Path, ffprobe: str = "ffprobe") -> Optional[float]:
        """The audio stream's own duration, which is not the container's."""
        info = cls._probe_json(path, ffprobe)
        if info is None:
            return None
        for stream in info.get("streams", []):
            if stream.get("codec_type") != "audio":
                continue
            value = stream.get("duration")
            if value in (None, "", "N/A"):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return None

    @classmethod
    def _audio_stream_present(cls, path: Path, ffprobe: str = "ffprobe") -> Optional[bool]:
        """Whether the rendered file has an audio stream.

        ``None`` means the probe itself failed, which is different from "the
        file has no audio stream" and must not be reported as the latter.
        """
        info = cls._probe_json(path, ffprobe)
        if info is None:
            return None
        return any(
            stream.get("codec_type") == "audio" for stream in info.get("streams", [])
        )

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
        ffprobe = str(settings.get("ffprobe") or "ffprobe")
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
                # The file name is built from the positional index, never from
                # the row id: a row id comes from an artefact and could contain
                # path separators.  The legacy pipeline used the same scheme.
                audio_path = cache_dir / f"{index:04d}_{key[:16]}.wav"
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
                measured = self._audio_duration(Path(result_path), ffprobe)
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
        render_settings["ffprobe"] = ffprobe
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
                # The *media* duration is authoritative.  The duration the
                # caller reported is only used to report a source change, so a
                # stale number can never shorten the output and then be used
                # to validate that shortened output.
                source_duration = self._audio_duration(Path(video_path), ffprobe)
                expected = source_duration or video_duration
                tolerance = float(settings.get("duration_tolerance", 0.25))
                measured_duration = self._audio_duration(partial_output, ffprobe)
                if measured_duration is None:
                    rendered = False
                    message = "Rendered output could not be probed"
                elif expected > 0 and abs(measured_duration - expected) > tolerance:
                    rendered = False
                    message = (
                        f"Output duration {measured_duration:.3f}s differs from "
                        f"source {expected:.3f}s"
                    )
                if rendered:
                    has_audio = self._audio_stream_present(partial_output, ffprobe)
                    if has_audio is None:
                        rendered = False
                        message = "Rendered output could not be probed for audio streams"
                    elif not has_audio:
                        rendered = False
                        message = "Rendered output has no audio stream"
                if rendered:
                    audio_duration = self._audio_stream_duration(partial_output, ffprobe)
                    if audio_duration is not None and expected > 0:
                        audio_tolerance = max(float(settings.get("audio_tolerance", 0.5)), tolerance)
                        if abs(audio_duration - expected) > audio_tolerance:
                            rendered = False
                            message = (
                                f"Output audio stream is {audio_duration:.3f}s but the "
                                f"source is {expected:.3f}s"
                            )
                if rendered:
                    os.replace(partial_output, output_path)
                    message = "Render complete"
                    self._write_render_report(output_path, video_duration)
        else:
            # A REAL failure must carry its reason, not a generic message.
            reason = str(getattr(self.renderer, "error", "") or "").strip()
            message = f"Render failed: {reason}" if reason else "Render failed"
        self._emit(sink, 100.0, Stage.RENDER, message)
        return ExactDubbingRenderResult(
            is_demo=self.is_demo,
            ok=bool(rendered),
            output_path=output_path if rendered else "",
            warnings=warnings,
            message=message,
        )

    def _write_render_report(self, output_path: str, video_duration: float) -> None:
        """Write the render report next to the *published* output.

        The report is written only after the output passed every gate, so a
        failed run never leaves a success-looking report behind.
        """
        report = dict(getattr(self.renderer, "report", {}) or {})
        if not report:
            return
        final = Path(output_path)
        report["output"] = str(final)
        report["source_duration"] = report.get("source_duration") or video_duration
        report["is_demo"] = bool(self.is_demo)
        path = final.with_name(final.stem + ".render_report.json")
        try:
            path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - disk failure
            self.log(f"Could not write the render report: {exc}")

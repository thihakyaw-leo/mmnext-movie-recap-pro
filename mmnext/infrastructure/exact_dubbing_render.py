"""Real exact-dubbing renderer built on FFmpeg and FFprobe.

This is the native implementation of the legacy ``movie-recap`` exact-dubbing
contract.  It does not use moviepy and it never edits the legacy project.

The chain is:

1. **Fit** - every row's speech is squeezed into its *locked* window with a
   pitch-preserving FFmpeg ``atempo`` chain.  A second correction pass runs
   when FFmpeg's sample-window rounding leaves the clip longer than the
   window.  The source row's ``start``/``duration`` are never changed: the
   speech is fitted to the row, not the row to the speech.
2. **Mix** - the fitted clips are placed on an exact 44100 Hz timeline.  The
   mix is written through a bounded ``numpy`` memmap so a long movie does not
   need the whole timeline in RAM, and the areas without speech stay silent.
3. **Mux** - the untouched source video is muxed with the mixed track.  Every
   video frame and the original duration are preserved.
4. **Validate** - FFprobe must find an audio stream and a duration that
   matches the source.  Only then is the ``.partial`` output renamed into
   place; a failed validation leaves no final file behind.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..domain.exact_dubbing import atempo_chain, speech_window
from ..domain.models import ExactDubbingRow
from ..services.protocols import ExactDubbingRenderer

__all__ = ["FfmpegExactDubbingRenderer", "RenderValidationError"]

#: The mix grid.  The legacy pipeline used the same rate.
MIX_SAMPLE_RATE = 44100

#: FFmpeg's ``atempo`` rounds to a sample window; a clip may end up this much
#: longer than the target before a correction pass is required.
FIT_TOLERANCE = 0.04

#: Warning threshold for the speed fit.  It is a warning, never a cap.
SPEED_WARNING_RATIO = 1.35


class RenderValidationError(RuntimeError):
    """Raised when the rendered output fails the final validation."""


class FfmpegExactDubbingRenderer(ExactDubbingRenderer):
    """Render a dubbed video from fitted Burmese speech."""

    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        log: Optional[Callable[[str], None]] = None,
        work_dir: Optional[str] = None,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.log = log or (lambda msg: None)
        self.work_dir = Path(work_dir) if work_dir else None
        self._stage = "idle"

    # -- capability --------------------------------------------------------- #
    def available(self) -> bool:
        """True when both FFmpeg tools are on PATH."""
        return bool(shutil.which(self.ffmpeg)) and bool(shutil.which(self.ffprobe))

    def stage_progress(self) -> dict:
        return {"stage": self._stage, "percent": 0.0}

    # -- FFmpeg helpers ----------------------------------------------------- #
    def _run(self, command: Sequence[str]) -> None:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"{Path(command[0]).name} failed ({completed.returncode}): {detail[-800:]}"
            )

    def _probe(self, path: str | Path) -> dict:
        completed = subprocess.run(
            [
                self.ffprobe,
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
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()
            raise RuntimeError(f"ffprobe failed for {path}: {detail[-400:]}")
        try:
            return json.loads(completed.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ffprobe returned unreadable JSON for {path}") from exc

    @staticmethod
    def _duration(info: dict) -> float:
        try:
            return float(info.get("format", {}).get("duration", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _has_audio_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "audio" for stream in info.get("streams", [])
        )

    @staticmethod
    def _frame_rate(info: dict) -> float:
        for stream in info.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            for key in ("avg_frame_rate", "r_frame_rate"):
                value = str(stream.get(key) or "")
                if "/" in value:
                    num, _, den = value.partition("/")
                    try:
                        num_f, den_f = float(num), float(den)
                    except ValueError:
                        continue
                    if num_f > 0 and den_f > 0:
                        return num_f / den_f
        return 0.0

    # -- fitting ------------------------------------------------------------ #
    def _fit_row(
        self,
        raw_audio: Path,
        target: float,
        ratio: float,
        destination: Path,
    ) -> Path:
        """Fit ``raw_audio`` into ``target`` seconds and return the result."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        if ratio <= 1.0:
            # The speech is short enough: only trim it to the window.
            self._run(
                [
                    self.ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(raw_audio),
                    "-ar",
                    str(MIX_SAMPLE_RATE),
                    "-ac",
                    "1",
                    "-t",
                    f"{target:.6f}",
                    str(destination),
                ]
            )
            return destination

        chain = atempo_chain(ratio)
        self._run(
            [
                self.ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(raw_audio),
                "-af",
                chain,
                "-ar",
                str(MIX_SAMPLE_RATE),
                "-ac",
                "1",
                "-t",
                f"{target:.6f}",
                str(destination),
            ]
        )
        produced = self._duration(self._probe(destination))
        if produced > target + FIT_TOLERANCE:
            # FFmpeg rounds the atempo window; correct it and add 1 % margin.
            corrected = ratio * (produced / target) * 1.01
            self._run(
                [
                    self.ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-i",
                    str(raw_audio),
                    "-af",
                    atempo_chain(corrected),
                    "-ar",
                    str(MIX_SAMPLE_RATE),
                    "-ac",
                    "1",
                    "-t",
                    f"{target:.6f}",
                    str(destination),
                ]
            )
        return destination

    # -- mixing ------------------------------------------------------------- #
    @staticmethod
    def _read_wav_mono(path: Path) -> "object":
        """Read a mono PCM WAV into a numpy float64 array in ``[-1, 1]``."""
        import numpy as np

        with wave.open(str(path), "rb") as handle:
            if handle.getnchannels() != 1:
                raise RenderValidationError(
                    f"Fitted clip {path.name} is not mono ({handle.getnchannels()} channels)"
                )
            if handle.getsampwidth() != 2:
                raise RenderValidationError(
                    f"Fitted clip {path.name} is not 16-bit PCM"
                )
            if handle.getframerate() != MIX_SAMPLE_RATE:
                raise RenderValidationError(
                    f"Fitted clip {path.name} is not {MIX_SAMPLE_RATE} Hz"
                )
            frames = handle.getnframes()
            raw = handle.readframes(frames)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        return samples

    def _mix(
        self,
        placements: Sequence[tuple[float, Path]],
        total: float,
        destination: Path,
        scratch: Path,
    ) -> None:
        """Place every fitted clip on an exact 44100 Hz timeline."""
        import numpy as np

        frames = max(1, int(math.ceil(total * MIX_SAMPLE_RATE)))
        scratch.parent.mkdir(parents=True, exist_ok=True)
        mix = np.memmap(str(scratch), dtype="float64", mode="w+", shape=(frames,))
        try:
            mix[:] = 0.0
            for start, clip in placements:
                samples = self._read_wav_mono(clip)
                if samples.size == 0:
                    continue
                begin = int(round(start * MIX_SAMPLE_RATE))
                if begin >= frames:
                    continue
                count = min(samples.size, frames - begin)
                mix[begin:begin + count] += samples[:count]
            destination.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(destination), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(MIX_SAMPLE_RATE)
                chunk = 65536
                for offset in range(0, frames, chunk):
                    block = np.asarray(mix[offset:offset + chunk])
                    clipped = np.clip(block, -1.0, 1.0)
                    handle.writeframesraw(
                        (clipped * 32767.0).astype("<i2").tobytes()
                    )
        finally:
            del mix
            try:
                scratch.unlink()
            except OSError:
                pass

    # -- muxing ------------------------------------------------------------- #
    def _mux(
        self,
        video_path: Path,
        audio_path: Path,
        total: float,
        destination: Path,
    ) -> str:
        common = [
            self.ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{total:.9f}",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
        ]
        destination.parent.mkdir(parents=True, exist_ok=True)
        attempts = (
            ["-c:v", "h264_nvenc", "-preset", "fast"],
            ["-c:v", "libx264", "-preset", "medium"],
        )
        last_error = ""
        for extra in attempts:
            command = common + extra + ["-movflags", "+faststart", str(destination)]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode == 0:
                codec = extra[1]
                self.log(f"Exact dubbing muxed with {codec}")
                return codec
            last_error = (completed.stderr or completed.stdout or "").strip()
            self.log(f"GPU export unavailable ({last_error[-200:]}); falling back to CPU")
        raise RuntimeError(f"FFmpeg mux failed: {last_error[-800:]}")

    # -- protocol ----------------------------------------------------------- #
    def render(
        self,
        video_path: str,
        rows: Sequence[ExactDubbingRow],
        output_path: str,
        settings: dict,
    ) -> bool:
        """Render the dubbed video.  Returns ``True`` only on success."""
        settings = dict(settings or {})
        audio_paths: dict[str, str] = dict(settings.get("audio_paths") or {})
        self._stage = "render"
        try:
            if not self.available():
                self.log("FFmpeg/FFprobe are unavailable; no video was rendered")
                return False
            if not rows:
                self.log("No exact-dubbing rows to render")
                return False
            missing = [row.row_id for row in rows if row.row_id not in audio_paths]
            if missing:
                self.log(f"No synthesised audio for rows: {', '.join(missing[:5])}")
                return False

            source = Path(video_path)
            if not source.is_file():
                self.log(f"Source video is missing: {source}")
                return False

            probe = self._probe(source)
            total = float(settings.get("total_duration") or self._duration(probe))
            if total <= 0:
                self.log("Source video has no usable duration")
                return False
            fps = self._frame_rate(probe)

            destination = Path(output_path)
            work = self.work_dir or destination.parent / "exact_dubbing_work"
            work.mkdir(parents=True, exist_ok=True)
            fitted_dir = work / "fitted"
            fitted_dir.mkdir(parents=True, exist_ok=True)

            # -- fit every row into its locked window ------------------------ #
            placements: list[tuple[float, Path]] = []
            details: list[dict] = []
            for index, row in enumerate(rows):
                raw = Path(audio_paths[row.row_id])
                if not raw.is_file():
                    self.log(f"Synthesised audio is missing for {row.row_id}")
                    return False
                next_start = (
                    rows[index + 1].start if index + 1 < len(rows) else None
                )
                target = speech_window(row.start, row.duration, next_start, total)
                if target <= 0:
                    self.log(f"Row {row.row_id} has no usable speech window")
                    return False
                raw_info = self._probe(raw)
                raw_duration = self._duration(raw_info)
                ratio = raw_duration / target if target > 0 else 1.0
                fitted = self._fit_row(
                    raw, target, ratio, fitted_dir / f"{row.row_id}_fitted.wav"
                )
                if ratio > SPEED_WARNING_RATIO:
                    self.log(
                        f"[Speed warning] {row.row_id}: {ratio:.2f}x needed. "
                        "Consider a more concise faithful translation."
                    )
                placements.append((row.start, fitted))
                details.append(
                    {
                        "id": row.row_id,
                        "start": row.start,
                        "duration": row.duration,
                        "window": round(target, 6),
                        "voice": row.voice,
                        "raw_duration": round(raw_duration, 6),
                        "speed": round(ratio, 4),
                    }
                )

            # -- mix ------------------------------------------------------------ #
            self.log("Exact dubbing: mixing the dubbed audio")
            audio_out = work / "dubbed_audio.wav"
            self._mix(placements, total, audio_out, work / "dubbed_mix.float64.tmp")

            # -- mux ------------------------------------------------------------ #
            self.log("Exact dubbing: muxing the dubbed video")
            partial = destination.with_name(destination.stem + ".partial.mp4")
            codec = self._mux(source, audio_out, total, partial)

            # -- validate before publishing ------------------------------------ #
            info = self._probe(partial)
            measured = self._duration(info)
            tolerance = max(0.1, (1.0 / fps) if fps > 0 else 0.0)
            if abs(measured - total) > tolerance:
                raise RenderValidationError(
                    f"Output duration mismatch: source={total:.3f}s, output={measured:.3f}s"
                )
            if not self._has_audio_stream(info):
                raise RenderValidationError("Output audio stream is missing.")
            if not self._has_video_stream(info):
                raise RenderValidationError("Output video stream is missing.")

            os.replace(partial, destination)
            report = {
                "source_duration": total,
                "output_duration": measured,
                "encoder": codec,
                "segments": details,
                "output": str(destination),
            }
            report_path = Path(
                settings.get("report_path")
                or destination.with_name(destination.stem + ".render_report.json")
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.log(f"Exact dubbing render complete: {destination}")
            return True
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            self.log(f"Exact dubbing render failed: {exc}")
            return False
        finally:
            self._stage = "idle"

    @staticmethod
    def _has_video_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "video" for stream in info.get("streams", [])
        )

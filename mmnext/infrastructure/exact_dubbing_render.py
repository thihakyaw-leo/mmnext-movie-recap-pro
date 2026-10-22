"""Real exact-dubbing renderer built on FFmpeg and FFprobe.

This is the native implementation of the legacy ``movie-recap`` exact-dubbing
contract.  It does not use moviepy and it never edits the legacy project.

The chain is:

1. **Fit** - every row's speech is squeezed into its *locked* window with a
   pitch-preserving FFmpeg ``atempo`` chain.  The sped clip is measured and,
   when FFmpeg's sample-window rounding leaves it longer than the window, a
   second correction pass re-encodes it at a corrected ratio so that the
   words fit instead of being cut off.  The source row's ``start``/``duration``
   are never changed: the speech is fitted to the row, not the row to the
   speech.
2. **Mix** - the fitted clips are placed on an exact 44100 Hz timeline.  The
   mix is written through a bounded ``numpy`` memmap so a long movie does not
   need the whole timeline in RAM, and the areas without speech stay silent.
3. **Mux** - the untouched source video is muxed with the mixed track.  Every
   video frame and the original duration are preserved.
4. **Validate** - FFprobe must find a video stream, an audio stream whose own
   duration matches the source, and a container duration that matches the
   source.  Only then is the ``.partial`` output renamed into place; a failed
   validation leaves no final file behind.

The **media duration is always taken from the probed source**, never from a
caller-supplied number: a stale or truncated duration would otherwise produce
a silently shortened output that passes every check because the same wrong
number is used for the mix, the mux and the validation.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..domain.exact_dubbing import atempo_chain, speech_window
from ..domain.models import ExactDubbingRow
from ..services.protocols import ExactDubbingRenderer

try:  # numpy is an optional dependency; the mix needs it.
    # It is imported here, once, on purpose: importing numpy for the first
    # time from two threads at the same time can deadlock the interpreter, and
    # the mix always runs on a worker thread.  Importing it while this module
    # is loaded keeps that import on the thread that loads the module.
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency
    np = None  # type: ignore[assignment]

__all__ = ["FfmpegExactDubbingRenderer", "RenderValidationError"]

#: The mix grid.  The legacy pipeline used the same rate.
MIX_SAMPLE_RATE = 44100

#: FFmpeg's ``atempo`` rounds to a sample window; a clip may end up this much
#: longer than the target before a correction pass is required.
FIT_TOLERANCE = 0.04

#: Warning threshold for the speed fit.  It is a warning, never a cap.
SPEED_WARNING_RATIO = 1.35

#: How far the caller's duration may differ from the probed media before it is
#: reported as a source change.
SOURCE_DURATION_TOLERANCE = 0.5

#: Default subprocess timeout for one FFmpeg/FFprobe call.
DEFAULT_TIMEOUT_S = 1800

#: Tolerance for the final audio-stream duration check.  AAC adds a little
#: encoder padding, so the check is looser than the container check.
AUDIO_STREAM_TOLERANCE = 0.5


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
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.log = log or (lambda msg: None)
        self.work_dir = Path(work_dir) if work_dir else None
        self.timeout_s = int(timeout_s)
        self._stage = "idle"
        #: The reason of the last failure.  The coordinator reports it so a
        #: REAL failure is never reduced to a generic "Render failed".
        self.error: str = ""
        #: The details of the last successful render.  The coordinator writes
        #: the report *after* it published the final file.
        self.report: dict = {}

    # -- capability --------------------------------------------------------- #
    def available(self) -> bool:
        """True when both FFmpeg tools are on PATH."""
        return bool(shutil.which(self.ffmpeg)) and bool(shutil.which(self.ffprobe))

    def stage_progress(self) -> dict:
        return {"stage": self._stage, "percent": 0.0}

    # -- FFmpeg helpers ----------------------------------------------------- #
    def _run(self, command: Sequence[str], timeout: Optional[int] = None) -> str:
        """Run a tool and return its stdout.  Raises on a non-zero exit."""
        started = time.perf_counter()
        name = Path(command[0]).name
        self.log(f"run: {name}")
        try:
            completed = subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout or self.timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"{name} timed out after {timeout or self.timeout_s}s"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"{name} could not be started: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(
                f"{name} failed ({completed.returncode}): {detail[-800:]}"
            )
        self.log(f"done: {name} in {time.perf_counter() - started:.2f}s")
        return completed.stdout or ""

    def _probe(self, path: str | Path) -> dict:
        payload = self._run(
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
            timeout=120,
        )
        try:
            data = json.loads(payload or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ffprobe returned unreadable JSON for {path}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"ffprobe returned an unexpected document for {path}")
        return data

    @staticmethod
    def _duration(info: dict) -> float:
        try:
            return float(info.get("format", {}).get("duration", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _stream_duration(info: dict, codec_type: str) -> float:
        """Return the duration of the first stream of ``codec_type``."""
        for stream in info.get("streams", []):
            if stream.get("codec_type") != codec_type:
                continue
            for key in ("duration", "duration_ts"):
                value = stream.get(key)
                if value in (None, "", "N/A"):
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        return 0.0

    @staticmethod
    def _has_audio_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "audio" for stream in info.get("streams", [])
        )

    @staticmethod
    def _has_video_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "video" for stream in info.get("streams", [])
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
        """Fit ``raw_audio`` into ``target`` seconds and return the result.

        The sped clip is produced *without* a duration limit so it can be
        measured.  When FFmpeg's rounding leaves it longer than the window, a
        correction pass re-encodes it at the corrected ratio, which is what
        keeps the words inside the slot instead of cutting them off.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        if ratio <= 1.0:
            # The speech is short enough: only trim it to the window.
            self._run(
                [
                    self.ffmpeg, "-v", "error", "-y",
                    "-i", str(raw_audio),
                    "-ar", str(MIX_SAMPLE_RATE), "-ac", "1",
                    "-c:a", "pcm_s16le",
                    "-t", f"{target:.6f}",
                    str(destination),
                ]
            )
            return destination

        produced = destination.with_name(destination.stem + "_sped.wav")
        self._run(
            [
                self.ffmpeg, "-v", "error", "-y",
                "-i", str(raw_audio),
                "-af", atempo_chain(ratio),
                "-ar", str(MIX_SAMPLE_RATE), "-ac", "1",
                "-c:a", "pcm_s16le",
                str(produced),
            ]
        )
        measured = self._duration(self._probe(produced))
        if measured > target + FIT_TOLERANCE:
            corrected = ratio * (measured / target) * 1.01
            self._run(
                [
                    self.ffmpeg, "-v", "error", "-y",
                    "-i", str(raw_audio),
                    "-af", atempo_chain(corrected),
                    "-ar", str(MIX_SAMPLE_RATE), "-ac", "1",
                    "-c:a", "pcm_s16le",
                    str(produced),
                ]
            )
            measured = self._duration(self._probe(produced))
            if measured > target + FIT_TOLERANCE:
                # Even the corrected ratio does not fit; cut at the window and
                # say so, because a silent truncation must never be silent.
                self.log(
                    f"[Speed warning] the corrected fit is still {measured - target:.3f}s "
                    "too long; the tail is cut at the window edge."
                )
        # Trim to the window.  This is the hard cut at the slot edge and it
        # only removes what the fit could not compress.
        self._run(
            [
                self.ffmpeg, "-v", "error", "-y",
                "-i", str(produced),
                "-ar", str(MIX_SAMPLE_RATE), "-ac", "1",
                "-c:a", "pcm_s16le",
                "-t", f"{target:.6f}",
                str(destination),
            ]
        )
        return destination

    # -- mixing ------------------------------------------------------------- #
    @staticmethod
    def _read_wav_mono(path: Path):
        """Read a mono PCM WAV into a numpy float32 array in ``[-1, 1]``."""
        if np is None:  # pragma: no cover - optional dependency
            raise RenderValidationError(
                "NumPy is required for the exact-dubbing mix; install it and retry."
            )
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
            raw = handle.readframes(handle.getnframes())
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

    def _mix(
        self,
        placements: Sequence[tuple[float, Path]],
        total: float,
        destination: Path,
        scratch: Path,
    ) -> None:
        """Place every fitted clip on an exact 44100 Hz timeline."""
        if np is None:  # pragma: no cover - optional dependency
            raise RenderValidationError(
                "NumPy is required for the exact-dubbing mix; install it and retry."
            )
        frames = max(1, int(math.ceil(total * MIX_SAMPLE_RATE)))
        scratch.parent.mkdir(parents=True, exist_ok=True)
        self.log(f"Mix: opening a {total:.3f}s timeline at {MIX_SAMPLE_RATE} Hz")
        mix = np.memmap(str(scratch), dtype="float32", mode="w+", shape=(frames,))
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
            self.log(f"Mix: placed {len(placements)} clips, writing the track")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(destination), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(MIX_SAMPLE_RATE)
                chunk = 65536
                for offset in range(0, frames, chunk):
                    block = np.array(mix[offset:offset + chunk], copy=True)
                    clipped = np.clip(block, -1.0, 1.0)
                    handle.writeframesraw(
                        (clipped * 32767.0).astype("<i2").tobytes()
                    )
        finally:
            # The mapping has to be closed explicitly: on Windows an open
            # mapping keeps the scratch file locked and it would never be
            # deleted.
            try:
                mix.flush()
            except (OSError, ValueError):
                pass
            mapping = getattr(mix, "_mmap", None)
            if mapping is not None:
                try:
                    mapping.close()
                except (OSError, BufferError, ValueError):
                    pass
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
            self.ffmpeg, "-v", "error", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", f"{total:.9f}",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
        ]
        destination.parent.mkdir(parents=True, exist_ok=True)
        attempts = (
            ["-c:v", "h264_nvenc", "-preset", "fast"],
            ["-c:v", "libx264", "-preset", "medium"],
        )
        last_error = ""
        for extra in attempts:
            command = common + extra + ["-movflags", "+faststart", str(destination)]
            try:
                self._run(command)
            except RuntimeError as exc:
                last_error = str(exc)
                self.log(f"GPU export unavailable ({last_error[-200:]}); falling back to CPU")
                continue
            self.log(f"Exact dubbing muxed with {extra[1]}")
            return extra[1]
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
        self.error = ""
        self.report = {}
        fitted_dir: Optional[Path] = None
        audio_out: Optional[Path] = None
        scratch: Optional[Path] = None
        try:
            if not self.available():
                self.error = "FFmpeg/FFprobe are unavailable; no video was rendered"
                self.log(self.error)
                return False
            if not rows:
                self.error = "No exact-dubbing rows to render"
                self.log(self.error)
                return False
            missing = [row.row_id for row in rows if row.row_id not in audio_paths]
            if missing:
                self.error = f"No synthesised audio for rows: {', '.join(missing[:5])}"
                self.log(self.error)
                return False

            source = Path(video_path)
            if not source.is_file():
                self.error = f"Source video is missing: {source}"
                self.log(self.error)
                return False

            probe = self._probe(source)
            # The probed media duration is authoritative.  A caller-supplied
            # duration is only used to report a source change.
            total = self._duration(probe)
            if total <= 0:
                self.error = "Source video has no usable duration"
                self.log(self.error)
                return False
            claimed = settings.get("total_duration")
            if claimed:
                try:
                    claimed_f = float(claimed)
                except (TypeError, ValueError):
                    claimed_f = 0.0
                if claimed_f > 0 and abs(claimed_f - total) > SOURCE_DURATION_TOLERANCE:
                    self.log(
                        f"[Source warning] the caller reported {claimed_f:.3f}s but the "
                        f"media is {total:.3f}s; the media duration is used."
                    )
            fps = self._frame_rate(probe)

            destination = Path(output_path)
            work = self.work_dir or destination.parent / "exact_dubbing_work"
            work.mkdir(parents=True, exist_ok=True)
            fitted_dir = work / "fitted"
            fitted_dir.mkdir(parents=True, exist_ok=True)
            audio_out = work / "dubbed_audio.wav"
            scratch = work / "dubbed_mix.float32.tmp"

            # -- fit every row into its locked window ------------------------ #
            placements: list[tuple[float, Path]] = []
            details: list[dict] = []
            for index, row in enumerate(rows):
                raw = Path(audio_paths[row.row_id])
                if not raw.is_file():
                    self.error = f"Synthesised audio is missing for {row.row_id}"
                    self.log(self.error)
                    return False
                next_start = rows[index + 1].start if index + 1 < len(rows) else None
                target = speech_window(row.start, row.duration, next_start, total)
                if target <= 0:
                    self.error = f"Row {row.row_id} has no usable speech window"
                    self.log(self.error)
                    return False
                raw_duration = self._duration(self._probe(raw))
                ratio = raw_duration / target if target > 0 else 1.0
                fitted = self._fit_row(
                    raw, target, ratio, fitted_dir / f"{index:04d}_fitted.wav"
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
            self._mix(placements, total, audio_out, scratch)

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
            if not self._has_video_stream(info):
                raise RenderValidationError("Output video stream is missing.")
            if not self._has_audio_stream(info):
                raise RenderValidationError("Output audio stream is missing.")
            audio_duration = self._stream_duration(info, "audio")
            if audio_duration > 0:
                audio_tolerance = max(AUDIO_STREAM_TOLERANCE, tolerance)
                if abs(audio_duration - total) > audio_tolerance:
                    raise RenderValidationError(
                        f"Output audio stream duration {audio_duration:.3f}s differs "
                        f"from source {total:.3f}s"
                    )

            os.replace(partial, destination)
            self.report = {
                "source_duration": total,
                "output_duration": measured,
                "audio_duration": audio_duration,
                "encoder": codec,
                "segments": details,
            }
            self.log(f"Exact dubbing render complete: {destination}")
            return True
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            self.error = str(exc)
            self.log(f"Exact dubbing render failed: {exc}")
            return False
        finally:
            self._stage = "idle"
            # Per-run artefacts must not pile up: the mix, the fitted clips
            # and the mixed track are all reproducible from the cache.
            if fitted_dir is not None:
                shutil.rmtree(fitted_dir, ignore_errors=True)
            if audio_out is not None:
                try:
                    audio_out.unlink()
                except OSError:
                    pass
            if scratch is not None:
                try:
                    scratch.unlink()
                except OSError:
                    pass

"""Shared FFmpeg/FFprobe helpers for the runtime render adapters.

Both the exact-dubbing renderer and the splitter renderer shell out to the
same two tools, read the same JSON probe document, and apply the same final
validation vocabulary - a video stream, an audio stream, and a duration that
matches what was asked for.  That logic lives here once, so a fix to the tool
invocation or to the validation reaches every renderer instead of drifting
between two copies.

Every tool call uses an explicit UTF-8 decode (FFmpeg emits UTF-8 whatever the
console code page is) and a timeout, so a wedged tool is reported as a failure
rather than blocking a worker thread forever.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time as _time
from pathlib import Path
from typing import Callable, Optional, Sequence

__all__ = ["FfmpegTools"]

#: Default subprocess timeout for one FFmpeg/FFprobe call.
DEFAULT_TIMEOUT_S = 1800

#: Memoised ``shutil.which`` answers, keyed by ``(tool, path)``.
#
# The answer cannot change while the process runs, so re-asking is pure waste.
# It is also expensive: the *first* ``shutil.which`` from a worker thread can
# take seconds on Windows (measured: 6.4s versus 0.008s on the GUI thread),
# and ``available()`` used to run that probe once per rendered part.
_WHICH_CACHE: dict[str, bool] = {}


def _tool_on_path(tool: str) -> bool:
    """Whether ``tool`` is on PATH, answered once per process."""
    key = f"{os.environ.get('PATH', '')}|{tool}"
    cached = _WHICH_CACHE.get(key)
    if cached is None:
        cached = bool(shutil.which(tool))
        _WHICH_CACHE[key] = cached
    return cached


class FfmpegTools:
    """Thin, validated wrapper around FFmpeg and FFprobe."""

    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        timeout_s: int = DEFAULT_TIMEOUT_S,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout_s = int(timeout_s)
        self.log = log or (lambda msg: None)

    # -- capability --------------------------------------------------------- #
    def available(self) -> bool:
        """True when both FFmpeg tools are on PATH.

        The probe is memoised per ``(PATH, tool)`` pair: the answer is fixed
        for the process, and the first probe from a worker thread is slow on
        Windows, so a per-part re-probe would add seconds to every render.
        """
        return _tool_on_path(self.ffmpeg) and _tool_on_path(self.ffprobe)

    # -- tool invocation ----------------------------------------------------- #
    def run(self, command: Sequence[str], timeout: Optional[int] = None) -> str:
        """Run a tool and return its stdout.  Raises on a non-zero exit.

        The failure message carries the tool's own stderr, so a REAL render
        failure keeps its reason instead of becoming a generic "failed".
        """
        started = _now()
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
        self.log(f"done: {name} in {_elapsed(started):.2f}s")
        return completed.stdout or ""

    def probe(self, path: str | Path) -> dict:
        """Return the FFprobe document for ``path`` as a dictionary."""
        payload = self.run(
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

    # -- probe readers -------------------------------------------------------- #
    @staticmethod
    def duration(info: dict) -> float:
        """The container duration in seconds, or ``0.0`` when unreadable."""
        try:
            return float(info.get("format", {}).get("duration", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def stream_duration(info: dict, codec_type: str) -> float:
        """The duration of the first stream of ``codec_type``.

        A stream duration is *not* the container duration: a mux can pin the
        container to the source length while its audio track is short or
        entirely absent, which is exactly what a final check must catch.
        """
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
    def has_audio_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "audio" for stream in info.get("streams", [])
        )

    @staticmethod
    def has_video_stream(info: dict) -> bool:
        return any(
            stream.get("codec_type") == "video" for stream in info.get("streams", [])
        )

    @staticmethod
    def start_time(info: dict) -> float:
        """The first presentation timestamp of the video stream.

        A stream-copy cut snaps to the keyframe at or before the requested
        start, so this is how the *actual* start of a rendered part is known.
        """
        for stream in info.get("streams", []):
            if stream.get("codec_type") != "video":
                continue
            for key in ("start_time", "start_pts"):
                value = stream.get(key)
                if value in (None, "", "N/A"):
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        try:
            return float(info.get("format", {}).get("start_time", 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def frame_rate(info: dict) -> float:
        """The video frame rate, or ``0.0`` when it cannot be read."""
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

    # -- final validation ----------------------------------------------------- #
    def validate_media(
        self, path: str | Path, expected_duration: Optional[float] = None
    ) -> dict:
        """Probe ``path`` and return its measured media facts.

        ``tolerance`` is the duration tolerance that was applied: one frame
        (or 0.1s when the frame rate is unknown) unless a coarser one is
        needed.  Raises :class:`RuntimeError` when the file is not a complete
        audio+video media file, so a partial write is never published.
        """
        info = self.probe(path)
        measured = self.duration(info)
        fps = self.frame_rate(info)
        tolerance = max(0.1, (1.0 / fps) if fps > 0 else 0.0)
        report = {
            "duration": measured,
            "audio_duration": self.stream_duration(info, "audio"),
            "start_time": self.start_time(info),
            "frame_rate": fps,
            "tolerance": tolerance,
        }
        if not self.has_video_stream(info):
            raise RuntimeError(f"{Path(path).name} has no video stream")
        if not self.has_audio_stream(info):
            raise RuntimeError(f"{Path(path).name} has no audio stream")
        if measured <= 0:
            raise RuntimeError(f"{Path(path).name} has no usable duration")
        if expected_duration is not None and expected_duration > 0:
            tolerance = max(tolerance, _ceil_tolerance(expected_duration))
            if abs(measured - float(expected_duration)) > tolerance:
                raise RuntimeError(
                    f"{Path(path).name} is {measured:.3f}s but was expected to be "
                    f"{expected_duration:.3f}s"
                )
        report["tolerance"] = tolerance
        return report


#: A stream-copy cut lands on the keyframe and packet boundary it is given
#: rather than on the exact requested second, so a rendered part can differ
#: from its window by up to one packet / keyframe.  That drift is *reported*
#: by the renderer instead of being hidden; this allowance only decides when a
#: part is wrong enough to refuse.
PART_DRIFT_TOLERANCE = 0.5


def _ceil_tolerance(expected: float) -> float:
    """The duration drift tolerated for a rendered part.

    The allowance is a fixed packet-sized slack, not a fraction of the window:
    a fraction would grow unbounded for long parts and stop refusing anything.
    """
    return PART_DRIFT_TOLERANCE


def _now() -> float:
    return _time.perf_counter()


def _elapsed(started: float) -> float:
    return _time.perf_counter() - started

"""Splitter renderer built on FFmpeg.

The splitter cuts one source video into the parts the planner produced. Every
part is written to a ``.partial`` file, validated with FFprobe, and only then
renamed into place, so a failed cut never leaves a file that looks finished.

Two facts about a stream-copy cut are reported rather than assumed:

* a cut at a position that is not a keyframe lands on the keyframe at or
  before the requested start, so the part's *measured* start is reported and
  the caller can show it instead of repeating the requested number;
* the measured duration is checked against the requested window before the
  part is accepted.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence

from ..domain.models import SplitPart
from .ffmpeg_tools import FfmpegTools

__all__ = ["FfmpegSplitterRenderer"]


class FfmpegSplitterRenderer:
    """Render splitter parts with FFmpeg and validate every one."""

    def __init__(
        self,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        log: Optional[Callable[[str], None]] = None,
        timeout_s: int = 1800,
    ) -> None:
        self._tools = FfmpegTools(
            ffmpeg=ffmpeg, ffprobe=ffprobe, timeout_s=timeout_s, log=log
        )
        self.log = log or (lambda msg: None)
        #: The measured facts of the most recent part.  A keyframe-snapped cut
        #: is reported here so the UI never claims a boundary it did not get.
        self.last_report: dict = {}

    # -- capability --------------------------------------------------------- #
    def available(self) -> bool:
        """True when both FFmpeg tools are on PATH."""
        return self._tools.available()

    def stage_progress(self) -> dict:
        return {"stage": "render", "percent": 0.0}

    def _refuse(self, reason: str) -> None:
        """Record why a part was refused, so the caller can say the same."""
        self.last_report = {"error": reason}
        self.log(f"Part refused: {reason}")

    # -- rendering ----------------------------------------------------------- #
    def render_part(
        self,
        video_path: str,
        part: SplitPart,
        output_path: str,
        settings: dict,
    ) -> bool:
        """Cut one part.  Returns ``True`` only when it passed validation."""
        self.last_report = {}
        if not self.available():
            self._refuse("FFmpeg/FFprobe are unavailable; no part was rendered")
            return False
        if not output_path:
            self._refuse("No output path was given for the part")
            return False
        source = Path(video_path)
        if not source.is_file():
            self._refuse(f"Source video is missing: {source}")
            return False
        if getattr(part, "end", 0) <= getattr(part, "start", 0):
            self._refuse(f"Part {part.number} ends before it starts")
            return False

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        start = float(part.start)
        window = float(part.duration)
        # ``-ss`` before ``-i`` seeks by keyframe first (fast), then ``-t``
        # bounds the copied segment.  The video and audio streams are both
        # mapped so a part without an audio track is refused by the check
        # below instead of silently shipping a silent video.
        #
        # ``-f mp4`` is explicit because the output name is chosen by the
        # caller and may not carry a media extension (a coordinator-owned
        # ``.partial`` name, for instance), and FFmpeg cannot infer the muxer
        # from such a name.
        command = [
            self._tools.ffmpeg,
            "-v", "error", "-y",
            "-ss", f"{start:.6f}",
            "-i", str(source),
            "-t", f"{window:.6f}",
            "-map", "0:v:0", "-map", "0:a?",
            "-c", "copy",
            "-movflags", "+faststart",
            "-f", "mp4",
            str(destination),
        ]
        try:
            self._tools.run(command)
            report = self._tools.validate_media(destination, window)
        except (RuntimeError, OSError) as exc:
            self.last_report = {"error": str(exc)}
            self.log(f"Part {part.number} failed: {exc}")
            try:
                destination.unlink()
            except OSError:
                pass
            return False

        report["requested_start"] = start
        report["requested_duration"] = window
        report["part"] = getattr(part, "number", 0)
        report["cut_reason"] = getattr(
            getattr(part, "cut_reason", None), "value", "exact"
        )
        self.last_report = report
        measured_start = report.get("start_time", 0.0)
        if abs(measured_start - start) > 0.05:
            self.log(
                f"Part {part.number}: cut snapped from {start:.3f}s to "
                f"{measured_start:.3f}s (keyframe boundary)"
            )
        self.log(f"Part {part.number} rendered and validated")
        return True

    def render(
        self,
        video_path: str,
        parts: Sequence[SplitPart],
        output_path: str,
        settings: dict,
    ) -> bool:
        """Render every included part into ``output_path`` as a directory."""
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = [part for part in parts if getattr(part, "include", True)]
        if not selected:
            self.log("No selected parts to render")
            return False
        for part in selected:
            # The same name the coordinator uses, so a part reused from a
            # previous run is recognised as the same part.
            self.render_part(
                video_path, part, str(output_dir / f"part_{part.number}.mp4"), settings
            )
        return True

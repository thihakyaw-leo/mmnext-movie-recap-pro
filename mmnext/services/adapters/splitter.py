"""Splitter planner and renderer adapters.

The planner is pure domain arithmetic and lives here.  The renderer shells out
to FFmpeg, so the REAL one lives in the infrastructure layer next to the other
runtime render adapters; it is re-exported here so callers keep a single
import site.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from ...domain.enums import CutReason
from ...domain.models import SplitPart
from ...infrastructure.splitter_render import FfmpegSplitterRenderer
from ..protocols import SplitterService

__all__ = [
    "LegacySplitterPlanner",
    "DemoSplitterPlanner",
    "LegacySplitterRenderer",
    "DemoSplitterRenderer",
]

#: The real renderer, re-exported from the infrastructure layer.
LegacySplitterRenderer = FfmpegSplitterRenderer


class DemoSplitterPlanner:
    def plan(
        self,
        duration: float,
        part_seconds: float,
        max_extra_wait: float = 5.0,
        pause_times: Optional[Sequence[float]] = None,
        smart_cut: bool = False,
    ) -> list[SplitPart]:
        if duration <= 0:
            raise ValueError("Source duration must be positive")
        if part_seconds <= 0:
            raise ValueError("Part duration must be positive")
        pause_times = list(pause_times or [])
        parts: list[SplitPart] = []
        start = 0.0
        number = 1
        while start < duration - 1e-9:
            target = min(start + part_seconds, duration)
            cut = target
            if smart_cut and pause_times and target < duration:
                candidates = [p for p in pause_times if target <= p <= target + max_extra_wait]
                if candidates:
                    cut = min(candidates)
            # A trailing remainder is absorbed into the part it follows so a
            # "short tail" part is never produced on its own.  The tail must
            # fit the wait *and* be shorter than a full part: without the
            # second condition a wait that is larger than ``part_seconds``
            # would swallow the whole remainder and turn every part into one.
            tail = duration - cut
            if cut < duration and 0 < tail <= max_extra_wait and tail < part_seconds and cut > start:
                cut = duration
            if cut <= start:
                cut = min(duration, start + part_seconds)
            if cut <= start:
                break
            reason = CutReason.END if cut >= duration - 1e-9 else CutReason.EXACT
            if smart_cut and cut != target and cut < duration:
                reason = CutReason.PAUSE
            parts.append(SplitPart(number=number, start=start, end=cut, cut_reason=reason))
            start = cut
            number += 1
        if not parts:
            parts.append(SplitPart(number=1, start=0.0, end=duration, cut_reason=CutReason.END))
        return parts


LegacySplitterPlanner = DemoSplitterPlanner


class DemoSplitterRenderer:
    """Deterministic offline renderer used by the test suite."""

    def available(self) -> bool:
        return True

    def stage_progress(self) -> dict:
        return {"stage": "render", "percent": 100.0}

    def render_part(self, video_path: str, part: SplitPart, output_path: str, settings: dict) -> bool:
        if not output_path:
            return False
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"demo splitter part {part.number}".encode("utf-8"))
        return True

    def render(self, video_path: str, parts: Sequence[SplitPart], output_path: str, settings: dict) -> bool:
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        selected = [part for part in parts if getattr(part, "include", True)]
        return all(
            self.render_part(video_path, part, str(output_dir / f"part_{part.number}.mp4"), settings)
            for part in selected
        )

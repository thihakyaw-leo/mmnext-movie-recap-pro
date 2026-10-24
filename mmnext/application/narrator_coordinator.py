"""Narrator plan coordinator.

Qt-free. Turns a verbatim transcript into atomic narration segments via the
narrator planning service, without touching the exact-dubbing working set.
Narrator rows remain a separate contract from Exact Dubbing rows.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..domain.models import NarrationSegment, TranscriptRow
from ..services.adapters.narrator import NarratorPlanningService

__all__ = ["NarratorPlanCoordinator"]


class NarratorPlanCoordinator:
    def __init__(
        self,
        planner: Optional[NarratorPlanningService] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._planner = planner or NarratorPlanningService()
        self._log = log or (lambda msg: None)

    def plan(
        self,
        transcript_rows: list[TranscriptRow],
        video_duration: float,
    ) -> list[NarrationSegment]:
        """Build narration segments covering the whole source timeline.

        Each segment starts with blank narration (filled later by editing or
        translation, both out of scope for this slice).
        """
        units = self._planner.plan_units(transcript_rows, video_duration)
        segments: list[NarrationSegment] = []
        for index, unit in enumerate(units):
            start = float(unit.get("start", 0.0))
            end = float(unit.get("end", start))
            segments.append(
                NarrationSegment(
                    segment_id=f"narr_{index + 1:05d}",
                    source_segment_ids=unit.get("source_segment_ids", [str(index)]),
                    source_text=str(unit.get("text", "")),
                    narration="",
                    video_start=start,
                    video_end=end,
                    order=index,
                    semantic_boundary=bool(unit.get("semantic_boundary", False)),
                    forced_boundary=bool(unit.get("forced_boundary", False)),
                    visual_reason=self._visual_reason(unit),
                )
            )
        self._log(f"Narrator plan: {len(segments)} segment(s) over {video_duration:.3f}s")
        return segments

    @staticmethod
    def _visual_reason(unit: dict) -> str:
        if unit.get("forced_boundary"):
            return "forced"
        if unit.get("semantic_boundary"):
            return "sentence"
        return ""

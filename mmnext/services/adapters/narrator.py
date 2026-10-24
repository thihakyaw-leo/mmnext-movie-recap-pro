"""Narrator planning adapter.

Wraps the legacy narrator planner behind a small application-facing service
so the UI and application layers never import legacy modules directly. The
heavy work (Gemini story context, translation, TTS, render) is intentionally
NOT invoked here; this adapter only turns a verbatim transcript into atomic
narration units (full coverage of the source timeline, no summarisation).
"""
from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional, List

from ...domain.models import NarrationSegment, TranscriptRow

__all__ = ["NarratorPlanningService"]

DEFAULT_LEGACY_ROOT = r"J:\recap-en-to-mm-main\recap-en-to-mm-main"
LEGACY_PLANNER_REL = "app/recap_planner.py"


def _load_legacy_planner(legacy_root: Optional[str]) -> Optional[ModuleType]:
    """Load the external legacy planner defensively.

    The legacy project lives outside this repository and is read-only. If it
    cannot be imported the service degrades to a deterministic fallback rather
    than crashing the application.
    """
    if not legacy_root:
        return None
    path = Path(legacy_root) / LEGACY_PLANNER_REL
    if not path.is_file():
        return None
    try:
        spec = spec_from_file_location("mmnext_legacy_recap_planner", str(path))
        if spec is None or spec.loader is None:
            return None
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


class NarratorPlanningService:
    def __init__(
        self,
        legacy_root: Optional[str] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.legacy_root = legacy_root
        self._planner = _load_legacy_planner(legacy_root)
        self.log = log or (lambda msg: None)

    def plan_available(self) -> bool:
        """True when the external legacy planner module loaded successfully."""
        return self._planner is not None

    def stage_progress(self) -> dict:
        return {"stage": "idle", "percent": 0.0, "message": "Narrator planning not started"}

    # -- core --------------------------------------------------------------- #
    def plan_units(
        self, transcript_rows: List[TranscriptRow], video_duration: float
    ) -> List[dict]:
        """Turn verbatim transcript rows into atomic narration units.

        Each unit carries ``video_start``/``video_end`` (full coverage of the
        source timeline), the source text and boundary metadata. Falls back to
        one unit per transcript row when the legacy planner is unavailable.
        Never touches exact-dubbing rows.
        """
        duration = max(0.0, float(video_duration or 0.0))
        if self._planner is not None:
            try:
                units = self._plan_with_legacy(transcript_rows, duration)
                if units:
                    return units
            except Exception as exc:  # noqa: BLE001 - legacy is external/untrusted
                self.log(f"Legacy planner unavailable, using fallback: {exc}")
        return self._plan_fallback(transcript_rows, duration)

    def _plan_with_legacy(self, transcript_rows: List[TranscriptRow], duration: float) -> List[dict]:
        planner = self._planner
        segments = []
        for index, row in enumerate(transcript_rows):
            segments.append({
                "id": index,
                "start": float(row.start),
                "end": float(row.end),
                "text": row.text,
                "words": [{
                    "text": row.text,
                    "start": float(row.start),
                    "end": float(row.end),
                    "source_transcript_id": index,
                }],
            })
        transcript = {"segments": segments}
        units = planner.atomicize_timestamp_segments(transcript)
        units = planner.assign_full_coverage_boundaries(units, duration)
        out: List[dict] = []
        for unit in units:
            out.append({
                "start": float(unit.get("video_start", unit.get("speech_start", 0.0))),
                "end": float(unit.get("video_end", unit.get("speech_end", 0.0))),
                "text": str(unit.get("source_text", "")),
                "semantic_boundary": bool(unit.get("semantic_boundary", False)),
                "forced_boundary": bool(unit.get("forced_boundary", False)),
                "source_segment_ids": [
                    str(x)
                    for x in (unit.get("source_transcript_ids")
                              or [unit.get("source_transcript_id", 0)])
                ],
            })
        return out

    def _plan_fallback(self, transcript_rows: List[TranscriptRow], duration: float) -> List[dict]:
        out: List[dict] = []
        n = len(transcript_rows)
        for index, row in enumerate(transcript_rows):
            start = float(row.start)
            end = float(row.end)
            if index + 1 < n:
                end = min(end, float(transcript_rows[index + 1].start))
            out.append({
                "start": start,
                "end": max(end, start + 0.001),
                "text": row.text,
                "semantic_boundary": False,
                "forced_boundary": False,
                "source_segment_ids": [str(index)],
            })
        # Full coverage: extend the final unit to the video duration.
        if out and duration > out[-1]["end"]:
            out[-1]["end"] = duration
        return out

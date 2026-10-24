"""Common-editing application service.

Non-destructive trim, overlay and export orchestration for Common Editing mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from ..domain.enums import AppMode, FrameFill, OutputRatio
from ..domain.models import Overlay, ProjectSession


class CommonEditingService:
    def __init__(self, exporter=None):
        self.exporter = exporter

    def set_trim(self, session: ProjectSession, start: float, end: float) -> None:
        if start < 0 or end < start:
            raise ValueError("Invalid trim range")
        session.trim_start = float(start)
        session.trim_end = float(end)

    def add_overlay(self, session: ProjectSession, overlay: Overlay) -> None:
        session.overlays.append(overlay)

    def remove_overlay(self, session: ProjectSession, index: int) -> None:
        if 0 <= index < len(session.overlays):
            del session.overlays[index]

    def set_ratio(self, session: ProjectSession, ratio: OutputRatio) -> None:
        session.output_ratio = ratio

    def set_fill(self, session: ProjectSession, fill: FrameFill) -> None:
        session.frame_fill = fill

    def validate(self, session: ProjectSession) -> list[str]:
        issues = []
        if session.trim_end and session.trim_end < session.trim_start:
            issues.append("trim_end must be >= trim_start")
        for overlay in session.overlays:
            if overlay.end < overlay.start:
                issues.append(f"overlay {overlay.kind.value} has invalid timing")
        if session.output_ratio is None:
            issues.append("output ratio is required")
        return issues

    def export(self, video_path: str, session: ProjectSession, output_path: str, settings: Optional[dict] = None) -> bool:
        if self.exporter is None:
            return False
        if self.validate(session):
            return False
        return bool(self.exporter.export(video_path, session, output_path, settings or {}))

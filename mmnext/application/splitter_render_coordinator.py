"""Splitter render coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import Callable, Optional, Sequence

from ..domain.enums import Stage
from ..domain.events import ProgressEvent
from ..domain.models import SplitPart
from ..domain.paths import partial_path_for
from ..services.adapters.splitter import DemoSplitterPlanner, DemoSplitterRenderer

__all__ = ["SplitterRenderResult", "SplitterRenderCoordinator"]


@dataclass(slots=True)
class SplitterRenderResult:
    ok: bool = False
    stopped: bool = False
    output_paths: list[str] = field(default_factory=list)
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    is_demo: bool = True


class SplitterRenderCoordinator:
    def __init__(self, planner=None, renderer=None, is_demo=True, log=None):
        self.planner = planner or DemoSplitterPlanner()
        self.renderer = renderer
        self.is_demo = is_demo
        self.log = log or (lambda msg: None)
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    @property
    def stop_requested(self):
        return self._stop_requested

    def reset(self):
        self._stop_requested = False

    @staticmethod
    def _emit(sink, percent, stage, message):
        if sink is not None:
            sink(ProgressEvent(percent=percent, stage=stage, message=message))

    @staticmethod
    def _fingerprint(video_path, part, settings):
        return (
            f"{video_path}|{part.number}|{part.start}|{part.end}|"
            f"{settings.get('ratio')}|{settings.get('fill')}|{settings.get('text')}"
        )

    def run(self, parts, video_path, output_dir, settings=None, sink=None):
        settings = settings or {}
        if self._stop_requested:
            return SplitterRenderResult(stopped=True, message="Stopped before start")
        selected = [part for part in parts if getattr(part, "include", True)]
        if not selected:
            return SplitterRenderResult(message="No selected parts to render")
        for part in selected:
            if getattr(part, "end", 0) <= getattr(part, "start", 0):
                return SplitterRenderResult(message=f"Part {part.number} ends before it starts")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        completed = []
        warnings = []
        total = len(selected)
        for index, part in enumerate(selected):
            if self._stop_requested:
                return SplitterRenderResult(
                    is_demo=self.is_demo,
                    stopped=True,
                    output_paths=completed,
                    warnings=warnings,
                    message="Stopped during render",
                )
            output_path = output_dir / f"part_{part.number}.mp4"
            fingerprint_path = output_path.with_suffix(output_path.suffix + ".fingerprint")
            fingerprint = self._fingerprint(video_path, part, settings)
            if output_path.is_file() and fingerprint_path.is_file() and fingerprint_path.read_text(encoding="utf-8").strip() == fingerprint:
                completed.append(str(output_path))
                warnings.append(f"Part {part.number}: reused existing output")
                self.log(warnings[-1])
                self._emit(sink, (index + 1) / total * 100.0, Stage.RENDER, f"Reused part {index + 1}/{total}")
                continue
            partial = partial_path_for(output_path)
            rendered = self.renderer.render_part(video_path, part, str(partial), settings) if self.renderer else False
            if not rendered or not partial.is_file() or partial.stat().st_size <= 0:
                # A REAL failure keeps its reason: the renderer reports why it
                # refused the part instead of the result collapsing to a bare
                # "render failed".
                reason = str(getattr(self.renderer, "error", "") or "").strip()
                if not reason:
                    report = dict(getattr(self.renderer, "last_report", {}) or {})
                    reason = str(report.get("error", "") or "").strip()
                if not reason:
                    reason = "the renderer did not produce a validated output"
                return SplitterRenderResult(
                    is_demo=self.is_demo,
                    output_paths=completed,
                    warnings=warnings,
                    message=f"Render failed for part {part.number}: {reason}",
                )
            report = dict(getattr(self.renderer, "last_report", {}) or {})
            requested = float(report.get("requested_start", part.start))
            measured = report.get("start_time")
            if measured is not None and abs(float(measured) - requested) > 0.05:
                warnings.append(
                    f"Part {part.number}: cut snapped from {requested:.3f}s to "
                    f"{float(measured):.3f}s (keyframe boundary)"
                )
            os.replace(partial, output_path)
            fingerprint_path.write_text(fingerprint, encoding="utf-8")
            completed.append(str(output_path))
            self._emit(sink, (index + 1) / total * 100.0, Stage.RENDER, f"Rendered part {index + 1}/{total}")
        self._emit(sink, 100.0, Stage.RENDER, "Splitter render complete")
        return SplitterRenderResult(
            is_demo=self.is_demo,
            ok=True,
            output_paths=completed,
            warnings=warnings,
            message="Render complete",
        )

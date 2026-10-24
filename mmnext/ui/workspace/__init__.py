"""The production workspace."""

from __future__ import annotations

from .inspector import Inspector
from .mode_switcher import ModeSwitcher
from .preview import PreviewPanel
from .segment_table import SegmentTable
from .timeline import Timeline
from .workspace_screen import WorkspaceScreen

__all__ = [
    "ModeSwitcher",
    "PreviewPanel",
    "SegmentTable",
    "Timeline",
    "Inspector",
    "WorkspaceScreen",
]

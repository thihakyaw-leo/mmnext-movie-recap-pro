"""Narrator Mode control panel.

Narrator Mode works on a *summarised* narration track: rows may be merged,
re-ordered and rewritten. The panel exposes the narrator-specific actions
and never touches the exact-dubbing rows.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....domain.models import NarrationSegment
from ...theme.palette import Palette
from ...widgets.badge import StateBadge

__all__ = ["NarratorPanel"]


class NarratorPanel(QWidget):
    """Actions and counters for Narrator Mode."""

    regenerateRequested = Signal()
    translateRequested = Signal()
    saveRequested = Signal()
    validateRequested = Signal()
    pipelineRequested = Signal()
    pipelineStopRequested = Signal()
    openOutputRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title = QLabel("NARRATOR TRACK")
        self.title.setProperty("role", "sectionTitle")

        self.segment_count = QLabel("0 segments")
        self.segment_count.setProperty("role", "muted")

        self.dirty_badge = StateBadge("clean", Palette.SUCCESS)
        self.dirty_badge.setToolTip(
            "Unsaved narration edits. Save before leaving the mode."
        )

        self.translate_button = QPushButton("Translate to Myanmar")
        self.translate_button.setProperty("variant", "ghost")
        self.translate_button.setToolTip(
            "Simulated in milestone 1 - no translation service is called."
        )
        self.translate_button.clicked.connect(self.translateRequested)

        self.regenerate_button = QPushButton("Regenerate summary")
        self.regenerate_button.setProperty("variant", "ghost")
        self.regenerate_button.setToolTip(
            "Simulated in milestone 1 - the legacy planner is not wired yet."
        )
        self.regenerate_button.clicked.connect(self.regenerateRequested)

        self.validate_button = QPushButton("Validate")
        self.validate_button.setProperty("variant", "ghost")
        self.validate_button.clicked.connect(self.validateRequested)

        self.save_button = QPushButton("Save narration")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self.saveRequested)

        self.pipeline_button = QPushButton("Run narrator pipeline (DEMO)")
        self.pipeline_button.setProperty("variant", "primary")
        self.pipeline_button.setToolTip(
            "Runs plan -> translate -> synthesise -> Smart Sync render. "
            "The current adapters are DEMO, so the output is simulated."
        )
        self.pipeline_button.clicked.connect(self.pipelineRequested)

        self.pipeline_stop_button = QPushButton("Stop pipeline")
        self.pipeline_stop_button.setProperty("variant", "ghost")
        self.pipeline_stop_button.setEnabled(False)
        self.pipeline_stop_button.clicked.connect(self.pipelineStopRequested)

        self.open_output_button = QPushButton("Open output folder")
        self.open_output_button.setProperty("variant", "ghost")
        self.open_output_button.clicked.connect(self.openOutputRequested)

        layout.addWidget(self.title)
        layout.addWidget(self.segment_count)
        layout.addWidget(self.dirty_badge)
        layout.addStretch(1)
        layout.addWidget(self.translate_button)
        layout.addWidget(self.regenerate_button)
        layout.addWidget(self.validate_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.pipeline_button)
        layout.addWidget(self.pipeline_stop_button)
        layout.addWidget(self.open_output_button)
        root.addLayout(layout)

        self.pipeline_progress = QProgressBar()
        self.pipeline_progress.setValue(0)
        self.pipeline_progress.setVisible(False)
        root.addWidget(self.pipeline_progress)

        self.pipeline_status = QLabel("No narrator pipeline run yet.")
        self.pipeline_status.setProperty("role", "muted")
        self.pipeline_status.setWordWrap(True)
        root.addWidget(self.pipeline_status)

    # -- state --------------------------------------------------------------- #
    def set_segments(self, segments: list[NarrationSegment]) -> None:
        dirty = sum(1 for segment in segments if segment.dirty)
        chars = sum(len(segment.narration) for segment in segments)
        self.segment_count.setText(
            f"{len(segments)} segments  |  {chars} Myanmar characters"
        )
        if dirty:
            self.dirty_badge.set_state(f"{dirty} unsaved", Palette.WARNING)
        else:
            self.dirty_badge.set_state("clean", Palette.SUCCESS)
        self.save_button.setEnabled(dirty > 0)

    def set_pipeline_state(self, state: str, message: str) -> None:
        """Reflect the pipeline lifecycle in the panel."""
        running = state == "running"
        self.pipeline_button.setEnabled(not running)
        self.pipeline_stop_button.setEnabled(running)
        self.pipeline_progress.setVisible(running or state == "stopping")
        if message:
            self.pipeline_status.setText(message)

    def set_pipeline_progress(self, percent: float) -> None:
        self.pipeline_progress.setValue(int(max(0.0, min(100.0, percent))))

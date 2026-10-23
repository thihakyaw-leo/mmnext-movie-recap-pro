"""Splitter Mode control panel.

The splitter plans the output parts. The legacy planner used the cut
reasons ``exact``, ``pause``, ``breath``, ``quietest`` and ``end``; the
panel shows the same vocabulary so the eventual pipeline keeps the same
contract.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....domain.models import SplitPart
from ...theme.palette import Palette
from ...widgets.badge import StateBadge

__all__ = ["SplitterPanel"]


class SplitterPanel(QWidget):
    """Actions and counters for Splitter Mode."""

    planRequested = Signal()
    renderRequested = Signal()
    selectAllRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title = QLabel("OUTPUT PARTS")
        self.title.setProperty("role", "sectionTitle")

        self.part_count = QLabel("0 parts")
        self.part_count.setProperty("role", "muted")

        self.total_label = QLabel("0s")
        self.total_label.setProperty("role", "mono")

        self.include_badge = StateBadge("0 selected", Palette.ACCENT)

        self.plan_button = QPushButton("Re-plan parts")
        self.plan_button.setProperty("variant", "ghost")
        self.plan_button.setToolTip(
            "Simulated in milestone 1 - the legacy planner is not wired yet."
        )
        self.plan_button.clicked.connect(self.planRequested)

        self.select_button = QPushButton("Select all")
        self.select_button.setProperty("variant", "ghost")
        self.select_button.clicked.connect(self.selectAllRequested)

        self.render_button = QPushButton("Render parts")
        self.render_button.setProperty("variant", "primary")
        self.render_button.setToolTip(
            "Simulated in milestone 1 - FFmpeg is not called."
        )
        self.render_button.clicked.connect(self.renderRequested)

        layout.addWidget(self.title)
        layout.addWidget(self.part_count)
        layout.addWidget(self.total_label)
        layout.addWidget(self.include_badge)
        layout.addStretch(1)
        layout.addWidget(self.plan_button)
        layout.addWidget(self.select_button)
        layout.addWidget(self.render_button)

    # -- state --------------------------------------------------------------- #
    def set_parts(self, parts: list[SplitPart]) -> None:
        included = [part for part in parts if part.include]
        total = sum(part.duration for part in included)
        self.part_count.setText(f"{len(parts)} parts planned")
        self.total_label.setText(f"{total:.1f}s selected")
        self.include_badge.set_state(
            f"{len(included)} selected", Palette.ACCENT if included else Palette.NEUTRAL
        )
        self.render_button.setEnabled(bool(included))

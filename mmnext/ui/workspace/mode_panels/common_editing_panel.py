"""Common Video Editing control panel.

Holds the output settings that apply to every mode: aspect ratio, frame
fill and the output folder. The values mirror the legacy enums
(``16:9`` / ``9:16`` / ``1:1`` / ``Original`` and ``blur`` / ``black`` /
``crop``).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....domain.enums import FrameFill, OutputRatio
from ...theme.palette import Palette
from ...widgets.badge import StateBadge

__all__ = ["CommonEditingPanel"]


class CommonEditingPanel(QWidget):
    """Output settings for Common Video Editing."""

    outputFolderChanged = Signal(str)
    ratioChanged = Signal(str)
    fillChanged = Signal(str)
    addOverlayRequested = Signal()
    renderRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.title = QLabel("OUTPUT")
        self.title.setProperty("role", "sectionTitle")

        self.ratio_combo = QComboBox()
        for ratio in OutputRatio:
            self.ratio_combo.addItem(ratio.value)
        self.ratio_combo.setCurrentText(OutputRatio.ORIGINAL.value)
        self.ratio_combo.setToolTip("Output aspect ratio.")
        self.ratio_combo.currentTextChanged.connect(self.ratioChanged)

        self.fill_combo = QComboBox()
        for fill in FrameFill:
            self.fill_combo.addItem(fill.value)
        self.fill_combo.setCurrentText(FrameFill.BLUR.value)
        self.fill_combo.setToolTip("How the source is fitted to the output frame.")
        self.fill_combo.currentTextChanged.connect(self.fillChanged)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Output folder")
        self.folder_edit.setMinimumWidth(240)
        self.folder_edit.editingFinished.connect(self._emit_output_folder)

        self.overlay_button = QPushButton("Add overlay")
        self.overlay_button.setProperty("variant", "ghost")
        self.overlay_button.clicked.connect(self.addOverlayRequested)

        self.render_button = QPushButton("Render")
        self.render_button.setProperty("variant", "primary")
        self.render_button.setToolTip(
            "Simulated in milestone 1 - FFmpeg is not called."
        )
        self.render_button.clicked.connect(self.renderRequested)

        layout.addWidget(self.title)
        layout.addWidget(QLabel("Ratio"))
        layout.addWidget(self.ratio_combo)
        layout.addWidget(QLabel("Fill"))
        layout.addWidget(self.fill_combo)
        layout.addWidget(self.folder_edit, 1)
        layout.addWidget(self.overlay_button)
        layout.addWidget(self.render_button)

    # -- state --------------------------------------------------------------- #
    def _emit_output_folder(self) -> None:
        """Bound slot (never a lambda) so no ``self`` cycle is created."""
        self.outputFolderChanged.emit(self.folder_edit.text())

    def set_output_folder(self, path: str) -> None:
        if path and self.folder_edit.text() != path:
            self.folder_edit.setText(path)

    def set_overlay_count(self, count: int) -> None:
        self.overlay_button.setText(f"Add overlay ({count})")

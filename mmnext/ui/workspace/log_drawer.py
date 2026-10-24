"""The bottom log / progress drawer.

A collapsible panel at the bottom of the main window with two tabs:

* **Log** - the structured log stream.
* **Progress** - the current job's stage, percent and message.

The drawer is collapsed by default so the workspace keeps the vertical space
for the table and the timeline.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import LogLevel, Stage
from ...domain.models import Job, LogEntry
from ..theme.palette import SEVERITY_COLORS, Palette
from ..widgets.badge import StateBadge
from ..widgets.timecode import format_timecode

__all__ = ["LogDrawer"]

_LEVEL_COLORS = {
    LogLevel.DEBUG: Palette.TEXT_FAINT,
    LogLevel.INFO: Palette.TEXT_MUTED,
    LogLevel.WARNING: Palette.WARNING,
    LogLevel.ERROR: Palette.DANGER,
    LogLevel.SUCCESS: Palette.SUCCESS,
}


class LogDrawer(QWidget):
    """The collapsible bottom drawer."""

    clearRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("logDrawer")
        self.setStyleSheet(
            f"""
            QWidget#logDrawer {{
                background: {Palette.BG_PANEL};
                border-top: 1px solid {Palette.BORDER};
            }}
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- header ------------------------------------------------------------ #
        header = QHBoxLayout()
        header.setContentsMargins(14, 6, 14, 6)
        header.setSpacing(10)

        self.toggle_button = QPushButton("▾  Activity")
        self.toggle_button.setProperty("variant", "ghost")
        self.toggle_button.setCursor(Qt.PointingHandCursor)
        self.toggle_button.clicked.connect(self.toggle)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("role", "faint")

        self.clear_button = QPushButton("Clear")
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.clicked.connect(self.clearRequested)

        header.addWidget(self.toggle_button)
        header.addWidget(self.status_label)
        header.addStretch(1)
        header.addWidget(self.clear_button)
        root.addLayout(header)

        # -- body -------------------------------------------------------------- #
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {Palette.BORDER};
                background: {Palette.BG_TIMELINE};
            }}
            """
        )

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setProperty("role", "log")
        self.log_view.setMaximumBlockCount(2000)
        self.tabs.addTab(self.log_view, "Log")

        progress_tab = QWidget()
        progress_layout = QVBoxLayout(progress_tab)
        progress_layout.setContentsMargins(14, 12, 14, 12)
        progress_layout.setSpacing(8)

        progress_header = QHBoxLayout()
        self.stage_label = QLabel("idle")
        self.stage_label.setProperty("role", "h3")
        self.state_badge = StateBadge("no job", Palette.NEUTRAL)
        self.percent_label = QLabel("0%")
        self.percent_label.setProperty("role", "mono")
        progress_header.addWidget(self.stage_label)
        progress_header.addWidget(self.state_badge)
        progress_header.addStretch(1)
        progress_header.addWidget(self.percent_label)
        progress_layout.addLayout(progress_header)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress)

        self.message_label = QLabel("No job is running.")
        self.message_label.setProperty("role", "muted")
        self.message_label.setWordWrap(True)
        progress_layout.addWidget(self.message_label)

        self.tabs.addTab(progress_tab, "Progress")
        root.addWidget(self.tabs)

        export_btn = QPushButton("Export logs")
        export_btn.setProperty("variant", "ghost")
        export_btn.clicked.connect(self._export_logs)
        root.addWidget(export_btn)

        self._expanded = False
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.tabs.setVisible(False)
        self.setFixedHeight(38)

    # -- expand / collapse ---------------------------------------------------- #
    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.tabs.setVisible(expanded)
        self.toggle_button.setText("▾  Activity" if expanded else "▸  Activity")
        self.setFixedHeight(240 if expanded else 38)

    @property
    def expanded(self) -> bool:
        return self._expanded

    # -- content --------------------------------------------------------------- #
    def append_log(self, entry: LogEntry) -> None:
        color = _LEVEL_COLORS.get(entry.level, Palette.TEXT_MUTED)
        self.log_view.appendHtml(
            f'<span style="color:{color}">{entry.display()}</span>'
        )

    def set_log_text(self, text: str) -> None:
        self.log_view.setPlainText(text)

    def show_job(self, job: Optional[Job]) -> None:
        if job is None:
            self.stage_label.setText("idle")
            self.state_badge.set_state("no job", Palette.NEUTRAL)
            self.progress.setValue(0)
            self.percent_label.setText("0%")
            self.message_label.setText("No job is running.")
            return
        self.stage_label.setText(job.progress.stage.value)
        self.progress.setValue(job.progress.percent_int)
        self.percent_label.setText(f"{job.progress.percent_int}%")
        self.message_label.setText(job.progress.message or job.job_id)
        color = SEVERITY_COLORS.get(
            "error" if job.state.value == "failed" else "info", Palette.INFO
        )
        self.state_badge.set_state(job.state.value.replace("_", " "), color)

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _export_logs(self) -> None:
        if self._context is None:
            return
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getSaveFileName(self, "Export logs", "mmnext-logs.json", "JSON Files (*.json)")
        if path:
            self._context.export_logs(path)

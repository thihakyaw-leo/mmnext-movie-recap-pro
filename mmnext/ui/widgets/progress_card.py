"""The download progress card.

Shows one queued download with a determinate progress bar, the byte counter,
the speed, the ETA and the four transport controls (pause, resume, stop,
retry). Button enablement is derived from the task state, so the card can
never offer an action the download service would reject.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import TaskState
from ...domain.models import DownloadItem
from ..theme.palette import TASK_STATE_COLORS, Palette
from .badge import StateBadge
from .timecode import format_duration

__all__ = ["DownloadProgressCard"]


class DownloadProgressCard(QFrame):
    """One row of the download queue."""

    pauseRequested = Signal(str)     # item_id
    resumeRequested = Signal(str)
    stopRequested = Signal(str)
    retryRequested = Signal(str)
    openRequested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background: {Palette.BG_CARD};
                border: 1px solid {Palette.BORDER};
                border-radius: 8px;
            }}
            QProgressBar {{
                background: {Palette.BG_INPUT};
                border: 1px solid {Palette.BORDER};
                border-radius: 5px;
                height: 8px;
                text-align: center;
                color: transparent;
            }}
            QProgressBar::chunk {{
                background: {Palette.ACCENT};
                border-radius: 4px;
            }}
            """
        )
        self._item_id = ""
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # -- title row ------------------------------------------------------ #
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        self.title_label = QLabel("Untitled")
        self.title_label.setProperty("role", "h3")
        self.title_label.setWordWrap(False)

        self.quality_label = QLabel("1080p")
        self.quality_label.setProperty("role", "faint")

        self.state_badge = StateBadge("queued", TASK_STATE_COLORS["queued"])

        title_row.addWidget(self.title_label)
        title_row.addWidget(self.quality_label)
        title_row.addStretch(1)
        title_row.addWidget(self.state_badge)
        root.addLayout(title_row)

        # -- progress ------------------------------------------------------ #
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        # -- metrics -------------------------------------------------------- #
        metrics = QGridLayout()
        metrics.setHorizontalSpacing(18)
        metrics.setVerticalSpacing(2)

        self.percent_label = QLabel("0%")
        self.percent_label.setProperty("role", "mono")
        self.size_label = QLabel("-")
        self.size_label.setProperty("role", "muted")
        self.speed_label = QLabel("-")
        self.speed_label.setProperty("role", "muted")
        self.eta_label = QLabel("-")
        self.eta_label.setProperty("role", "muted")
        self.message_label = QLabel("")
        self.message_label.setProperty("role", "faint")
        self.message_label.setWordWrap(True)

        metrics.addWidget(self.percent_label, 0, 0)
        metrics.addWidget(self.size_label, 0, 1)
        metrics.addWidget(self.speed_label, 0, 2)
        metrics.addWidget(self.eta_label, 0, 3)
        metrics.addWidget(self.message_label, 1, 0, 1, 4)
        root.addLayout(metrics)

        # -- actions -------------------------------------------------------- #
        actions = QHBoxLayout()
        actions.setSpacing(8)

        # NOTE: every connection below uses a *bound method*, never a
        # lambda. A lambda that captures ``self`` creates a reference
        # cycle (parent -> child widget -> connection -> lambda -> parent)
        # which keeps the widget alive past interpreter shutdown and makes
        # Qt abort during teardown. See ``tests/test_architecture_gates.py``.
        self.pause_button = QPushButton("Pause")
        self.pause_button.setProperty("variant", "ghost")
        self.pause_button.clicked.connect(self._emit_pause)

        self.resume_button = QPushButton("Resume")
        self.resume_button.setProperty("variant", "ghost")
        self.resume_button.clicked.connect(self._emit_resume)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("variant", "ghost")
        self.stop_button.clicked.connect(self._emit_stop)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setProperty("variant", "ghost")
        self.retry_button.clicked.connect(self._emit_retry)

        self.open_button = QPushButton("Open in workspace")
        self.open_button.setProperty("variant", "primary")
        self.open_button.clicked.connect(self._emit_open)

        for button in (
            self.pause_button,
            self.resume_button,
            self.stop_button,
            self.retry_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(self.open_button)
        root.addLayout(actions)

    # -- signal emitters ---------------------------------------------------- #
    # Bound methods, not lambdas: see the note in ``__init__``.

    def _emit_pause(self) -> None:
        self.pauseRequested.emit(self._item_id)

    def _emit_resume(self) -> None:
        self.resumeRequested.emit(self._item_id)

    def _emit_stop(self) -> None:
        self.stopRequested.emit(self._item_id)

    def _emit_retry(self) -> None:
        self.retryRequested.emit(self._item_id)

    def _emit_open(self) -> None:
        self.openRequested.emit(self._item_id)

    # -- data -------------------------------------------------------------- #
    def apply(self, item: DownloadItem) -> None:
        """Refresh the card from a download item snapshot."""
        self._item_id = item.item_id
        self.title_label.setText(item.title or item.url)
        self.quality_label.setText(item.quality_label)
        self.progress.setValue(int(round(item.percent)))
        self.percent_label.setText(f"{item.percent:.1f}%")

        total_mb = item.total_bytes / (1024 * 1024)
        done_mb = item.downloaded_bytes / (1024 * 1024)
        self.size_label.setText(f"{done_mb:.1f} / {total_mb:.1f} MB")

        if item.speed_bps > 0:
            mbps = item.speed_bps / (1024 * 1024)
            self.speed_label.setText(f"{mbps:.2f} MB/s")
        else:
            self.speed_label.setText("-")

        self.eta_label.setText(format_duration(item.eta_s))
        self.message_label.setText(item.error_message or "")

        color = TASK_STATE_COLORS.get(item.state.value, Palette.NEUTRAL)
        self.state_badge.set_state(item.state.value.replace("_", " "), color)
        self._update_buttons(item.state)

    def _update_buttons(self, state: TaskState) -> None:
        running = state in (TaskState.QUEUED, TaskState.RUNNING)
        self.pause_button.setEnabled(running)
        self.resume_button.setEnabled(state in (TaskState.PAUSED, TaskState.STOPPED))
        self.stop_button.setEnabled(
            state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED)
        )
        self.retry_button.setEnabled(
            state in (TaskState.FAILED, TaskState.STOPPED, TaskState.CANCELLED)
        )
        self.open_button.setEnabled(state is TaskState.COMPLETE)

"""Production jobs screen.

A table of every job the job manager knows about, with a truthful badge per
state. The allowed transitions come from the job manager, so the action
buttons can never offer an illegal move.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import JobState
from ...domain.models import Job
from ..navigation.nav_rail import NavTarget
from ..theme.palette import JOB_STATE_COLORS, Palette
from ..widgets.badge import StateBadge
from ..widgets.card import Card, CardHeader
from .base import BaseScreen, ScreenHeader

__all__ = ["JobsScreen"]

_COLUMNS = ("Job", "Mode", "State", "Progress", "Stage", "Updated", "Message")


class JobsScreen(BaseScreen):
    """The job list."""

    screen_key = NavTarget.JOBS

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.layout.addWidget(
            ScreenHeader(
                "Production jobs",
                "Every job the app tracks. States come from the job state "
                "machine - illegal transitions are refused, not hidden.",
            )
        )

        card = Card()
        header_row = CardHeader(
            "Jobs", "Select a row to see the actions it currently allows."
        )

        self.resume_button = QPushButton("Resume")
        self.resume_button.setProperty("variant", "ghost")
        self.resume_button.clicked.connect(self._resume_selected)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setProperty("variant", "ghost")
        self.cancel_button.clicked.connect(self._cancel_selected)

        self.retry_button = QPushButton("Retry")
        self.retry_button.setProperty("variant", "ghost")
        self.retry_button.clicked.connect(self._retry)

        self.open_transcript_button = QPushButton("Open transcript")
        self.open_transcript_button.setProperty("variant", "ghost")
        self.open_transcript_button.clicked.connect(self._open_transcript_selected)

        header_row.add_trailing(self.resume_button)
        header_row.add_trailing(self.cancel_button)
        header_row.add_trailing(self.retry_button)
        header_row.add_trailing(self.open_transcript_button)
        card.add(header_row)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(list(_COLUMNS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        card.add(self.table)

        self.detail_label = QLabel("No job selected.")
        self.detail_label.setProperty("role", "muted")
        self.detail_label.setWordWrap(True)
        card.add(self.detail_label)

        self.layout.addWidget(card)
        self.layout.addStretch(1)

        self._job_ids: list[str] = []

    # -- context ------------------------------------------------------------ #
    def on_bind(self, context) -> None:
        context.jobUpdated.connect(self._refresh)
        context.jobStateChanged.connect(self._on_job_state_changed)

    def _on_job_state_changed(self, *_args) -> None:
        """Bound slot for ``jobStateChanged`` (Job, JobState)."""
        self._refresh()

    def _resume_selected(self) -> None:
        self._transition(JobState.DOWNLOADING)

    def _cancel_selected(self) -> None:
        self._transition(JobState.CANCELLED)

    def on_activate(self) -> None:
        self._refresh()

    # -- rendering ---------------------------------------------------------- #
    def _refresh(self) -> None:
        if self._context is None:
            return
        jobs = self._context.all_jobs()
        self.table.setRowCount(len(jobs))
        self._job_ids = []
        for row, job in enumerate(jobs):
            self._job_ids.append(job.job_id)
            self._fill_row(row, job)
        self._on_selection_changed()

    def _fill_row(self, row: int, job: Job) -> None:
        values = (
            job.job_id,
            job.mode.display_name,
            job.state.value.replace("_", " "),
            f"{job.progress.percent_int}%",
            job.progress.stage.value,
            job.updated_at or "-",
            job.progress.message or job.error_message or "",
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 2:
                color = JOB_STATE_COLORS.get(job.state.value, Palette.NEUTRAL)
                item.setForeground(Qt.GlobalColor.transparent)
                item.setData(Qt.ItemDataRole.ForegroundRole, Qt.GlobalColor.transparent)
                item.setText("")
                item.setIcon(self._dot_icon(color))
            if column == 3:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.table.setItem(row, column, item)

    def _dot_icon(self, color: str):
        from PySide6.QtGui import QColor, QIcon, QPixmap

        pixmap = QPixmap(10, 10)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = None
        try:
            from PySide6.QtGui import QPainter

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(0, 0, 10, 10)
        finally:
            if painter is not None:
                painter.end()
        return QIcon(pixmap)

    # -- selection ---------------------------------------------------------- #
    def _on_selection_changed(self) -> None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            self.detail_label.setText("No job selected.")
            self.resume_button.setEnabled(False)
            self.cancel_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self.open_transcript_button.setEnabled(False)
            return

        index = rows[0].row()
        if index < 0 or index >= len(self._job_ids):
            return
        job = self._context.jobs.get(self._job_ids[index])

        self.detail_label.setText(
            f"{job.job_id} - {job.mode.display_name} - {job.state.value} - "
            f"{job.progress.message or job.error_message or 'no message'}"
        )

        manager = self._context.jobs
        self.resume_button.setEnabled(
            manager.can_transition(job.job_id, JobState.DOWNLOADING)
            or manager.can_transition(job.job_id, JobState.PREPARING)
        )
        self.cancel_button.setEnabled(
            manager.can_transition(job.job_id, JobState.CANCELLED)
        )
        self.retry_button.setEnabled(
            manager.can_transition(job.job_id, JobState.DOWNLOAD_QUEUED)
            or manager.can_transition(job.job_id, JobState.PREPARING)
        )
        self.open_transcript_button.setEnabled(
            job.state == JobState.COMPLETE and not job.is_demo
        )

    def _transition(self, new_state: JobState) -> None:
        if self._context is None:
            return
        job = self._selected_job()
        if job is None:
            return
        try:
            self._context.transition_job(job.job_id, new_state)
        except Exception as exc:
            self.detail_label.setText(f"Refused: {exc}")

    def _retry(self) -> None:
        if self._context is None:
            return
        job = self._selected_job()
        if job is None:
            return
        try:
            self._context.transition_job(job.job_id, JobState.DOWNLOAD_QUEUED)
        except Exception as exc:
            self.detail_label.setText(f"Refused: {exc}")

    def _open_transcript_selected(self) -> None:
        if self._context is None:
            return
        job = self._selected_job()
        if job is None:
            return
        if job.source is None:
            self.detail_label.setText("Job has no source; cannot open transcript")
            return
        try:
            self._context.open_transcript_from_job(job.job_id, job.source.location)
        except Exception as exc:
            self.detail_label.setText(f"Open failed: {exc}")

    def _selected_job(self) -> Optional[Job]:
        if self._context is None or self.table.selectionModel() is None:
            return None
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        index = rows[0].row()
        if index < 0 or index >= len(self._job_ids):
            return None
        return self._context.jobs.get(self._job_ids[index])

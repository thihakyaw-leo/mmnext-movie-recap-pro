"""The production workspace.

Layout (Subtitle-Edit inspired, adapted to the four MMNext modes):

    +--------------------------------------------------------------+
    |  title + mode switcher                                        |
    |  mode control panel                                           |
    |  +------------------------------------------+------------------+
    |  |  video preview (placeholder player)    |  inspector       |
    |  |  working-set table                      |  (per mode)      |
    |  |  timeline with playhead                 |                  |
    |  +------------------------------------------+------------------+
    +--------------------------------------------------------------+

The workspace never touches a controller directly - it talks to the
:class:`~mmnext.ui.app_context.AppContext` and its signals.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import AppMode
from ...domain.models import TimelineMarker
from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader
from ..widgets.confirm import confirm_before_discard
from ..models.transcript_model import TranscriptTableModel
from .inspector import Inspector
from .mode_panels.common_editing_panel import CommonEditingPanel
from .mode_panels.exact_dubbing_panel import ExactDubbingPanel
from .mode_panels.narrator_panel import NarratorPanel
from .mode_panels.splitter_panel import SplitterPanel
from .mode_switcher import ModeSwitcher
from .preview import PreviewPanel
from .segment_table import SegmentTable
from .timeline import Timeline

__all__ = ["WorkspaceScreen"]


class WorkspaceScreen(QWidget):
    """The production workspace screen."""

    screen_key = NavTarget.WORKSPACE

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {Palette.BG_APP};")

        self._context = None
        self._mode = AppMode.COMMON_EDITING
        self._suppress_selection = False

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # -- header ------------------------------------------------------------ #
        header = QHBoxLayout()
        header.setSpacing(14)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("Production workspace")
        title.setProperty("role", "h1")
        self.subtitle = QLabel("No source loaded.")
        self.subtitle.setProperty("role", "muted")
        titles.addWidget(title)
        titles.addWidget(self.subtitle)
        header.addLayout(titles)
        header.addStretch(1)

        self.mode_switcher = ModeSwitcher()
        self.mode_switcher.modeChanged.connect(self._on_mode_switched)
        header.addWidget(self.mode_switcher)
        root.addLayout(header)

        transcript_controls = QHBoxLayout()
        self.transcribe_button = QPushButton("Transcribe local video… (REAL)")
        self.transcribe_button.clicked.connect(self._start_local_transcript)
        self.transcript_stop = QPushButton("Stop transcription")
        self.transcript_stop.setEnabled(False)
        self.transcript_stop.clicked.connect(self._stop_transcript)
        self.auto_language = QCheckBox("Auto-detect language")
        self.auto_language.setChecked(True)
        self.language_edit = QLineEdit("en")
        self.language_edit.setMaximumWidth(70)
        self.language_edit.setToolTip("Whisper language code, e.g. en, my, fr; ignored with auto-detect")
        for widget in (self.transcribe_button, self.auto_language, self.language_edit, self.transcript_stop):
            transcript_controls.addWidget(widget)
        root.addLayout(transcript_controls)
        self.transcript_status = QLabel("DEMO source transcript; no real transcription running.")
        self.transcript_status.setWordWrap(True)
        root.addWidget(self.transcript_status)
        self.transcript_progress = QProgressBar()
        self.transcript_progress.setValue(0)
        root.addWidget(self.transcript_progress)

        # -- mode control panel ------------------------------------------------ #
        self.mode_panel_host = QWidget()
        self.mode_panel_layout = QVBoxLayout(self.mode_panel_host)
        self.mode_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.mode_panel_layout.setSpacing(0)

        self.narrator_panel = NarratorPanel()
        self.exact_panel = ExactDubbingPanel()
        self.splitter_panel = SplitterPanel()
        self.common_panel = CommonEditingPanel()
        for panel in (
            self.narrator_panel,
            self.exact_panel,
            self.splitter_panel,
            self.common_panel,
        ):
            self.mode_panel_layout.addWidget(panel)
            panel.setVisible(False)
        root.addWidget(self.mode_panel_host)

        # -- main split ---------------------------------------------------------- #
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        left = QWidget()
        left.setStyleSheet(f"background: {Palette.BG_APP};")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # preview -------------------------------------------------------------
        self.preview_card = Card()
        preview_header = CardHeader(
            "Preview",
            "The mpv adapter is optional - a placeholder player keeps the "
            "workspace usable without it.",
        )
        self.preview_card.add(preview_header)
        self.preview = PreviewPanel()
        self.preview_card.add(self.preview)
        left_layout.addWidget(self.preview_card, 3)

        self.transcript_model = TranscriptTableModel(self)
        self.transcript_view = QTableView()
        self.transcript_view.setModel(self.transcript_model)
        self.transcript_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.transcript_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.transcript_view.horizontalHeader().setStretchLastSection(True)
        self.transcript_view.selectionModel().currentRowChanged.connect(self._on_transcript_selected)
        left_layout.addWidget(QLabel("Verbatim source transcript — read-only; not a narrator recap"))
        left_layout.addWidget(self.transcript_view, 2)

        # working set ----------------------------------------------------------
        self.table_card = Card()
        self.table_header = CardHeader("Working set", "")
        self.table_card.add(self.table_header)
        self.table = SegmentTable()
        self.table.rowSelected.connect(self._on_row_selected)
        self.table.selectionCleared.connect(self._on_selection_cleared)
        self.table.narrationEdited.connect(self._on_narration_edited)
        self.table.burmeseEdited.connect(self._on_burmese_edited)
        self.table_card.add(self.table)
        left_layout.addWidget(self.table_card, 4)

        # timeline --------------------------------------------------------------
        self.timeline_card = Card()
        timeline_header = CardHeader("Timeline", "Click or drag to move the playhead.")
        self.timeline_card.add(timeline_header)
        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self._on_timeline_seek)
        self.timeline_card.add(self.timeline)
        left_layout.addWidget(self.timeline_card, 0)

        self.splitter.addWidget(left)

        self.inspector = Inspector()
        self.inspector.narrationChanged.connect(self._on_inspector_text)
        self.inspector.genderChanged.connect(self._on_gender_changed)
        self.inspector.saveRequested.connect(self._on_save_requested)
        self.inspector.validateRequested.connect(self._on_validate_requested)
        self.splitter.addWidget(self.inspector)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([1000, 330])

        root.addWidget(self.splitter, 1)

        # -- mode panel wiring --------------------------------------------------- #
        self.narrator_panel.saveRequested.connect(self._on_save_requested)
        self.narrator_panel.validateRequested.connect(self._on_validate_requested)
        self.exact_panel.saveRequested.connect(self._on_save_requested)
        self.exact_panel.validateRequested.connect(self._on_validate_requested)

        self._apply_mode_visibility()

    # -- binding ---------------------------------------------------------------- #
    def bind(self, context) -> None:
        self._context = context
        context.sessionChanged.connect(self._reload)
        context.metadataChanged.connect(self._on_metadata_changed)
        context.sourceChanged.connect(self._on_source_changed)
        context.modeChanged.connect(self._on_context_mode_changed)
        context.selection.rowChanged.connect(self._on_context_selection)
        context.selection.selectionCleared.connect(self._on_selection_cleared)
        context.validationChanged.connect(self._on_validation_changed)
        context.transcriptProgress.connect(self._on_transcript_progress)
        context.transcriptStateChanged.connect(self._on_transcript_state)
        self._reload()

    def on_activate(self) -> None:
        self._reload()

    def _on_source_changed(self, _source) -> None:
        """Bound slot for ``sourceChanged`` (VideoSource)."""
        self._reload()

    @property
    def context(self):
        """The bound :class:`AppContext` (``None`` before :meth:`bind`)."""
        return self._context

    @property
    def mode(self) -> AppMode:
        """The mode currently displayed by the workspace."""
        return self._mode

    # -- data ------------------------------------------------------------------- #
    def _reload(self) -> None:
        context = self._context
        if context is None:
            return
        session = context.session
        if session is None:
            self.subtitle.setText("No source loaded.")
            self.transcript_model.set_rows([])
            self.table.set_narration_segments([])
            self.table.set_exact_rows([])
            self.table.set_parts([])
            self.table.set_overlays([])
            self.inspector.clear()
            self.preview.set_caption("")
            self.preview.set_source("", 0.0)
            self.timeline.set_duration(0.0)
            self.timeline.set_markers([])
            return

        source = session.source
        name = source.name if source is not None else "Untitled"
        duration = session.total_duration()
        self.subtitle.setText(
            f"{name}  |  {len(session.narration_segments)} narration segments  |  "
            f"{len(session.exact_dubbing_rows)} exact rows  |  "
            f"{len(session.split_parts)} parts"
        )
        if source is not None:
            self.preview.set_source(source.location, duration)
        self.timeline.set_duration(duration)
        selected_id = context.selection.row_id
        selected_kind = context.selection.kind
        self.transcript_view.blockSignals(True)
        self.transcript_model.set_rows(session.transcript)
        self.transcript_view.blockSignals(False)
        if selected_kind == "transcript":
            for index, row in enumerate(session.transcript):
                if row.row_id == selected_id:
                    self.transcript_view.selectRow(index)
                    break
        elif not selected_id:
            self.inspector.clear()
            self.preview.set_caption("")
        self.transcript_status.setText(
            "DEMO source transcript — simulated fixture. Use REAL transcription to replace it."
            if session.is_demo else context.transcript_message)
        self.table.set_narration_segments(session.narration_segments)
        self.table.set_exact_rows(session.exact_dubbing_rows)
        self.table.set_parts(session.split_parts)
        self.table.set_overlays(session.overlays)
        self._refresh_markers()
        self._refresh_mode_panels()
        self._apply_mode_visibility()

    def _on_metadata_changed(self, _metadata) -> None:
        self._reload()

    def _start_local_transcript(self) -> None:
        if self._context is None or self._context.transcript_running:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Transcribe a real local video", "", "Media (*.mp4 *.mkv *.mov *.avi *.webm *.wav *.mp3);;All files (*)")
        if not path:
            return
        if not confirm_before_discard(self, self._context, action="a new local transcript", allow_save=False):
            return
        # The explicit discard was approved. Do not pretend to save edits.
        self._context.project.mark_narration_clean()
        self._context.project.mark_exact_rows_clean()
        try:
            self._context.start_local_transcript(path, self.language_edit.text().strip() or None, self.auto_language.isChecked())
        except (ValueError, RuntimeError, OSError) as exc:
            self.transcript_status.setText(f"Transcribe failed: {exc}. Fix the input/dependency and restart.")

    def _stop_transcript(self) -> None:
        if self._context is not None:
            self._context.stop_transcript()

    def _on_transcript_state(self, state, message) -> None:
        self.transcript_status.setText(message)
        active = self._context.transcript_running or state in {"running", "stopping"}
        self.transcribe_button.setEnabled(not active)
        self.transcript_stop.setEnabled(active and state != "stopping")
        if state == "running":
            self.transcript_progress.setRange(0, 0)
        elif state == "complete":
            self.transcript_progress.setRange(0, 100)
            self.transcript_progress.setValue(100)
        elif state in {"failed", "stopped"}:
            self.transcript_progress.setRange(0, 100)
            self.transcript_progress.setValue(0)

    def _on_transcript_progress(self, event) -> None:
        self.transcript_status.setText(f"REAL transcription: {event.message}")
        if event.percent > 0:
            self.transcript_progress.setRange(0, 100)
            self.transcript_progress.setValue(int(event.percent))

    def _on_transcript_selected(self, current, _previous) -> None:
        if current.isValid() and self._context is not None:
            row = self.transcript_model.rows[current.row()]
            self._context.selection.select(row.row_id, "transcript")

    def _refresh_markers(self) -> None:
        context = self._context
        if context is None or context.session is None:
            self.timeline.set_markers([])
            return
        session = context.session
        markers: list[TimelineMarker] = []
        if self._mode is AppMode.NARRATOR and not session.narration_segments:
            markers = [TimelineMarker(position=r.start, duration=r.duration, label=r.row_id, kind="transcript") for r in session.transcript]
        if self._mode is AppMode.NARRATOR:
            for segment in session.narration_segments:
                markers.append(
                    TimelineMarker(
                        position=segment.start,
                        duration=segment.duration,
                        label=segment.segment_id.replace("narr_", "#"),
                        kind="segment",
                    )
                )
        elif self._mode is AppMode.EXACT_DUBBING:
            for row in session.exact_dubbing_rows:
                markers.append(
                    TimelineMarker(
                        position=row.start,
                        duration=row.duration,
                        label=row.row_id.replace("seg_", "#"),
                        kind="exact",
                    )
                )
        elif self._mode is AppMode.SPLITTER:
            for part in session.split_parts:
                markers.append(
                    TimelineMarker(
                        position=part.start,
                        duration=part.duration,
                        label=f"Part {part.number}",
                        kind="part",
                    )
                )
        else:
            for overlay in session.overlays:
                markers.append(
                    TimelineMarker(
                        position=overlay.start,
                        duration=overlay.duration,
                        label=overlay.kind.value.replace("_", " ").title(),
                        kind="overlay",
                    )
                )
        self.timeline.set_markers(markers)

    def _refresh_mode_panels(self) -> None:
        context = self._context
        if context is None or context.session is None:
            return
        session = context.session
        self.narrator_panel.set_segments(session.narration_segments)
        self.exact_panel.set_rows(session.exact_dubbing_rows)
        self.splitter_panel.set_parts(session.split_parts)
        self.common_panel.set_output_folder(session.output_folder)
        self.common_panel.set_overlay_count(len(session.overlays))

    # -- mode ------------------------------------------------------------------- #
    def _on_context_mode_changed(self, mode: AppMode) -> None:
        self.set_mode(mode)

    def set_mode(self, mode: AppMode) -> None:
        self._mode = mode
        self.mode_switcher.set_mode(mode)
        self.table.set_mode(mode)
        self.inspector.set_mode(mode)
        self.timeline.set_mode(mode)
        self._apply_mode_visibility()
        self._refresh_markers()
        self._refresh_mode_panels()
        self.table_header.set_subtitle(self._table_subtitle())

    def _apply_mode_visibility(self) -> None:
        self.narrator_panel.setVisible(self._mode is AppMode.NARRATOR)
        self.exact_panel.setVisible(self._mode is AppMode.EXACT_DUBBING)
        self.splitter_panel.setVisible(self._mode is AppMode.SPLITTER)
        self.common_panel.setVisible(self._mode is AppMode.COMMON_EDITING)

    def _table_subtitle(self) -> str:
        return {
            AppMode.NARRATOR: "Summarised narration - rows may be merged, "
                              "re-ordered and rewritten.",
            AppMode.EXACT_DUBBING: "One row per source line - nothing may be "
                                   "summarised, omitted, re-ordered or merged.",
            AppMode.SPLITTER: "The output parts planned from the source.",
            AppMode.COMMON_EDITING: "The overlays placed on the output.",
        }[self._mode]

    def _on_mode_switched(self, mode: AppMode) -> None:
        if self._context is not None:
            self._context.set_mode(mode)
        else:
            self.set_mode(mode)

    # -- selection ---------------------------------------------------------------- #
    def _on_row_selected(self, row_id: str, kind: str) -> None:
        if self._context is None:
            return
        self._context.selection.select(row_id, kind)
        self._show_row(row_id, kind)

    def _on_context_selection(self, row_id: str, kind: str) -> None:
        # The selection may originate outside the table (keyboard, the
        # timeline, a problem list); mirror it back so the table, the
        # timeline and the inspector always agree.
        if self._kind_matches_table(kind):
            self.table.select_row_id(row_id)
        self._show_row(row_id, kind)

    def _kind_matches_table(self, kind: str) -> bool:
        """True when ``kind`` is the working set shown by the current mode."""
        return {
            AppMode.NARRATOR: "narration",
            AppMode.EXACT_DUBBING: "exact",
            AppMode.SPLITTER: "part",
            AppMode.COMMON_EDITING: "overlay",
        }.get(self._mode) == kind

    def _on_selection_cleared(self) -> None:
        self.inspector.clear()

    def _show_row(self, row_id: str, kind: str) -> None:
        context = self._context
        if context is None or context.session is None:
            return
        session = context.session
        self.timeline.set_selection(row_id)

        if kind == "transcript":
            for row in session.transcript:
                if row.row_id == row_id:
                    self.inspector.show_generic(row.row_id, f"{row.start}s — {row.end}s (locked)", row.text)
                    self.preview.set_caption(row.text)
                    self.preview.set_position(row.start)
                    self.timeline.set_position(row.start)
                    return
        if kind == "narration":
            for segment in session.narration_segments:
                if segment.segment_id == row_id:
                    self.inspector.show_narration(segment)
                    self.preview.set_caption(segment.narration)
                    self.preview.set_position(segment.start)
                    self.timeline.set_position(segment.start)
                    return
        elif kind == "exact":
            for row in session.exact_dubbing_rows:
                if row.row_id == row_id:
                    self.inspector.show_exact(row)
                    self.preview.set_caption(row.burmese or row.original)
                    self.preview.set_position(row.start)
                    self.timeline.set_position(row.start)
                    return
        elif kind == "part":
            for part in session.split_parts:
                if f"part_{part.number}" == row_id:
                    self.inspector.show_generic(
                        f"Part {part.number}",
                        f"{part.start:.1f}s - {part.end:.1f}s",
                        f"cut reason: {part.cut_reason.value}",
                    )
                    self.preview.set_caption(part.label or f"Part {part.number}")
                    self.preview.set_position(part.start)
                    self.timeline.set_position(part.start)
                    return
        elif kind == "overlay":
            for overlay in session.overlays:
                if overlay.kind.value == row_id:
                    self.inspector.show_generic(
                        overlay.kind.value.replace("_", " ").title(),
                        f"{overlay.start:.1f}s - {overlay.end:.1f}s",
                        f"position: {overlay.position}",
                    )
                    self.preview.set_caption(overlay.text or overlay.kind.value)
                    self.preview.set_position(overlay.start)
                    self.timeline.set_position(overlay.start)
                    return

    # -- edits -------------------------------------------------------------------- #
    def _on_narration_edited(self, segment_id: str, text: str) -> None:
        if self._context is not None:
            self._context.project.update_narration(segment_id, text)
            self._refresh_mode_panels()

    def _on_burmese_edited(self, row_id: str, text: str) -> None:
        if self._context is not None:
            self._context.project.update_exact_row(row_id, burmese=text)
            self._refresh_mode_panels()

    def _on_inspector_text(self, row_id: str, text: str) -> None:
        if self._context is None:
            return
        if self._mode is AppMode.NARRATOR:
            self._context.project.update_narration(row_id, text)
        else:
            self._context.project.update_exact_row(row_id, burmese=text)
        self._refresh_mode_panels()

    def _on_gender_changed(self, row_id: str, gender: str) -> None:
        if self._context is None:
            return
        self._context.project.update_exact_row(row_id, gender=gender)
        self._refresh_mode_panels()

    def _on_save_requested(self, _mode_value: str) -> None:
        if self._context is None:
            return
        if self._mode is AppMode.NARRATOR:
            self._context.project.mark_narration_clean()
        elif self._mode is AppMode.EXACT_DUBBING:
            self._context.project.mark_exact_rows_clean()
        self._refresh_mode_panels()

    def _on_validate_requested(self, _mode_value: str) -> None:
        if self._context is None:
            return
        self._context.validate(self._mode)

    def _on_validation_changed(self, report) -> None:
        # Update exact dubbing panel validation state
        if self._mode is AppMode.EXACT_DUBBING:
            self.exact_panel.update_validation(report)
        # Future: update other panels

    # -- timeline ------------------------------------------------------------------ #
    def _on_timeline_seek(self, seconds: float) -> None:
        self.preview.set_position(seconds)

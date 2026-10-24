"""The right-hand inspector.

Shows the properties of whatever is selected in the working set and offers
the controls that belong to the *current mode only*:

* Narrator Mode      - edit the narration text, see boundary flags.
* Exact Dubbing Mode - pick the speaker gender, see the voice it maps to.
* Splitter Mode      - see the cut reason and toggle the part.
* Common Editing     - see the overlay kind, position and range.

The narrator and exact-dubbing panels are separate classes with separate
widgets; there is no shared "text row" abstraction that could blur the two
contracts.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import AppMode, Gender
from ...domain.models import ExactDubbingRow, NarrationSegment
from ..theme.palette import Palette
from ..widgets.timecode import format_duration, format_timecode

__all__ = ["Inspector"]

_GENDER_ITEMS = (
    (Gender.MALE.value, "my-MM-ThihaNeural"),
    (Gender.FEMALE.value, "my-MM-NilarNeural"),
    (Gender.UNKNOWN.value, "my-MM-NilarNeural (fallback)"),
)


class _InspectorSection(QWidget):
    """A titled group of fields."""

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title = QLabel(title.upper())
        self.title.setProperty("role", "sectionTitle")
        layout.addWidget(self.title)

        self.form = QFormLayout()
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(6)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.form)

    def add_row(self, label: str, widget: QWidget) -> QWidget:
        self.form.addRow(label, widget)
        return widget

    def add_label(self, label: str, value: str = "-") -> QLabel:
        field = QLabel(value)
        field.setProperty("role", "mono")
        field.setTextInteractionFlags(Qt.TextSelectableByMouse)
        field.setWordWrap(True)
        self.form.addRow(label, field)
        return field


class Inspector(QWidget):
    """Right-side property inspector."""

    narrationChanged = Signal(str, str)   # segment_id, text
    genderChanged = Signal(str, str)      # row_id, gender value
    saveRequested = Signal(str)           # mode value
    validateRequested = Signal(str)       # mode value

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(330)
        self.setStyleSheet(
            f"""
            QWidget#inspector {{
                background: {Palette.BG_PANEL};
                border-left: 1px solid {Palette.BORDER};
            }}
            """
        )
        self.setObjectName("inspector")

        self._mode = AppMode.COMMON_EDITING
        self._segment: Optional[NarrationSegment] = None
        self._exact_row: Optional[ExactDubbingRow] = None
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(10)

        self.header = QLabel("INSPECTOR")
        self.header.setProperty("role", "sectionTitle")
        outer.addWidget(self.header)

        self.hint = QLabel("Select a row to inspect it.")
        self.hint.setProperty("role", "muted")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        outer.addWidget(scroll, 1)

        host = QWidget()
        host.setStyleSheet(f"background: {Palette.BG_PANEL};")
        self.body = QVBoxLayout(host)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(14)
        scroll.setWidget(host)

        # -- narrator section ------------------------------------------------ #
        self.narrator_section = _InspectorSection("Narration")
        self.narration_edit = QPlainTextEdit()
        self.narration_edit.setPlaceholderText("Myanmar narration for this segment")
        self.narration_edit.setMinimumHeight(120)
        self.narration_edit.setProperty("role", "log")
        self.narration_edit.textChanged.connect(self._on_narration_text_changed)
        self.narrator_section.add_row("Text", self.narration_edit)

        self.narrator_source = self.narrator_section.add_label("Source", "-")
        self.narrator_range = self.narrator_section.add_label("Range", "-")
        self.narrator_duration = self.narrator_section.add_label("Duration", "-")
        self.narrator_flags = self.narrator_section.add_label("Flags", "-")
        self.body.addWidget(self.narrator_section)

        # -- exact dubbing section ------------------------------------------- #
        self.exact_section = _InspectorSection("Exact dubbing")
        self.exact_original = self.exact_section.add_label("Original", "-")
        self.exact_row_id = self.exact_section.add_label("Row id", "-")
        self.exact_range = self.exact_section.add_label("Range", "-")

        self.gender_combo = QComboBox()
        for value, _voice in _GENDER_ITEMS:
            self.gender_combo.addItem(value)
        self.gender_combo.currentIndexChanged.connect(self._on_gender_changed)
        self.exact_section.add_row("Speaker", self.gender_combo)

        self.voice_label = QLabel("-")
        self.voice_label.setProperty("role", "mono")
        self.exact_section.add_row("Voice", self.voice_label)

        self.exact_edit = QPlainTextEdit()
        self.exact_edit.setPlaceholderText("Myanmar translation for this line")
        self.exact_edit.setMinimumHeight(120)
        self.exact_edit.setProperty("role", "log")
        self.exact_edit.textChanged.connect(self._on_exact_text_changed)
        self.exact_section.add_row("Burmese", self.exact_edit)

        self.exact_note = QLabel(
            "The original line, its id and its timing are immutable. "
            "Only the Burmese text and the speaker may change."
        )
        self.exact_note.setProperty("role", "faint")
        self.exact_note.setWordWrap(True)
        self.exact_section.add_row("", self.exact_note)
        self.body.addWidget(self.exact_section)

        # -- generic section -------------------------------------------------- #
        self.generic_section = _InspectorSection("Properties")
        self.generic_name = self.generic_section.add_label("Name", "-")
        self.generic_range = self.generic_section.add_label("Range", "-")
        self.generic_detail = self.generic_section.add_label("Detail", "-")
        self.body.addWidget(self.generic_section)

        self.body.addStretch(1)

        # -- actions ------------------------------------------------------------ #
        actions = QHBoxLayout()
        actions.setSpacing(8)

        # Bound methods, not lambdas: a lambda capturing ``self`` creates a
        # parent -> child -> connection -> lambda -> parent cycle that keeps
        # the widget alive past interpreter shutdown and aborts Qt teardown.
        self.validate_button = QPushButton("Validate")
        self.validate_button.setProperty("variant", "ghost")
        self.validate_button.clicked.connect(self._emit_validate)

        self.save_button = QPushButton("Save edits")
        self.save_button.setProperty("variant", "primary")
        self.save_button.clicked.connect(self._emit_save)

        actions.addWidget(self.validate_button)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)

        self.set_mode(AppMode.COMMON_EDITING)

    # -- signal emitters ---------------------------------------------------- #
    # Bound methods, not lambdas: see the note in ``__init__``.

    def _emit_validate(self) -> None:
        self.validateRequested.emit(self._mode.value)

    def _emit_save(self) -> None:
        self.saveRequested.emit(self._mode.value)

    # -- mode --------------------------------------------------------------- #
    def set_mode(self, mode: AppMode) -> None:
        self._mode = mode
        self.narrator_section.setVisible(mode is AppMode.NARRATOR)
        self.exact_section.setVisible(mode is AppMode.EXACT_DUBBING)
        self.generic_section.setVisible(
            mode in (AppMode.COMMON_EDITING, AppMode.SPLITTER)
        )
        self.save_button.setEnabled(
            mode in (AppMode.NARRATOR, AppMode.EXACT_DUBBING)
        )
        if mode is AppMode.NARRATOR:
            self.header.setText("INSPECTOR - NARRATOR")
        elif mode is AppMode.EXACT_DUBBING:
            self.header.setText("INSPECTOR - EXACT DUBBING")
        elif mode is AppMode.SPLITTER:
            self.header.setText("INSPECTOR - SPLITTER")
        else:
            self.header.setText("INSPECTOR - COMMON EDITING")

    # -- selection ----------------------------------------------------------- #
    def show_narration(self, segment: NarrationSegment) -> None:
        self._segment = segment
        self._exact_row = None
        self._loading = True
        self.narration_edit.setPlainText(segment.narration)
        self._loading = False
        self.narrator_source.setText(segment.source_text)
        self.narrator_range.setText(
            f"{format_timecode(segment.start)} - {format_timecode(segment.end)}"
        )
        self.narrator_duration.setText(format_duration(segment.duration))
        flags = []
        if segment.semantic_boundary:
            flags.append("semantic boundary")
        if segment.forced_boundary:
            flags.append("forced boundary")
        if segment.visual_reason:
            flags.append(segment.visual_reason)
        self.narrator_flags.setText(", ".join(flags) if flags else "-")
        self.hint.setText("")

    def show_exact(self, row: ExactDubbingRow) -> None:
        self._exact_row = row
        self._segment = None
        self._loading = True
        self.exact_edit.setPlainText(row.burmese)
        self.gender_combo.setCurrentIndex(
            max(0, self.gender_combo.findText(row.gender.value))
        )
        self._loading = False
        self.exact_original.setText(row.original)
        self.exact_row_id.setText(row.row_id)
        self.exact_range.setText(
            f"{format_timecode(row.start)} + {row.duration:.2f}s"
        )
        self._update_voice_label(row)
        self.hint.setText("")

    def show_generic(self, name: str, range_text: str, detail: str) -> None:
        self._segment = None
        self._exact_row = None
        self.generic_name.setText(name)
        self.generic_range.setText(range_text)
        self.generic_detail.setText(detail)
        self.hint.setText("")

    def clear(self) -> None:
        self._segment = None
        self._exact_row = None
        self.hint.setText("Select a row to inspect it.")

    # -- editing ------------------------------------------------------------- #
    def _on_narration_text_changed(self) -> None:
        if self._loading or self._segment is None:
            return
        self.narrationChanged.emit(self._segment.segment_id, self.narration_edit.toPlainText())

    def _on_exact_text_changed(self) -> None:
        if self._loading or self._exact_row is None:
            return
        self.narrationChanged.emit(self._exact_row.row_id, self.exact_edit.toPlainText())

    def _on_gender_changed(self, index: int) -> None:
        if self._loading or self._exact_row is None or index < 0:
            return
        value = self.gender_combo.itemText(index)
        self.genderChanged.emit(self._exact_row.row_id, value)
        self._update_voice_label(self._exact_row)

    def _update_voice_label(self, row: ExactDubbingRow) -> None:
        for value, voice in _GENDER_ITEMS:
            if value == row.gender.value:
                self.voice_label.setText(voice)
                if row.gender is Gender.UNKNOWN:
                    self.voice_label.setStyleSheet(f"color: {Palette.WARNING};")
                else:
                    self.voice_label.setStyleSheet("")
                return

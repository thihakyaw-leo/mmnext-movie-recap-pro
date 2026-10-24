"""The working-set table.

One :class:`QTableView` per working set, stacked. The active view is chosen
by the current :class:`~mmnext.domain.enums.AppMode`:

* Narrator Mode      -> :class:`NarrationTableModel`
* Exact Dubbing Mode -> :class:`ExactDubbingTableModel`
* Splitter Mode      -> :class:`SplitPartTableModel`
* Common Editing     -> :class:`OverlayTableModel`

The narrator table and the exact-dubbing table are *different views over
different row types*. Nothing converts between them.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import AppMode
from ...domain.models import (
    ExactDubbingRow,
    NarrationSegment,
    Overlay,
    SplitPart,
)
from ..models.exact_dubbing_model import ExactDubbingTableModel
from ..models.narration_model import NarrationTableModel
from ..models.overlay_model import OverlayTableModel
from ..models.split_part_model import SplitPartTableModel

__all__ = ["SegmentTable"]


def _configure(view: QTableView) -> None:
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    view.setEditTriggers(
        QAbstractItemView.EditTrigger.DoubleClicked
        | QAbstractItemView.EditTrigger.SelectedClicked
        | QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.AnyKeyPressed
    )
    view.setAlternatingRowColors(True)
    view.setWordWrap(False)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(26)
    header = view.horizontalHeader()
    header.setHighlightSections(False)
    header.setStretchLastSection(True)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)


class SegmentTable(QWidget):
    """Stacked working-set tables."""

    rowSelected = Signal(str, str)     # row_id, kind
    selectionCleared = Signal()
    narrationEdited = Signal(str, str)  # segment_id, text
    burmeseEdited = Signal(str, str)    # row_id, text

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        # -- narrator -------------------------------------------------------- #
        self.narration_model = NarrationTableModel()
        self.narration_view = QTableView()
        self.narration_view.setModel(self.narration_model)
        _configure(self.narration_view)
        self.narration_model.narrationEdited.connect(self.narrationEdited)
        self.narration_view.selectionModel().currentRowChanged.connect(
            self._on_narration_row_changed
        )
        self.stack.addWidget(self.narration_view)

        # -- exact dubbing --------------------------------------------------- #
        self.exact_model = ExactDubbingTableModel()
        self.exact_view = QTableView()
        self.exact_view.setModel(self.exact_model)
        _configure(self.exact_view)
        self.exact_model.burmeseEdited.connect(self.burmeseEdited)
        self.exact_view.selectionModel().currentRowChanged.connect(
            self._on_exact_row_changed
        )
        self.stack.addWidget(self.exact_view)

        # -- splitter parts -------------------------------------------------- #
        self.parts_model = SplitPartTableModel()
        self.parts_view = QTableView()
        self.parts_view.setModel(self.parts_model)
        _configure(self.parts_view)
        self.parts_view.selectionModel().currentRowChanged.connect(
            self._on_part_row_changed
        )
        self.stack.addWidget(self.parts_view)

        # -- overlays -------------------------------------------------------- #
        self.overlay_model = OverlayTableModel()
        self.overlay_view = QTableView()
        self.overlay_view.setModel(self.overlay_model)
        _configure(self.overlay_view)
        self.overlay_view.selectionModel().currentRowChanged.connect(
            self._on_overlay_row_changed
        )
        self.stack.addWidget(self.overlay_view)

    # -- data -------------------------------------------------------------- #
    def set_mode(self, mode: AppMode) -> None:
        if mode is AppMode.NARRATOR:
            self.stack.setCurrentWidget(self.narration_view)
        elif mode is AppMode.EXACT_DUBBING:
            self.stack.setCurrentWidget(self.exact_view)
        elif mode is AppMode.SPLITTER:
            self.stack.setCurrentWidget(self.parts_view)
        else:
            self.stack.setCurrentWidget(self.overlay_view)

    def set_narration_segments(self, segments: list[NarrationSegment]) -> None:
        self.narration_model.set_segments(segments)

    def set_exact_rows(self, rows: list[ExactDubbingRow]) -> None:
        self.exact_model.set_rows(rows)

    def set_parts(self, parts: list[SplitPart]) -> None:
        self.parts_model.set_parts(parts)

    def set_overlays(self, overlays: list[Overlay]) -> None:
        self.overlay_model.set_overlays(overlays)

    def current_table(self) -> QTableView:
        return self.stack.currentWidget()  # type: ignore[return-value]

    def select_row(self, row: int) -> None:
        view = self.current_table()
        if view is None or view.model() is None:
            return
        if 0 <= row < view.model().rowCount():
            view.selectRow(row)

    def selected_row(self) -> int:
        view = self.current_table()
        if view is None:
            return -1
        index = view.currentIndex()
        return index.row() if index.isValid() else -1

    def selected_row_id(self) -> str:
        row = self.selected_row()
        if row < 0:
            return ""
        return self._row_id_at(self.current_table().model(), row)

    def select_row_id(self, row_id: str) -> bool:
        """Select the row carrying ``row_id``.

        Used to keep the table in sync with a selection made elsewhere
        (keyboard navigation, the timeline, a problem list).  Returns
        ``True`` when a matching row was found and selected.
        """
        if not row_id:
            return False
        view = self.current_table()
        if view is None or view.model() is None:
            return False
        model = view.model()
        for row in range(model.rowCount()):
            if self._row_id_at(model, row) == row_id:
                view.selectRow(row)
                return True
        return False

    def _row_id_at(self, model, row: int) -> str:
        """The stable id of ``row`` in ``model`` (empty when unknown)."""
        if model is self.narration_model:
            segment = self.narration_model.segment_at(row)
            return segment.segment_id if segment else ""
        if model is self.exact_model:
            exact = self.exact_model.row_at(row)
            return exact.row_id if exact else ""
        if model is self.parts_model:
            part = self.parts_model.part_at(row)
            return f"part_{part.number}" if part else ""
        if model is self.overlay_model:
            overlay = self.overlay_model.overlay_at(row)
            return overlay.kind.value if overlay else ""
        return ""

    # -- selection --------------------------------------------------------- #
    def _on_narration_row_changed(self, current, _previous) -> None:
        if current.isValid():
            segment = self.narration_model.segment_at(current.row())
            if segment is not None:
                self.rowSelected.emit(segment.segment_id, "narration")
        else:
            self.selectionCleared.emit()

    def _on_exact_row_changed(self, current, _previous) -> None:
        if current.isValid():
            exact = self.exact_model.row_at(current.row())
            if exact is not None:
                self.rowSelected.emit(exact.row_id, "exact")
        else:
            self.selectionCleared.emit()

    def _on_part_row_changed(self, current, _previous) -> None:
        if current.isValid():
            part = self.parts_model.part_at(current.row())
            if part is not None:
                self.rowSelected.emit(f"part_{part.number}", "part")
        else:
            self.selectionCleared.emit()

    def _on_overlay_row_changed(self, current, _previous) -> None:
        if current.isValid():
            overlay = self.overlay_model.overlay_at(current.row())
            if overlay is not None:
                self.rowSelected.emit(overlay.kind.value, "overlay")
        else:
            self.selectionCleared.emit()

"""The workspace timeline.

A custom-painted timeline with:

* a time ruler,
* one track per active working set (segments / exact rows / split parts /
  overlays),
* a draggable playhead,
* click-to-seek.

The timeline is painted rather than composed from widgets because the
number of blocks is data-driven and a paint pass keeps it fast and
predictable.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygon
from PySide6.QtWidgets import QSizePolicy, QWidget

from ...domain.enums import AppMode
from ...domain.models import TimelineMarker
from ..theme.palette import Palette
from ..widgets.timecode import format_timecode

__all__ = ["Timeline"]

_RULER_HEIGHT = 22
_TRACK_TOP = 30
_TRACK_HEIGHT = 46
_TRACK_GAP = 8
_SIDE_PADDING = 8


class Timeline(QWidget):
    """A single-track timeline with a playhead."""

    seekRequested = Signal(float)
    positionChanged = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(_RULER_HEIGHT + _TRACK_TOP + _TRACK_HEIGHT + 12)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(
            f"background: {Palette.BG_TIMELINE}; border: 1px solid {Palette.BORDER};"
            f"border-radius: 6px;"
        )

        self._duration = 0.0
        self._position = 0.0
        self._markers: list[TimelineMarker] = []
        self._mode = AppMode.COMMON_EDITING
        self._selected = ""
        self._dragging = False

    # -- data -------------------------------------------------------------- #
    def set_duration(self, duration: float) -> None:
        self._duration = max(0.0, duration)
        self.update()

    def set_position(self, position: float) -> None:
        self._position = max(0.0, position)
        self.update()

    def set_markers(self, markers: list[TimelineMarker]) -> None:
        self._markers = list(markers)
        self.update()

    def set_mode(self, mode: AppMode) -> None:
        self._mode = mode
        self.update()

    def set_selection(self, marker_id: str) -> None:
        self._selected = marker_id
        self.update()

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    # -- painting ----------------------------------------------------------- #
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(Palette.BG_TIMELINE))

        self._paint_ruler(painter, rect)
        self._paint_track(painter, rect)
        self._paint_playhead(painter, rect)

    def _paint_ruler(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(
            QRectF(rect.left(), rect.top(), rect.width(), _RULER_HEIGHT),
            QColor(Palette.BG_TOOLBAR),
        )
        painter.setPen(QPen(QColor(Palette.BORDER), 1))
        painter.drawLine(
            int(rect.left()),
            int(rect.top() + _RULER_HEIGHT),
            int(rect.right()),
            int(rect.top() + _RULER_HEIGHT),
        )

        if self._duration <= 0:
            return

        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)

        # Aim for roughly six labels regardless of duration.
        steps = 6
        for index in range(steps + 1):
            ratio = index / steps
            x = self._x_for(ratio, rect)
            seconds = self._duration * ratio
            painter.setPen(QPen(QColor(Palette.TEXT_FAINT), 1))
            painter.drawLine(
                int(x),
                int(rect.top() + _RULER_HEIGHT - 5),
                int(x),
                int(rect.top() + _RULER_HEIGHT),
            )
            painter.setPen(QColor(Palette.TEXT_FAINT))
            painter.drawText(
                QRectF(x - 40, rect.top() + 2, 80, _RULER_HEIGHT - 6),
                Qt.AlignmentFlag.AlignCenter,
                format_timecode(seconds, millis=False),
            )

    def _paint_track(self, painter: QPainter, rect: QRectF) -> None:
        track_rect = QRectF(
            rect.left() + _SIDE_PADDING,
            rect.top() + _TRACK_TOP,
            rect.width() - _SIDE_PADDING * 2,
            _TRACK_HEIGHT,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Palette.TIMELINE_TRACK))
        painter.drawRoundedRect(track_rect, 4, 4)

        if self._duration <= 0 or not self._markers:
            painter.setPen(QColor(Palette.TEXT_FAINT))
            font = QFont(self.font())
            font.setPointSize(9)
            painter.setFont(font)
            painter.drawText(
                track_rect,
                Qt.AlignmentFlag.AlignCenter,
                "No timeline blocks in the current working set",
            )
            return

        for marker in self._markers:
            if marker.duration <= 0:
                continue
            start_ratio = marker.position / self._duration
            end_ratio = (marker.position + marker.duration) / self._duration
            x0 = self._x_for(start_ratio, rect)
            x1 = self._x_for(end_ratio, rect)
            width = max(2.0, x1 - x0)

            block = QRectF(x0, track_rect.top() + 4, width, track_rect.height() - 8)
            selected = marker.label == self._selected
            if selected:
                color = QColor(Palette.TIMELINE_SELECTED)
            else:
                color = QColor(self._marker_color(marker))
            painter.setBrush(color)
            painter.setPen(QPen(QColor(Palette.BG_TIMELINE), 1))
            painter.drawRoundedRect(block, 3, 3)

            if width > 42:
                font = QFont(self.font())
                font.setPointSize(8)
                painter.setFont(font)
                painter.setPen(QColor(Palette.TEXT))
                painter.drawText(
                    block.adjusted(4, 0, -4, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    marker.label,
                )

    def _marker_color(self, marker: TimelineMarker) -> str:
        if marker.kind == "part":
            return Palette.ACCENT
        if marker.kind == "overlay":
            return Palette.WARNING
        if marker.kind == "exact":
            return "#2f81f7"
        return Palette.WAVEFORM_DIM

    def _paint_playhead(self, painter: QPainter, rect: QRectF) -> None:
        if self._duration <= 0:
            return
        ratio = max(0.0, min(1.0, self._position / self._duration))
        x = self._x_for(ratio, rect)

        painter.setPen(QPen(QColor(Palette.PLAYHEAD), 2))
        painter.drawLine(
            int(x), int(rect.top() + _RULER_HEIGHT - 4), int(x), int(rect.bottom())
        )

        head = QRectF(x - 5, rect.top() + _RULER_HEIGHT - 8, 10, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Palette.PLAYHEAD))
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(int(head.left()), int(head.top())),
                    QPoint(int(head.right()), int(head.top())),
                    QPoint(int(head.center().x()), int(head.bottom())),
                ]
            )
        )

    def _x_for(self, ratio: float, rect: QRectF) -> float:
        usable = rect.width() - _SIDE_PADDING * 2
        return rect.left() + _SIDE_PADDING + usable * max(0.0, min(1.0, ratio))

    def _ratio_for(self, x: float) -> float:
        rect = QRectF(self.rect())
        usable = rect.width() - _SIDE_PADDING * 2
        if usable <= 0:
            return 0.0
        return max(0.0, min(1.0, (x - rect.left() - _SIDE_PADDING) / usable))

    # -- interaction --------------------------------------------------------- #
    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._dragging = True
        self._seek_to(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._dragging:
            self._seek_to(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._dragging:
            self._dragging = False
            self._seek_to(event.position().x())

    def _seek_to(self, x: float) -> None:
        if self._duration <= 0:
            return
        target = self._ratio_for(x) * self._duration
        self._position = target
        self.update()
        self.positionChanged.emit(target)
        self.seekRequested.emit(target)

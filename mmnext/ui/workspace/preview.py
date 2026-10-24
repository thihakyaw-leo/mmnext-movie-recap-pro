"""Video preview panel.

The panel is written against the :class:`VideoPlayer` protocol, so it works
with the mpv adapter *and* with the placeholder fallback. When no real
player is available it draws a synthetic frame that shows the current
timecode and the selected segment - so the workspace is never a blank box.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...application.player_service import PlayerService
from ...domain.enums import AppMode
from ..theme.palette import Palette
from ..widgets.timecode import format_timecode

__all__ = ["PreviewPanel"]

_TICK_MS = 100


class _PlaceholderCanvas(QWidget):
    """Draws the synthetic preview frame."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet(
            f"background: {Palette.BG_TIMELINE}; border: 1px solid {Palette.BORDER};"
            f"border-radius: 6px;"
        )
        self._position = 0.0
        self._duration = 0.0
        self._caption = ""
        self._player_name = "Placeholder player"

    def set_state(
        self,
        position: float,
        duration: float,
        caption: str,
        player_name: str,
    ) -> None:
        self._position = position
        self._duration = duration
        self._caption = caption
        self._player_name = player_name
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.fillRect(rect, QColor(Palette.BG_TIMELINE))

        # subtle grid so the frame does not look like a broken widget
        pen = QPen(QColor(Palette.BORDER))
        pen.setWidth(1)
        painter.setPen(pen)
        step = 48
        for x in range(rect.left(), rect.right(), step):
            painter.drawLine(x, rect.top(), x, rect.bottom())
        for y in range(rect.top(), rect.bottom(), step):
            painter.drawLine(rect.left(), y, rect.right(), y)

        title_font = QFont(self.font())
        title_font.setPointSize(13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(Palette.TEXT))
        painter.drawText(
            rect.adjusted(16, 12, -16, 0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            "VIDEO PREVIEW",
        )

        caption_font = QFont(self.font())
        caption_font.setPointSize(9)
        painter.setFont(caption_font)
        painter.setPen(QColor(Palette.TEXT_FAINT))
        painter.drawText(
            rect.adjusted(16, 34, -16, 0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            f"{self._player_name} - no video output in demo mode",
        )

        if self._caption:
            painter.setFont(caption_font)
            painter.setPen(QColor(Palette.TEXT_MUTED))
            painter.drawText(
                rect.adjusted(16, 0, -16, -18),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                self._caption,
            )

        # big timecode in the centre
        big_font = QFont(self.font())
        big_font.setPointSize(26)
        big_font.setBold(True)
        painter.setFont(big_font)
        painter.setPen(QColor(Palette.TEXT_MUTED))
        time_text = format_timecode(self._position)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(time_text)
        painter.drawText(
            QRectF(
                rect.center().x() - width / 2,
                rect.center().y() - 18,
                width + 8,
                40,
            ),
            Qt.AlignmentFlag.AlignCenter,
            time_text,
        )

        # progress bar across the bottom
        if self._duration > 0:
            track = QRectF(
                rect.left() + 16,
                rect.bottom() - 12,
                rect.width() - 32,
                4,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(Palette.BORDER))
            painter.drawRoundedRect(track, 2, 2)
            ratio = max(0.0, min(1.0, self._position / self._duration))
            done = QRectF(
                track.left(), track.top(), track.width() * ratio, track.height()
            )
            painter.setBrush(QColor(Palette.ACCENT))
            painter.drawRoundedRect(done, 2, 2)


class PreviewPanel(QWidget):
    """The preview area with transport controls."""

    seekRequested = Signal(float)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._player_service = PlayerService()
        self._player = self._player_service.create()
        self._duration = 0.0
        self._caption = ""
        self._mode = AppMode.COMMON_EDITING

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.canvas = _PlaceholderCanvas()
        layout.addWidget(self.canvas, 1)

        # -- transport -------------------------------------------------------- #
        transport = QHBoxLayout()
        transport.setSpacing(8)

        self.play_button = QPushButton("Play")
        self.play_button.setFixedWidth(74)
        self.play_button.clicked.connect(self._toggle_play)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderMoved.connect(self._on_slider_moved)

        self.time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.time_label.setProperty("role", "mono")
        self.time_label.setFixedWidth(210)
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        transport.addWidget(self.play_button)
        transport.addWidget(self.slider, 1)
        transport.addWidget(self.time_label)
        layout.addLayout(transport)

        self.player_label = QLabel("")
        self.player_label.setProperty("role", "faint")
        layout.addWidget(self.player_label)

        # -- synthetic clock for the placeholder player ----------------------- #
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        self._update_player_label()

    # -- player ------------------------------------------------------------- #
    @property
    def player(self):
        return self._player

    @property
    def player_info(self):
        return self._player_service.info(self._player)

    def set_source(self, path: str, duration: float) -> None:
        self._duration = max(0.0, duration)
        if hasattr(self._player, "set_duration"):
            self._player.set_duration(self._duration)
        if path:
            self._player.open(path)
        self._update_time_label()

    def set_caption(self, caption: str) -> None:
        self._caption = caption
        self.canvas.set_state(
            self._player.position,
            self._duration,
            caption,
            self._player.info.name,
        )

    def set_mode(self, mode: AppMode) -> None:
        self._mode = mode

    def set_position(self, seconds: float) -> None:
        self._player.seek(seconds)
        self._update_time_label()
        self.canvas.set_state(
            self._player.position, self._duration, self._caption, self._player.info.name
        )

    def position(self) -> float:
        return self._player.position

    def is_playing(self) -> bool:
        return self._player.is_playing

    # -- transport ---------------------------------------------------------- #
    def _toggle_play(self) -> None:
        if self._player.is_playing:
            self._player.pause()
        else:
            self._player.play()
        self.play_button.setText("Pause" if self._player.is_playing else "Play")

    def _on_tick(self) -> None:
        if self._player_service.is_placeholder(self._player):
            self._player_service.tick_placeholder(self._player, _TICK_MS / 1000.0)
        position = self._player.position
        if self._duration > 0:
            self.slider.blockSignals(True)
            self.slider.setValue(
                int(max(0.0, min(1000.0, position / self._duration * 1000)))
            )
            self.slider.blockSignals(False)
        self._update_time_label()
        self.canvas.set_state(
            position, self._duration, self._caption, self._player.info.name
        )

    def _on_slider_moved(self, value: int) -> None:
        if self._duration <= 0:
            return
        target = value / 1000.0 * self._duration
        self._player.seek(target)
        self._update_time_label()
        self.seekRequested.emit(target)

    def _update_time_label(self) -> None:
        position = self._player.position
        self.time_label.setText(
            f"{format_timecode(position)} / {format_timecode(self._duration)}"
        )

    def _update_player_label(self) -> None:
        info = self._player.info
        self.player_label.setText(
            f"Adapter: {info.name} - {info.detail or ('ready' if info.available else 'unavailable')}"
        )

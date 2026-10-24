"""The left navigation rail.

A vertical list of destinations. The rail is dumb on purpose: it emits
``navigate(target)`` and the main window decides which screen to show.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..theme.palette import Palette

__all__ = ["NavItem", "NavRail", "NavTarget"]


class NavTarget:
    """Screen identifiers used by the rail and the main window."""

    HOME = "home"
    IMPORT = "import"
    ANALYZE = "analyze"
    DOWNLOADS = "downloads"
    JOBS = "jobs"
    WORKSPACE = "workspace"
    SETTINGS = "settings"

    @classmethod
    def values(cls) -> tuple[str, ...]:
        """Every valid target value, in navigation order."""
        return (
            cls.HOME,
            cls.IMPORT,
            cls.ANALYZE,
            cls.DOWNLOADS,
            cls.JOBS,
            cls.WORKSPACE,
            cls.SETTINGS,
        )

    @classmethod
    def is_valid(cls, value: str) -> bool:
        return value in cls.values()


@dataclass(frozen=True, slots=True)
class NavItem:
    """One rail entry."""

    key: str
    label: str
    glyph: str
    tooltip: str = ""


_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem(NavTarget.HOME, "Home", "⌂", "Start here"),
    NavItem(NavTarget.IMPORT, "Import", "＋", "Import a local file or a YouTube URL"),
    NavItem(NavTarget.ANALYZE, "Analyze", "◈", "Inspect source metadata"),
    NavItem(NavTarget.DOWNLOADS, "Downloads", "⇩", "Download queue"),
    NavItem(NavTarget.JOBS, "Jobs", "▤", "Production jobs"),
    NavItem(NavTarget.WORKSPACE, "Workspace", "▦", "Production workspace"),
    NavItem(NavTarget.SETTINGS, "Settings", "⚙", "Application settings"),
)


class _RailButton(QWidget):
    """A single rail entry (icon + label, hover highlight)."""

    clicked = Signal(str)

    def __init__(self, item: NavItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._item = item
        self._active = False
        self._hovered = False
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        self._glyph = QLabel(item.glyph)
        self._glyph.setAlignment(Qt.AlignCenter)
        self._glyph.setFixedSize(QSize(28, 22))

        self._label = QLabel(item.label)
        self._label.setAlignment(Qt.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(self._glyph)
        layout.addWidget(self._label)
        layout.addStretch(1)

        self._apply_style()

    def _apply_style(self) -> None:
        if self._active:
            color = Palette.ACCENT
        elif self._hovered:
            color = Palette.TEXT
        else:
            color = Palette.TEXT_MUTED
        self._glyph.setStyleSheet(f"color: {color}; font-size: 16px;")
        self._label.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 600;"
        )
        if self._active:
            self._label.setStyleSheet(
                f"color: {Palette.TEXT}; font-size: 11px; font-weight: 700;"
            )

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()
        self.update()

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._item.key)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._active:
            accent = QColor(Palette.ACCENT)
            accent.setAlpha(230)
            painter.fillRect(self.rect().adjusted(0, 6, 3, -6), accent)
        painter.setPen(QPen(QColor(Palette.BORDER), 1))
        painter.drawLine(self.rect().bottomLeft(), self.rect().bottomRight())


class NavRail(QWidget):
    """The vertical navigation rail."""

    navigate = Signal(str)   # NavTarget key

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(96)
        self.setStyleSheet(
            f"""
            QWidget {{
                background: {Palette.BG_RAIL};
                border-right: 1px solid {Palette.BORDER};
            }}
            """
        )

        self._buttons: dict[str, _RailButton] = {}
        self._active_key = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 10)
        layout.setSpacing(2)

        brand = QLabel("MMNext")
        brand.setAlignment(Qt.AlignCenter)
        brand.setStyleSheet(
            f"color: {Palette.TEXT}; font-size: 15px; font-weight: 800;"
            f"letter-spacing: 1px; padding-bottom: 4px;"
        )
        layout.addWidget(brand)

        subtitle = QLabel("Recap Pro")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            f"color: {Palette.TEXT_FAINT}; font-size: 10px; padding-bottom: 12px;"
        )
        layout.addWidget(subtitle)

        for item in _NAV_ITEMS:
            button = _RailButton(item)
            button.clicked.connect(self._on_clicked)
            self._buttons[item.key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        self._demo_label = QLabel("DEMO MODE")
        self._demo_label.setAlignment(Qt.AlignCenter)
        self._demo_label.setStyleSheet(
            f"color: {Palette.WARNING}; font-size: 10px; font-weight: 800;"
            f"letter-spacing: 1px;"
        )
        layout.addWidget(self._demo_label)

    def _on_clicked(self, key: str) -> None:
        self.navigate.emit(key)

    def set_active(self, key: str) -> None:
        self._active_key = key
        for button_key, button in self._buttons.items():
            button.set_active(button_key == key)

    @property
    def active_key(self) -> str:
        return self._active_key

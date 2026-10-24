"""Common base class for the top-level screens."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..theme.palette import Palette

__all__ = ["BaseScreen", "ScreenHeader"]


class ScreenHeader(QWidget):
    """Title + subtitle + optional action row at the top of a screen."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "h1")
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setProperty("role", "muted")
        self.subtitle_label.setWordWrap(True)
        layout.addWidget(self.subtitle_label)

        self.actions = QWidget()
        self.actions_layout = QVBoxLayout(self.actions)
        self.actions_layout.setContentsMargins(0, 6, 0, 0)
        self.actions_layout.setSpacing(6)
        layout.addWidget(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions_layout.addWidget(widget)
        return widget


class BaseScreen(QWidget):
    """A scrollable screen with a header and a content area.

    Screens never touch controllers directly - they receive an
    :class:`~mmnext.ui.app_context.AppContext` and connect to its signals.
    """

    screen_key = ""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {Palette.BG_APP}; }}"
        )

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {Palette.BG_APP};")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(28, 24, 28, 28)
        self._layout.setSpacing(18)

        self._scroll.setWidget(self._content)
        outer.addWidget(self._scroll)

    @property
    def layout(self) -> QVBoxLayout:
        """The screen's content layout."""
        return self._layout

    def bind(self, context) -> None:
        """Attach the application context. Called once by the main window."""
        self._context = context
        self.on_bind(context)

    def on_bind(self, context) -> None:
        """Hook for subclasses to connect signals."""
        return None

    def on_activate(self) -> None:
        """Hook called every time the screen becomes visible."""
        return None

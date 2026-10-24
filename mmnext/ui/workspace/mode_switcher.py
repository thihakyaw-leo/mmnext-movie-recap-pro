"""The mode switcher.

Four exclusive modes, in the order from ``Agent.md``:

1. Common Video Editing
2. Splitter Mode
3. Narrator Mode
4. Exact Dubbing Mode

The switcher never mixes contracts: switching modes swaps the *working set*
(segment table, inspector) but keeps the narration and exact-dubbing data
separate at the model level.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ...domain.enums import AppMode
from ..theme.palette import Palette

__all__ = ["ModeSwitcher"]

_MODE_ORDER = (
    AppMode.COMMON_EDITING,
    AppMode.SPLITTER,
    AppMode.NARRATOR,
    AppMode.EXACT_DUBBING,
)

_MODE_HINTS = {
    AppMode.COMMON_EDITING: "Timeline, overlays and output settings.",
    AppMode.SPLITTER: "Plan output parts and pick cut points.",
    AppMode.NARRATOR: "Write the Myanmar narration over the source.",
    AppMode.EXACT_DUBBING: "Translate every line, one row per source line.",
}


class ModeSwitcher(QWidget):
    """A segmented control for the four production modes."""

    modeChanged = Signal(object)   # AppMode

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._buttons: dict[AppMode, QPushButton] = {}
        self._mode = AppMode.COMMON_EDITING

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel("MODE")
        label.setProperty("role", "sectionTitle")
        layout.addWidget(label)

        for mode in _MODE_ORDER:
            button = QPushButton(mode.display_name)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(_MODE_HINTS[mode])
            button.setMinimumHeight(30)
            # A lambda capturing ``self`` (or ``mode``) would create a
            # reference cycle that keeps the button alive past interpreter
            # shutdown and aborts Qt teardown. The mode is carried on the
            # button itself and read back in the bound slot instead.
            button.setProperty("appMode", mode.value)
            button.clicked.connect(self._on_button_clicked)
            self._buttons[mode] = button
            layout.addWidget(button)

        layout.addStretch(1)

        self.hint_label = QLabel(_MODE_HINTS[AppMode.COMMON_EDITING])
        self.hint_label.setProperty("role", "faint")
        layout.addWidget(self.hint_label)

        self._apply_styles()

    def _on_button_clicked(self) -> None:
        """Slot for every mode button.

        The clicked button carries its mode in the ``appMode`` property so
        no closure has to capture ``self``.
        """
        button = self.sender()
        if not isinstance(button, QPushButton):
            return
        raw = button.property("appMode")
        if not raw:
            return
        try:
            mode = AppMode(raw)
        except ValueError:
            return
        self._on_clicked(mode)

    def _on_clicked(self, mode: AppMode) -> None:
        if mode is self._mode:
            return
        self.set_mode(mode)
        self.modeChanged.emit(mode)

    def _apply_styles(self) -> None:
        for mode, button in self._buttons.items():
            active = mode is self._mode
            if active:
                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: {Palette.ACCENT};
                        color: #ffffff;
                        border: 1px solid {Palette.ACCENT};
                        border-radius: 5px;
                        padding: 6px 16px;
                        font-weight: 700;
                    }}
                    QPushButton:hover {{
                        background: {Palette.ACCENT_HOVER};
                    }}
                    """
                )
            else:
                button.setStyleSheet(
                    f"""
                    QPushButton {{
                        background: {Palette.BG_CARD};
                        color: {Palette.TEXT_MUTED};
                        border: 1px solid {Palette.BORDER_STRONG};
                        border-radius: 5px;
                        padding: 6px 16px;
                    }}
                    QPushButton:hover {{
                        background: {Palette.BG_CARD_HOVER};
                        color: {Palette.TEXT};
                        border-color: {Palette.BORDER_FOCUS};
                    }}
                    """
                )

    def set_mode(self, mode: AppMode) -> None:
        self._mode = mode
        for button_mode, button in self._buttons.items():
            button.setChecked(button_mode is mode)
        self.hint_label.setText(_MODE_HINTS.get(mode, ""))
        self._apply_styles()

    @property
    def mode(self) -> AppMode:
        return self._mode

    @property
    def current_mode(self) -> AppMode:
        """Alias for :attr:`mode`."""
        return self._mode

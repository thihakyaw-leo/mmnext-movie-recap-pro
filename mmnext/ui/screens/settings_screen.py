"""Settings screen.

Everything on this screen is local to the app. There is no account, no sync
and no telemetry - the page exists so the shell is complete and so the
demo-mode switch has somewhere to live.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import FrameFill, OutputRatio
from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader
from ..widgets.confirm import confirm_before_discard
from .base import BaseScreen, ScreenHeader

__all__ = ["SettingsScreen"]


class SettingsScreen(BaseScreen):
    """Local application settings."""

    screen_key = NavTarget.SETTINGS

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.layout.addWidget(
            ScreenHeader(
                "Settings",
                "Local preferences for the production workspace. Nothing here "
                "is uploaded anywhere.",
            )
        )

        # -- output ----------------------------------------------------------- #
        output_card = Card()
        output_card.add(
            CardHeader("Output", "Applies to the next render of the current project.")
        )

        form = QFormLayout()
        form.setSpacing(10)

        self.ratio_combo = QComboBox()
        for ratio in OutputRatio:
            self.ratio_combo.addItem(ratio.value, ratio.value)

        self.fill_combo = QComboBox()
        for fill in FrameFill:
            self.fill_combo.addItem(fill.value.title(), fill.value)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText(r"J:\Movies\The Last Signal\MMNext Output")

        form.addRow("Aspect ratio", self.ratio_combo)
        form.addRow("Frame fill", self.fill_combo)
        form.addRow("Output folder", self.output_edit)
        output_card.add_layout(form)
        self.layout.addWidget(output_card)

        # -- demo mode --------------------------------------------------------- #
        demo_card = Card()
        demo_card.add(
            CardHeader(
                "Demo mode",
                "Demo mode is always on in milestone 1 - every external "
                "capability is simulated.",
            )
        )

        demo_body = QVBoxLayout()
        demo_body.setSpacing(8)

        self.demo_check = QCheckBox("Run with simulated data (no network, no tools)")
        self.demo_check.setChecked(True)
        self.demo_check.setEnabled(False)

        self.reset_button = QPushButton("Reset the demo project")
        self.reset_button.clicked.connect(self._reset_demo)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "muted")

        demo_body.addWidget(self.demo_check)
        demo_body.addWidget(self.reset_button)
        demo_body.addWidget(self.status_label)
        demo_card.add_layout(demo_body)
        self.layout.addWidget(demo_card)

        # -- dependencies ------------------------------------------------------ #
        deps_card = Card()
        deps_card.add(
            CardHeader(
                "Optional dependencies",
                "The app is fully usable without any of these. When they are "
                "present the matching capability is unlocked.",
            )
        )

        deps = QVBoxLayout()
        deps.setSpacing(6)
        for name, purpose, state in (
            ("mpv", "Video preview playback", "not detected"),
            ("FFmpeg", "Render and split", "not detected"),
            ("Whisper", "Transcription", "not wired in this milestone"),
            ("Edge TTS", "Burmese narration audio", "not wired in this milestone"),
            ("yt-dlp", "YouTube download", "not wired in this milestone"),
        ):
            deps.addWidget(self._dependency_row(name, purpose, state))
        deps_card.add_layout(deps)
        self.layout.addWidget(deps_card)

        # -- diagnostics ------------------------------------------------------- #
        diag_card = Card()
        diag_card.add(
            CardHeader(
                "Diagnostics",
                "Runtime probe report for Python, tools, and environment.",
            )
        )
        diag_body = QVBoxLayout()
        self.diag_label = QLabel("")
        self.diag_label.setWordWrap(True)
        self.diag_button = QPushButton("Generate diagnostics report")
        self.diag_button.clicked.connect(self._generate_diag)
        diag_body.addWidget(self.diag_button)
        diag_body.addWidget(self.diag_label)
        diag_card.add_layout(diag_body)
        self.layout.addWidget(diag_card)

    def _generate_diag(self) -> None:
        if self._context is None:
            return
        from ...application.diagnostics_service import DiagnosticsService
        import json

        svc = DiagnosticsService(jobs_dir=getattr(self._context, "_jobs_dir", None))
        report = svc.report()
        self.diag_label.setText(json.dumps(report, indent=2))

    def _dependency_row(self, name: str, purpose: str, state: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        name_label = QLabel(name)
        name_label.setFixedWidth(110)
        name_label.setStyleSheet(f"color: {Palette.TEXT}; font-weight: 600;")

        purpose_label = QLabel(purpose)
        purpose_label.setProperty("role", "muted")

        state_label = QLabel(state)
        state_label.setProperty("role", "faint")

        layout.addWidget(name_label)
        layout.addWidget(purpose_label, 1)
        layout.addWidget(state_label)
        return row

    def _reset_demo(self) -> None:
        if self._context is None:
            return
        # Restoring the demo project throws every unsaved edit away, so the
        # user has to confirm before anything is discarded.
        if not confirm_before_discard(
            self, self._context, action="the demo project", allow_save=False
        ):
            self.status_label.setText("Reset cancelled - nothing was discarded.")
            self.status_label.setStyleSheet(f"color: {Palette.TEXT_MUTED};")
            return
        self._context.reset()
        self.status_label.setText("Demo project restored to its initial state.")
        self.status_label.setStyleSheet(f"color: {Palette.SUCCESS};")

    def on_bind(self, context) -> None:
        context.sessionChanged.connect(self._load_session)

    def _load_session(self) -> None:
        if self._context is None:
            return
        session = self._context.session
        if session is None:
            return
        index = self.ratio_combo.findData(session.output_ratio.value)
        if index >= 0:
            self.ratio_combo.setCurrentIndex(index)
        index = self.fill_combo.findData(session.frame_fill.value)
        if index >= 0:
            self.fill_combo.setCurrentIndex(index)
        self.output_edit.setText(session.output_folder)

"""Home screen - the entry point of the app.

Shows what the current build can do, what it deliberately cannot do yet, and
the two big "start" actions (import a file / paste a YouTube URL).
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader, StatTile
from .base import BaseScreen, ScreenHeader

__all__ = ["HomeScreen"]


class _FeatureRow(QWidget):
    """One 'available now' / 'coming later' row."""

    def __init__(
        self, name: str, detail: str, ready: bool, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(10)

        dot = QLabel("●")
        dot.setFixedWidth(14)
        color = Palette.SUCCESS if ready else Palette.TEXT_FAINT
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")

        name_label = QLabel(name)
        name_label.setFixedWidth(190)
        name_label.setStyleSheet(f"color: {Palette.TEXT}; font-weight: 600;")

        detail_label = QLabel(detail)
        detail_label.setProperty("role", "muted")
        detail_label.setWordWrap(True)

        layout.addWidget(dot)
        layout.addWidget(name_label)
        layout.addWidget(detail_label, 1)


class HomeScreen(BaseScreen):
    """Landing screen."""

    screen_key = NavTarget.HOME

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._context = None

        header = ScreenHeader(
            "MMNext Movie Recap Pro",
            "Milestone 1 - the complete editor shell, running on deterministic "
            "demo data. No API keys, no network, no FFmpeg, no mpv required.",
        )
        self.layout.addWidget(header)

        # -- quick actions --------------------------------------------------- #
        actions = Card()
        actions_header = CardHeader(
            "Quick start",
            "Pick how you want to bring a source in.",
        )
        actions.add(actions_header)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        self.import_button = QPushButton("Import a local video")
        self.import_button.setProperty("variant", "primary")
        self.import_button.setMinimumHeight(34)
        self.import_button.clicked.connect(self._emit_import)

        self.youtube_button = QPushButton("Paste a YouTube URL")
        self.youtube_button.setMinimumHeight(34)
        self.youtube_button.clicked.connect(self._emit_import)

        self.workspace_button = QPushButton("Open the workspace")
        self.workspace_button.setMinimumHeight(34)
        self.workspace_button.clicked.connect(self._emit_workspace)

        button_row.addWidget(self.import_button)
        button_row.addWidget(self.youtube_button)
        button_row.addWidget(self.workspace_button)
        button_row.addStretch(1)
        actions.add_layout(button_row)
        self.layout.addWidget(actions)

        # -- stats ------------------------------------------------------------ #
        stats = Card()
        stats.add(CardHeader("This project", "Live figures from the loaded demo."))
        stat_row = QGridLayout()
        stat_row.setSpacing(12)

        self.stat_segments = StatTile("Narration segments", "0")
        self.stat_rows = StatTile("Exact dubbing rows", "0")
        self.stat_parts = StatTile("Splitter parts", "0")
        self.stat_overlays = StatTile("Overlays", "0")

        stat_row.addWidget(self.stat_segments, 0, 0)
        stat_row.addWidget(self.stat_rows, 0, 1)
        stat_row.addWidget(self.stat_parts, 0, 2)
        stat_row.addWidget(self.stat_overlays, 0, 3)
        stats.add_layout(stat_row)
        self.layout.addWidget(stats)

        # -- capability matrix ------------------------------------------------ #
        capability = Card()
        capability.add(
            CardHeader(
                "What works today",
                "Milestone 1 ships the editor shell. Everything external is "
                "simulated on purpose.",
            )
        )

        ready = [
            ("Shell & navigation", "Six screens, one left rail, a bottom log drawer."),
            ("Import", "Local path or YouTube URL, validated before it is accepted."),
            ("Analyze", "Metadata, qualities and duration from a fixed fixture."),
            ("Download queue", "Simulated progress with pause / resume / stop / retry."),
            ("Production workspace", "Segment table, timeline, playhead, inspector."),
            ("Mode switcher", "Four modes, each with its own working set."),
        ]
        later = [
            ("Whisper transcription", "Not wired yet - the transcript is a fixture."),
            ("Burmese translation", "Not wired yet - the rows are pre-filled."),
            ("Edge TTS synthesis", "Not wired yet - no audio is produced."),
            ("FFmpeg render", "Not wired yet - renders are simulated."),
            ("YouTube download", "Not wired yet - the queue is a simulation."),
        ]

        for name, detail in ready:
            capability.add(_FeatureRow(name, detail, ready=True))
        capability.add(QLabel(""))
        unavailable = QLabel("NOT WIRED IN THIS MILESTONE")
        unavailable.setProperty("role", "sectionTitle")
        capability.add(unavailable)
        for name, detail in later:
            capability.add(_FeatureRow(name, detail, ready=False))

        self.layout.addWidget(capability)
        self.layout.addStretch(1)

    # -- context binding ---------------------------------------------------- #

    def on_bind(self, context) -> None:
        # The context is stored on the widget and the slots below accept
        # (and ignore) the signal payloads. Connecting a lambda that
        # captures ``self`` would create a reference cycle that keeps the
        # screen alive past interpreter shutdown and aborts Qt teardown.
        self._context = context
        context.sessionChanged.connect(self._on_session_changed)
        context.metadataChanged.connect(self._on_metadata_changed)
        self._refresh_stats(context)

    def _on_session_changed(self) -> None:
        if self._context is not None:
            self._refresh_stats(self._context)

    def _on_metadata_changed(self, _metadata) -> None:
        if self._context is not None:
            self._refresh_stats(self._context)

    def _refresh_stats(self, context) -> None:
        session = context.session
        if session is None:
            self.stat_segments.set_value("0")
            self.stat_rows.set_value("0")
            self.stat_parts.set_value("0")
            self.stat_overlays.set_value("0")
            return
        self.stat_segments.set_value(str(len(session.narration_segments)))
        self.stat_rows.set_value(str(len(session.exact_dubbing_rows)))
        self.stat_parts.set_value(str(len(session.split_parts)))
        self.stat_overlays.set_value(str(len(session.overlays)))

    def _emit_import(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to(NavTarget.IMPORT)

    def _emit_workspace(self) -> None:
        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to(NavTarget.WORKSPACE)

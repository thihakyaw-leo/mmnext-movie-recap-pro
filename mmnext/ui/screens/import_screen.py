"""Import screen - bring a local file or a YouTube URL into the project.

The screen validates the input before anything is accepted, then hands the
result to the application layer. In demo mode nothing is written to disk and
no network call is made.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...domain.enums import SourceType
from ...domain.models import VideoSource
from ...services.demo.demo_providers import is_youtube
from ..navigation.nav_rail import NavTarget
from ..theme.palette import Palette
from ..widgets.card import Card, CardHeader
from .base import BaseScreen, ScreenHeader

__all__ = ["ImportScreen"]


class ImportScreen(BaseScreen):
    """Local file / YouTube URL intake."""

    screen_key = NavTarget.IMPORT

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.layout.addWidget(
            ScreenHeader(
                "Import a source",
                "Choose a video already on this machine, or paste a YouTube "
                "URL. In demo mode the source is never read - the app only "
                "records what you picked.",
            )
        )

        # -- local file ------------------------------------------------------ #
        local_card = Card()
        local_card.add(
            CardHeader(
                "Local video",
                "Point at a file on disk. The path is validated, not opened.",
            )
        )

        local_row = QHBoxLayout()
        local_row.setSpacing(8)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"J:\Movies\The Last Signal\The Last Signal - E07.mp4")
        self.path_edit.setClearButtonEnabled(True)

        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._browse)

        local_row.addWidget(self.path_edit, 1)
        local_row.addWidget(self.browse_button)
        local_card.add_layout(local_row)
        self.layout.addWidget(local_card)

        # -- youtube --------------------------------------------------------- #
        yt_card = Card()
        yt_card.add(
            CardHeader(
                "YouTube URL",
                "Standard watch, shorts and youtu.be links are recognised.",
            )
        )

        yt_row = QHBoxLayout()
        yt_row.setSpacing(8)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        )
        self.url_edit.setClearButtonEnabled(True)

        self.paste_button = QPushButton("Paste")
        self.paste_button.clicked.connect(self._paste)

        self.use_demo_button = QPushButton("Use demo URL")
        self.use_demo_button.setProperty("variant", "ghost")
        self.use_demo_button.clicked.connect(self._use_demo_url)

        yt_row.addWidget(self.url_edit, 1)
        yt_row.addWidget(self.paste_button)
        yt_row.addWidget(self.use_demo_button)
        yt_card.add_layout(yt_row)
        self.layout.addWidget(yt_card)

        # -- action ---------------------------------------------------------- #
        action_card = Card()
        action_card.add(CardHeader("Next step"))

        action_row = QHBoxLayout()
        action_row.setSpacing(10)

        self.import_button = QPushButton("Import and analyze")
        self.import_button.setProperty("variant", "primary")
        self.import_button.setMinimumHeight(34)
        self.import_button.clicked.connect(self._import_clicked)

        self.reset_button = QPushButton("Clear")
        self.reset_button.clicked.connect(self._reset)

        action_row.addWidget(self.import_button)
        action_row.addWidget(self.reset_button)
        action_row.addStretch(1)
        action_card.add_layout(action_row)

        self.status_label = QLabel("")
        self.status_label.setProperty("role", "muted")
        self.status_label.setWordWrap(True)
        action_card.add(self.status_label)
        self.layout.addWidget(action_card)

        self.layout.addStretch(1)

    # -- helpers ------------------------------------------------------------ #
    def _browse(self) -> None:
        start_dir = str(Path.home())
        if self.path_edit.text().strip():
            candidate = Path(self.path_edit.text().strip())
            if candidate.parent.exists():
                start_dir = str(candidate.parent)
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select a video file",
            start_dir,
            "Video files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _paste(self) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            self.url_edit.setText(clipboard.text().strip())

    def _use_demo_url(self) -> None:
        self.url_edit.setText("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self._set_status("Demo URL loaded.", Palette.TEXT_MUTED)

    def _reset(self) -> None:
        self.path_edit.clear()
        self.url_edit.clear()
        self._set_status("", Palette.TEXT_MUTED)

    def _set_status(self, text: str, color: str = Palette.TEXT_MUTED) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color};")

    # -- import ------------------------------------------------------------- #
    def _import_clicked(self) -> None:
        if self._context is None:
            return

        path = self.path_edit.text().strip()
        url = self.url_edit.text().strip()

        if path:
            if not Path(path).exists():
                self._set_status(
                    f"'{path}' does not exist. Pick an existing file or use the "
                    "demo URL instead.",
                    Palette.DANGER,
                )
                return
            source = VideoSource.local(path)
            source.duration_s = 0.0
        elif url:
            if not is_youtube(url):
                self._set_status(
                    "That does not look like a YouTube link. Expected a "
                    "youtube.com or youtu.be URL.",
                    Palette.DANGER,
                )
                return
            source = VideoSource.youtube(url)
        else:
            self._set_status(
                "Choose a local file or paste a YouTube URL first.",
                Palette.WARNING,
            )
            return

        self._context.set_source(source)
        self._context.analyze(source)
        self._set_status("Imported. Metadata loaded from the demo fixture.",
                         Palette.SUCCESS)

        parent = self.window()
        if parent is not None and hasattr(parent, "navigate_to"):
            parent.navigate_to(NavTarget.ANALYZE)

    def on_bind(self, context) -> None:
        context.sourceChanged.connect(self._on_source_changed)

    def _on_source_changed(self, source: VideoSource) -> None:
        if source.source_type is SourceType.LOCAL_FILE:
            self.path_edit.setText(source.location)
        else:
            self.url_edit.setText(source.location)

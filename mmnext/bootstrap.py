"""Application bootstrap.

This is the one place that knows how to assemble the app: it creates the
:class:`~PySide6.QtWidgets.QApplication`, applies the dark theme and the
Myanmar-capable font stack, and returns the main window.

Keeping it separate from :mod:`mmnext.main` means the test-suite can build
the application without running the event loop.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .ui.theme.stylesheet import app_font, build_stylesheet

__all__ = ["create_application", "create_main_window", "bootstrap"]


def create_application(argv: Optional[list[str]] = None) -> QApplication:
    """Return the process-wide :class:`QApplication`.

    If an instance already exists it is reused, so calling this twice in a
    test session is safe.
    """
    existing = QApplication.instance()
    if existing is not None:
        app = existing
    else:
        app = QApplication(argv if argv is not None else [])

    font = QFont(app_font())
    app.setFont(font)
    app.setStyleSheet(build_stylesheet())
    app.setApplicationName("MMNext Movie Recap Pro")
    app.setOrganizationName("MMNext")
    return app


def create_main_window(app: Optional[QApplication] = None) -> MainWindow:
    """Build the main window with the demo project already loaded."""
    if app is None:
        app = create_application()
    return MainWindow()


def bootstrap(argv: Optional[list[str]] = None) -> int:
    """Start the GUI event loop. Returns the Qt exit code."""
    app = create_application(argv)
    window = create_main_window(app)
    window.show()
    return app.exec()

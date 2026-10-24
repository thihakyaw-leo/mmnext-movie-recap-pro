"""Application stylesheet.

One Qt stylesheet drives the whole app. Widgets stay unstyled in code and the
look lives here, which keeps the individual screen modules readable.
"""

from __future__ import annotations

from .fonts import MONO_FONT_FAMILIES, UI_FONT_FAMILIES, pick_family
from .palette import Palette

__all__ = ["build_stylesheet", "app_font", "mono_font"]


def app_font() -> str:
    """The resolved UI family name."""
    return pick_family(UI_FONT_FAMILIES)


def mono_font() -> str:
    """The resolved monospace family name."""
    return pick_family(MONO_FONT_FAMILIES)


def build_stylesheet() -> str:
    """Return the global Qt stylesheet."""
    return f"""
/* ---------------------------------------------------------------- base --- */
QWidget {{
    background: {Palette.BG_APP};
    color: {Palette.TEXT};
    font-family: "{app_font()}";
    font-size: 13px;
}}

QToolTip {{
    background: {Palette.BG_ELEVATED};
    color: {Palette.TEXT};
    border: 1px solid {Palette.BORDER_STRONG};
    padding: 4px 6px;
}}

QMainWindow::separator {{
    background: {Palette.BORDER};
    width: 1px;
    height: 1px;
}}

/* ------------------------------------------------------------- labels ---- */
QLabel {{
    background: transparent;
}}

QLabel[role="h1"] {{
    font-size: 22px;
    font-weight: 600;
    color: {Palette.TEXT};
}}

QLabel[role="h2"] {{
    font-size: 16px;
    font-weight: 600;
    color: {Palette.TEXT};
}}

QLabel[role="h3"] {{
    font-size: 13px;
    font-weight: 600;
    color: {Palette.TEXT};
}}

QLabel[role="muted"] {{
    color: {Palette.TEXT_MUTED};
}}

QLabel[role="faint"] {{
    color: {Palette.TEXT_FAINT};
}}

QLabel[role="mono"] {{
    font-family: "{mono_font()}";
}}

QLabel[role="sectionTitle"] {{
    color: {Palette.TEXT_FAINT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

QLabel[role="warning"] {{
    color: {Palette.WARNING};
    background: transparent;
    font-size: 12px;
}}

/* ------------------------------------------------------------- buttons --- */
QPushButton {{
    background: {Palette.BG_ELEVATED};
    color: {Palette.TEXT};
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 5px;
    padding: 6px 14px;
    min-height: 18px;
}}

QPushButton:hover {{
    background: {Palette.BG_CARD_HOVER};
    border-color: {Palette.BORDER_FOCUS};
}}

QPushButton:pressed {{
    background: {Palette.ACCENT_SUNKEN};
}}

QPushButton:disabled {{
    color: {Palette.TEXT_FAINT};
    background: {Palette.BG_CARD};
    border-color: {Palette.BORDER};
}}

QPushButton[variant="primary"] {{
    background: {Palette.ACCENT};
    border-color: {Palette.ACCENT};
    color: #ffffff;
    font-weight: 600;
}}

QPushButton[variant="primary"]:hover {{
    background: {Palette.ACCENT_HOVER};
    border-color: {Palette.ACCENT_HOVER};
}}

QPushButton[variant="primary"]:disabled {{
    background: {Palette.ACCENT_SUNKEN};
    border-color: {Palette.ACCENT_SUNKEN};
    color: {Palette.TEXT_FAINT};
}}

QPushButton[variant="danger"] {{
    background: {Palette.DANGER_SOFT};
    border-color: {Palette.DANGER};
    color: {Palette.DANGER};
}}

QPushButton[variant="danger"]:hover {{
    background: {Palette.DANGER};
    color: {Palette.TEXT_INVERSE};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {Palette.TEXT_MUTED};
    padding: 6px 10px;
}}

QPushButton[variant="ghost"]:hover {{
    background: {Palette.BG_CARD};
    color: {Palette.TEXT};
}}

QPushButton[variant="ghost"]:disabled {{
    background: transparent;
    color: {Palette.TEXT_FAINT};
}}

/* --------------------------------------------------------------- input --- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {Palette.BG_INPUT};
    color: {Palette.TEXT};
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 5px;
    padding: 6px 8px;
    selection-background-color: {Palette.ACCENT_SUNKEN};
    selection-color: {Palette.TEXT};
}}

QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {Palette.BORDER_FOCUS};
}}

QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
    color: {Palette.TEXT_FAINT};
    background: {Palette.BG_CARD};
}}

QComboBox::drop-down {{
    border: none;
    width: 18px;
}}

QComboBox QAbstractItemView {{
    background: {Palette.BG_ELEVATED};
    border: 1px solid {Palette.BORDER_STRONG};
    selection-background-color: {Palette.ACCENT_SUNKEN};
    selection-color: {Palette.TEXT};
    outline: none;
}}

/* ------------------------------------------------------------- checkbox -- */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 3px;
    background: {Palette.BG_INPUT};
}}

QCheckBox::indicator:checked {{
    background: {Palette.ACCENT};
    border-color: {Palette.ACCENT};
}}

/* -------------------------------------------------------------- tables --- */
QTableView, QTreeView, QListView {{
    background: {Palette.BG_CARD};
    alternate-background-color: {Palette.BG_PANEL};
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    gridline-color: {Palette.BORDER};
    selection-background-color: {Palette.ACCENT_SUNKEN};
    selection-color: {Palette.TEXT};
    outline: none;
}}

QTableView::item, QTreeView::item, QListView::item {{
    padding: 3px 4px;
    border: none;
}}

QTableView::item:selected, QTreeView::item:selected {{
    background: {Palette.ACCENT_SUNKEN};
    color: {Palette.TEXT};
}}

QHeaderView::section {{
    background: {Palette.BG_TOOLBAR};
    color: {Palette.TEXT_MUTED};
    border: none;
    border-right: 1px solid {Palette.BORDER};
    border-bottom: 1px solid {Palette.BORDER};
    padding: 6px 8px;
    font-weight: 600;
}}

QHeaderView::section:last {{
    border-right: none;
}}

/* ------------------------------------------------------------ scrollbar -- */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {Palette.BORDER_STRONG};
    border-radius: 5px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {Palette.TEXT_FAINT};
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {Palette.BORDER_STRONG};
    border-radius: 5px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {Palette.TEXT_FAINT};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ------------------------------------------------------------ progress --- */
QProgressBar {{
    background: {Palette.BG_INPUT};
    border: 1px solid {Palette.BORDER};
    border-radius: 5px;
    height: 8px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background: {Palette.ACCENT};
    border-radius: 4px;
}}

/* -------------------------------------------------------------- sliders -- */
QSlider::groove:horizontal {{
    background: {Palette.BG_INPUT};
    height: 4px;
    border-radius: 2px;
}}

QSlider::sub-page:horizontal {{
    background: {Palette.ACCENT};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {Palette.TEXT};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}

/* ---------------------------------------------------------------- tabs --- */
QTabWidget::pane {{
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    background: {Palette.BG_PANEL};
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    color: {Palette.TEXT_MUTED};
    padding: 7px 16px;
    border: 1px solid transparent;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:selected {{
    background: {Palette.BG_PANEL};
    color: {Palette.TEXT};
    border-color: {Palette.BORDER};
    border-bottom-color: {Palette.BG_PANEL};
}}

QTabBar::tab:hover:!selected {{
    color: {Palette.TEXT};
}}

/* -------------------------------------------------------------- groups --- */
QGroupBox {{
    border: 1px solid {Palette.BORDER};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {Palette.TEXT_MUTED};
}}

/* --------------------------------------------------------------- menus --- */
QMenuBar {{
    background: {Palette.BG_TOOLBAR};
    border-bottom: 1px solid {Palette.BORDER};
}}

QMenuBar::item:selected {{
    background: {Palette.BG_CARD_HOVER};
}}

QMenu {{
    background: {Palette.BG_ELEVATED};
    border: 1px solid {Palette.BORDER_STRONG};
    border-radius: 6px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background: {Palette.ACCENT_SUNKEN};
}}

/* -------------------------------------------------------------- splitters */
QSplitter::handle {{
    background: {Palette.BORDER};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QSplitter::handle:hover {{
    background: {Palette.BORDER_FOCUS};
}}

/* ---------------------------------------------------------------- misc --- */
QStatusBar {{
    background: {Palette.BG_TOOLBAR};
    border-top: 1px solid {Palette.BORDER};
    color: {Palette.TEXT_MUTED};
}}

QStatusBar::item {{
    border: none;
}}

QPlainTextEdit[role="log"] {{
    background: {Palette.BG_TIMELINE};
    font-family: "{mono_font()}";
    font-size: 12px;
    color: {Palette.TEXT_MUTED};
    border: none;
}}
"""

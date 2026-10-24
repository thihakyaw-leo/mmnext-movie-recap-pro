"""Theme package: palette, fonts and the global stylesheet."""

from __future__ import annotations

from .fonts import FontSpec, MONO_FONT_FAMILIES, UI_FONT_FAMILIES, pick_family
from .palette import (
    JOB_STATE_COLORS,
    Palette,
    SEVERITY_COLORS,
    TASK_STATE_COLORS,
)
from .stylesheet import app_font, build_stylesheet, mono_font

__all__ = [
    "FontSpec",
    "UI_FONT_FAMILIES",
    "MONO_FONT_FAMILIES",
    "pick_family",
    "Palette",
    "SEVERITY_COLORS",
    "JOB_STATE_COLORS",
    "TASK_STATE_COLORS",
    "build_stylesheet",
    "app_font",
    "mono_font",
]

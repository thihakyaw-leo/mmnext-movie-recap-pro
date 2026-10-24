"""Font stack for the editor UI.

The UI has to render Burmese (Myanmar script) correctly, so the family list
always ends with fonts that ship Myanmar glyphs. On Windows the usual
candidates are ``Myanmar Text`` (Windows 10/11) and ``Padauk`` /
``Noto Sans Myanmar`` when installed.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FontSpec", "UI_FONT_FAMILIES", "MONO_FONT_FAMILIES", "pick_family"]


@dataclass(frozen=True, slots=True)
class FontSpec:
    family: str
    size: int
    bold: bool = False
    italic: bool = False


#: Ordered fallback list for UI text. The first available family wins.
UI_FONT_FAMILIES: tuple[str, ...] = (
    "Myanmar Text",
    "Noto Sans Myanmar",
    "Padauk",
    "Segoe UI",
    "Tahoma",
    "Arial",
    "Sans Serif",
)

#: Monospace stack used for timecodes and log output.
MONO_FONT_FAMILIES: tuple[str, ...] = (
    "Cascadia Mono",
    "Consolas",
    "Courier New",
    "DejaVu Sans Mono",
    "Monospace",
)


def pick_family(candidates: tuple[str, ...] = UI_FONT_FAMILIES) -> str:
    """Return the first candidate family that is actually installed.

    Falls back to the last entry, which Qt resolves generically.
    """
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:  # pragma: no cover - Qt always present in the UI layer
        return candidates[-1]

    try:
        available = set(QFontDatabase.families())
    except Exception:  # pragma: no cover
        return candidates[-1]

    for family in candidates:
        if family in available:
            return family
    return candidates[-1]

"""Colour palette for the dark professional editor theme.

The palette is a small, explicit set of tokens. Widgets never hard-code a
hex value - they reference these names so the whole app can be re-skinned
from one place.
"""

from __future__ import annotations

__all__ = ["Palette", "SEVERITY_COLORS", "JOB_STATE_COLORS", "TASK_STATE_COLORS"]


class Palette:
    """Dark editor palette (a charcoal / slate base with a single accent)."""

    # -- surfaces ----------------------------------------------------------- #
    BG_APP = "#0d1117"        # window background
    BG_RAIL = "#0a0e14"        # left navigation rail
    BG_PANEL = "#11161d"      # side panels, inspector
    BG_CARD = "#151b24"       # cards
    BG_CARD_HOVER = "#1b2330"
    BG_INPUT = "#0f141b"
    BG_ELEVATED = "#1a212c"
    BG_TIMELINE = "#0b1017"
    BG_TOOLBAR = "#121820"

    # -- lines ------------------------------------------------------------- #
    BORDER = "#212a36"
    BORDER_STRONG = "#2d3846"
    BORDER_FOCUS = "#3d7bfd"

    # -- text -------------------------------------------------------------- #
    TEXT = "#e6edf3"
    TEXT_MUTED = "#9aa7b4"
    TEXT_FAINT = "#6b7785"
    TEXT_INVERSE = "#0d1117"

    # -- accents ----------------------------------------------------------- #
    ACCENT = "#3d7bfd"
    ACCENT_HOVER = "#5a90ff"
    ACCENT_SUNKEN = "#1f3a75"
    ACCENT_SOFT = "#16233d"

    # -- semantic ---------------------------------------------------------- #
    SUCCESS = "#2ea043"
    SUCCESS_SOFT = "#12261a"
    WARNING = "#d29922"
    WARNING_SOFT = "#2b2211"
    DANGER = "#f85149"
    DANGER_SOFT = "#2d1618"
    INFO = "#58a6ff"
    INFO_SOFT = "#10243b"
    NEUTRAL = "#6b7785"
    NEUTRAL_SOFT = "#171d26"

    # -- playback / timeline ----------------------------------------------- #
    PLAYHEAD = "#ff7b72"
    TIMELINE_TRACK = "#1b2330"
    TIMELINE_SELECTED = "#2b4c8f"
    TIMELINE_MARKER = "#d29922"
    WAVEFORM = "#3d7bfd"
    WAVEFORM_DIM = "#24334d"


SEVERITY_COLORS: dict[str, str] = {
    "info": Palette.INFO,
    "warning": Palette.WARNING,
    "error": Palette.DANGER,
}

JOB_STATE_COLORS: dict[str, str] = {
    "new": Palette.NEUTRAL,
    "source_analyzed": Palette.INFO,
    "download_queued": Palette.NEUTRAL,
    "downloading": Palette.ACCENT,
    "download_paused": Palette.WARNING,
    "download_stopped": Palette.NEUTRAL,
    "download_failed": Palette.DANGER,
    "downloaded": Palette.SUCCESS,
    "preparing": Palette.ACCENT,
    "awaiting_translation_or_edit": Palette.WARNING,
    "validating": Palette.ACCENT,
    "ready_to_render": Palette.INFO,
    "rendering": Palette.ACCENT,
    "complete": Palette.SUCCESS,
    "failed": Palette.DANGER,
    "stop_requested": Palette.WARNING,
    "cancelled": Palette.NEUTRAL,
}

TASK_STATE_COLORS: dict[str, str] = {
    "queued": Palette.NEUTRAL,
    "running": Palette.ACCENT,
    "pause_requested": Palette.WARNING,
    "paused": Palette.WARNING,
    "stop_requested": Palette.WARNING,
    "stopped": Palette.NEUTRAL,
    "failed": Palette.DANGER,
    "complete": Palette.SUCCESS,
    "cancelled": Palette.NEUTRAL,
}

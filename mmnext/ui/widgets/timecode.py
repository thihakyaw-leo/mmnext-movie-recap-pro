"""Timecode helpers.

The legacy pipelines stored seconds as floats and formatted them as
``HH:MM:SS.mmm``. The UI uses the same convention everywhere so a timecode
shown in the timeline, the inspector and the segment list always agree.
"""

from __future__ import annotations

__all__ = ["format_timecode", "format_duration", "parse_timecode"]


def format_timecode(seconds: float, *, millis: bool = True) -> str:
    """Format ``seconds`` as ``HH:MM:SS`` (or ``HH:MM:SS.mmm``)."""
    if seconds is None:
        seconds = 0.0
    negative = seconds < 0
    total = abs(float(seconds))
    hours, rem = divmod(int(total), 3600)
    minutes, secs = divmod(rem, 60)
    if millis:
        ms = int(round((total - int(total)) * 1000))
        if ms == 1000:  # rounding overflow
            ms = 0
            secs += 1
            if secs == 60:
                secs = 0
                minutes += 1
                if minutes == 60:
                    minutes = 0
                    hours += 1
        text = f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"
    else:
        text = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"-{text}" if negative else text


def format_duration(seconds: float) -> str:
    """Human duration: ``1h 54m 35s`` / ``4m 12s`` / ``12s``."""
    total = int(max(0.0, float(seconds or 0.0)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def parse_timecode(text: str) -> float:
    """Parse ``HH:MM:SS[.mmm]`` or ``MM:SS`` into seconds.

    Returns ``0.0`` for unparsable input rather than raising, because the
    value can come from a user-typed field.
    """
    if not text:
        return 0.0
    cleaned = text.strip()
    try:
        parts = cleaned.split(":")
        if len(parts) == 3:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes = float(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
        return float(cleaned)
    except ValueError:
        return 0.0

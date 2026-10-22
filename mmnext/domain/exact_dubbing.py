"""Pure exact-dubbing contract: schema, validation and speech fitting maths.

This module is the single source of truth for the *exact dubbing* rules that
the legacy ``movie-recap`` pipeline enforced:

* ``translated_gender.json`` is a JSON **array**, one row per source segment,
  in the original order, with the keys ``id``, ``start``, ``duration``,
  ``original``, ``burmese`` and ``gender``;
* ``id``, ``original``, ``start`` and ``duration`` are **immutable** - they
  must match the source segment exactly (``start``/``duration`` within
  ``1e-6``);
* ``burmese`` must be a non-blank string that contains real Myanmar Unicode
  (never Zawgyi, never a row that is still English);
* ``gender`` is one of ``male`` / ``female`` / ``unknown`` and selects the
  Edge TTS Myanmar voice.  ``unknown`` deliberately shares the female voice.

It also owns the two pieces of maths the renderer needs: the *speech window*
(how far a row may expand into the silence before the next row) and the
``atempo`` chain (pitch-preserving speed fitting).

The module imports no Qt, no application and no infrastructure code.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

__all__ = [
    "EXACT_DUB_VOICES",
    "MYANMAR_UNICODE_PATTERN",
    "TIMING_TOLERANCE",
    "DubbingTranslation",
    "atempo_chain",
    "cache_signature",
    "parse_translated_gender",
    "speech_window",
    "validate_against_source",
    "voice_for_gender",
]

#: Myanmar block (U+1000-U+109F) plus Myanmar Extended-A (U+AA60-U+AA7F).
MYANMAR_UNICODE_PATTERN = re.compile(r"[\u1000-\u109f\uaa60-\uaa7f]")

#: Gender -> Edge TTS Myanmar voice (legacy ``movie-recap`` mapping).
EXACT_DUB_VOICES: dict[str, str] = {
    "male": "my-MM-ThihaNeural",
    "female": "my-MM-NilarNeural",
    # An uncertain speaker falls back to the female voice, exactly like the
    # legacy pipeline.  It is never derived from biometric analysis.
    "unknown": "my-MM-NilarNeural",
}

#: Source timing may never drift by more than this (seconds).
TIMING_TOLERANCE = 1e-6

_VALID_GENDERS = frozenset(EXACT_DUB_VOICES)


@dataclass(frozen=True, slots=True)
class DubbingTranslation:
    """One validated ``translated_gender.json`` row.

    ``id`` is the legacy positional index (an ``int``) or the source row id
    (a ``str``); both are accepted, and ``validate_against_source`` checks the
    row against its source segment either way.  ``row_id`` is the optional
    extra key that carries the source row id when the file was written by
    MMNext; the legacy pipeline tolerates unknown keys.
    """

    id: int | str
    start: float
    duration: float
    original: str
    burmese: str
    gender: str
    row_id: str = ""

    @property
    def end(self) -> float:
        return self.start + self.duration

    @property
    def voice(self) -> str:
        return voice_for_gender(self.gender)


def voice_for_gender(gender: Any) -> str:
    """Return the Edge TTS Myanmar voice for ``gender``."""
    value = getattr(gender, "value", gender)
    key = str(value or "unknown").strip().lower()
    return EXACT_DUB_VOICES.get(key, EXACT_DUB_VOICES["unknown"])


def cache_signature(voice: str, text: str) -> str:
    """Return the content-addressed cache signature of one speech row.

    Only the voice and the Burmese text participate, so changing either one
    invalidates the cached audio while re-ordering the rows does not.
    """
    raw = f"{voice}\n{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_number(value: Any) -> bool:
    """Whether ``value`` is a real number (``bool`` is not a number here)."""
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def parse_translated_gender(payload: Any) -> list[DubbingTranslation]:
    """Validate and parse a ``translated_gender.json`` payload.

    Raises :class:`ValueError` with a precise message for every rejected
    shape: a wrong container type, a missing key, a non-finite number, an
    empty Burmese text, a row that still contains Latin text only, or an
    unknown gender.
    """
    if not isinstance(payload, list):
        raise ValueError("translated_gender.json must contain a JSON array of rows")
    if not payload:
        raise ValueError("translated_gender.json contains no rows")

    rows: list[DubbingTranslation] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Row {index}: expected an object")
        for key in ("id", "start", "duration", "original", "burmese", "gender"):
            if key not in raw:
                raise ValueError(f"Row {index}: missing key {key!r}")

        row_id = raw["id"]
        if isinstance(row_id, bool) or not isinstance(row_id, (int, str)):
            raise ValueError(f"Row {index}: id must be an integer or a string")
        if isinstance(row_id, str) and not row_id.strip():
            raise ValueError(f"Row {index}: id must not be empty")

        for key in ("start", "duration"):
            if not _is_number(raw[key]):
                raise ValueError(f"Row {index}: {key} must be a finite number")

        start = float(raw["start"])
        duration = float(raw["duration"])
        if start < 0 or duration <= 0:
            raise ValueError(f"Row {index}: start must be >= 0 and duration > 0")

        original = raw["original"]
        if not isinstance(original, str):
            raise ValueError(f"Row {index}: original must be a string")

        burmese = raw["burmese"]
        if not isinstance(burmese, str) or not burmese.strip():
            raise ValueError(f"Row {index}: Burmese translation is missing")
        if not MYANMAR_UNICODE_PATTERN.search(burmese):
            raise ValueError(
                f"Row {index}: Burmese translation must contain Myanmar Unicode"
            )

        gender = raw["gender"]
        if not isinstance(gender, str) or gender not in _VALID_GENDERS:
            raise ValueError(
                f"Row {index}: gender must be male, female or unknown"
            )

        rows.append(
            DubbingTranslation(
                id=row_id,
                start=start,
                duration=duration,
                original=original,
                burmese=burmese,
                gender=gender,
                row_id=str(raw.get("row_id", "") or ""),
            )
        )
    return rows


def _source_identifier(source: Any) -> str:
    """Return the source row's identifier as a string."""
    for key in ("row_id", "id", "segment_id"):
        value = getattr(source, key, None)
        if value is None and isinstance(source, Mapping):
            value = source.get(key)
        if value is not None:
            return str(value)
    return ""


def _source_text(source: Any) -> Optional[str]:
    """Return the source row's original text."""
    for key in ("original", "text"):
        value = getattr(source, key, None)
        if value is None and isinstance(source, Mapping):
            value = source.get(key)
        if value is not None:
            return str(value)
    return None


def validate_against_source(
    rows: Sequence[DubbingTranslation],
    source_rows: Sequence[Any],
) -> None:
    """Check that the translation never changed a locked source field.

    ``source_rows`` are the source segments (anything with an identifier and a
    source text).  The count, the order and the identifier must match, and
    ``start``/``duration`` must match within :data:`TIMING_TOLERANCE`.  An
    integer ``id`` is the legacy positional index; a string ``id`` is the
    source row id.  Nothing is ever repaired silently.
    """
    if len(rows) != len(source_rows):
        raise ValueError(
            f"Translation must contain all {len(source_rows)} segments, "
            f"in original order (got {len(rows)})."
        )
    for index, (row, source) in enumerate(zip(rows, source_rows)):
        source_id = _source_identifier(source)
        if isinstance(row.id, int):
            if row.id != index:
                raise ValueError(
                    f"Segment {index}: id mismatch (expected the positional id {index})."
                )
        elif str(row.id) != source_id:
            raise ValueError(f"Segment {source_id}: id mismatch.")
        if row.row_id and source_id and row.row_id != source_id:
            raise ValueError(f"Segment {source_id}: row_id mismatch.")
        source_text = _source_text(source)
        if source_text is None:
            raise ValueError(f"Segment {source_id}: source text is unusable")
        if row.original != source_text:
            raise ValueError(f"Segment {source_id}: original mismatch.")
        for key, value in (("start", row.start), ("duration", row.duration)):
            expected = getattr(source, key, None)
            if expected is None and isinstance(source, Mapping):
                expected = source.get(key)
            if not _is_number(expected):
                raise ValueError(f"Segment {source_id}: source {key} is unusable")
            if abs(value - float(expected)) > TIMING_TOLERANCE:
                raise ValueError(f"Segment {source_id}: changed {key}.")


def speech_window(
    start: float,
    duration: float,
    next_start: Optional[float],
    total: float,
) -> float:
    """Return how many seconds of speech a row may occupy.

    A row may expand into 80 % of the silent gap before the next row, but it
    can never overlap the next row and never runs past the end of the media.
    """
    target = float(duration)
    if next_start is not None:
        gap = float(next_start) - (float(start) + target)
        target = min(target + max(0.0, gap * 0.8), float(next_start) - float(start))
    return min(target, float(total) - float(start))


def atempo_chain(ratio: float) -> str:
    """Return an FFmpeg ``atempo`` filter chain for ``ratio``.

    ``atempo`` only accepts values up to 2.0 per instance, so a faster ratio
    needs a chain.  The chain keeps the pitch, unlike a naive resample.
    """
    value = float(ratio)
    if value <= 0:
        raise ValueError("atempo ratio must be positive")
    parts: list[str] = []
    while value > 2:
        parts.append("atempo=2")
        value /= 2
    parts.append(f"atempo={value:.9f}")
    return ",".join(parts)


def windows_for_rows(
    rows: Sequence[DubbingTranslation],
    total: float,
) -> list[float]:
    """Return the speech window of every row, in order."""
    windows: list[float] = []
    for index, row in enumerate(rows):
        next_start = rows[index + 1].start if index + 1 < len(rows) else None
        windows.append(speech_window(row.start, row.duration, next_start, total))
    return windows


def iter_genders(rows: Iterable[Any]) -> list[str]:
    """Return the gender of every row as a plain string."""
    return [str(getattr(row, "gender", "unknown")) for row in rows]

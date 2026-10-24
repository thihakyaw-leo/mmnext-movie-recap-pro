"""Validation rules.

The exact-dubbing rules reproduce the legacy ``movie-recap`` invariants
exactly, because those are a hard contract:

  * row count and order must match the source transcript;
  * ``id`` and ``original`` are immutable;
  * ``start`` / ``duration`` must match the source within 1e-6;
  * ``burmese`` must be non-empty and contain Myanmar codepoints;
  * ``gender`` must be one of male / female / unknown;
  * a source-duration drift greater than 0.05 s blocks rendering.

The narrator rules mirror ``narration_problems`` from the legacy editor.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from .enums import Severity
from .models import (
    ExactDubbingRow,
    NarrationSegment,
    TranscriptRow,
    ValidationIssue,
    ValidationReport,
)

__all__ = [
    "MYANMAR_BURMESE_RE",
    "MYANMAR_DIGIT_RE",
    "MYANMAR_SCRIPT_RE",
    "LATIN_SCRIPT_RE",
    "TIMESTAMP_EPSILON",
    "MAX_DURATION_DRIFT",
    "is_burmese",
    "has_myanmar_digits",
    "has_mixed_script",
    "validate_exact_dubbing",
    "validate_narration",
    "validate_source_duration",
]

#: Myanmar block U+1000-U+109F plus extended U+AA60-U+AA7F.
MYANMAR_SCRIPT_RE = re.compile(r"[\u1000-\u109f\uaa60-\uaa7f]")

#: Backwards compatible alias - the original public name.
MYANMAR_BURMESE_RE = MYANMAR_SCRIPT_RE

#: Myanmar digits U+1040-U+1049 (``၀`` .. ``၉``).
MYANMAR_DIGIT_RE = re.compile(r"[\u1040-\u1049]")

#: Basic Latin letters, used for mixed-script detection.
LATIN_SCRIPT_RE = re.compile(r"[A-Za-z]")

#: Legacy tolerance for start / duration comparison.
TIMESTAMP_EPSILON = 1e-6

#: Legacy tolerance for source duration drift before render is blocked.
MAX_DURATION_DRIFT = 0.05

_DIALOGUE_HINTS = (
    "hello", "hi ", "hey", "goodbye", "thank", "please", "sorry",
    "yes", "no ", "okay", "oh ", "hmm", "wow", "heh", "haha",
)


def is_burmese(text: str) -> bool:
    """True when ``text`` contains at least one Myanmar codepoint."""
    if not text:
        return False
    return bool(MYANMAR_SCRIPT_RE.search(text))


def has_myanmar_digits(text: str) -> bool:
    """True when ``text`` contains Myanmar digits (U+1040-U+1049).

    Myanmar digits are *not* ASCII digits, so a naive ``str.isdigit()`` check
    on a Myanmar sentence returns ``False`` even though the text contains
    numbers.  The exact-dubbing validator uses this to allow numeric content
    that is written with Myanmar digits.
    """
    if not text:
        return False
    return bool(MYANMAR_DIGIT_RE.search(text))


def has_mixed_script(text: str) -> bool:
    """True when ``text`` mixes Myanmar and Latin letters.

    Mixing scripts inside one narration line is usually a mistranslation
    (an untranslated English phrase left inside the Myanmar text) and is
    reported as a warning rather than an error, because a deliberate
    product name or a transliterated title is legitimate.
    """
    if not text:
        return False
    return bool(MYANMAR_SCRIPT_RE.search(text)) and bool(LATIN_SCRIPT_RE.search(text))


def _is_question(text: str) -> bool:
    stripped = (text or "").strip()
    return stripped.endswith("?") or stripped.endswith("။")


def validate_exact_dubbing(
    rows: Sequence[ExactDubbingRow],
    source: Sequence[TranscriptRow],
) -> ValidationReport:
    """Validate exact-dubbing rows against the source transcript.

    The comparison is positional: row *i* must correspond to source row *i*.
    """
    issues: list[ValidationIssue] = []

    if len(rows) != len(source):
        issues.append(
            ValidationIssue(
                code="row_count_mismatch",
                message=(
                    f"Row count mismatch: {len(rows)} dubbing rows vs "
                    f"{len(source)} source rows"
                ),
                severity=Severity.ERROR,
            )
        )

    for index, row in enumerate(rows):
        if index >= len(source):
            issues.append(
                ValidationIssue(
                    code="extra_row",
                    message=f"Row {index + 1} has no matching source row",
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                )
            )
            continue

        src = source[index]

        if row.row_id != src.row_id:
            issues.append(
                ValidationIssue(
                    code="id_changed",
                    message=(
                        f"Row {index + 1} id changed: '{row.row_id}' -> "
                        f"'{src.row_id}' (order must be preserved)"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="id",
                )
            )

        if row.original != src.text:
            issues.append(
                ValidationIssue(
                    code="original_changed",
                    message=(
                        f"Row {index + 1} source text was modified; exact "
                        "dubbing must never change the original line"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="original",
                )
            )

        if abs(row.start - src.start) > TIMESTAMP_EPSILON:
            issues.append(
                ValidationIssue(
                    code="start_drift",
                    message=(
                        f"Row {index + 1} start drift "
                        f"{abs(row.start - src.start):.6f}s exceeds tolerance"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="start",
                )
            )

        if abs(row.duration - src.duration) > TIMESTAMP_EPSILON:
            issues.append(
                ValidationIssue(
                    code="duration_drift",
                    message=(
                        f"Row {index + 1} duration drift "
                        f"{abs(row.duration - src.duration):.6f}s exceeds tolerance"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="duration",
                )
            )

        if not row.burmese.strip():
            issues.append(
                ValidationIssue(
                    code="missing_burmese",
                    message=f"Row {index + 1} has no Burmese translation",
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="burmese",
                )
            )
        elif not is_burmese(row.burmese):
            issues.append(
                ValidationIssue(
                    code="non_burmese",
                    message=(
                        f"Row {index + 1} translation contains no Myanmar "
                        "characters"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="burmese",
                )
            )
        elif has_mixed_script(row.burmese):
            issues.append(
                ValidationIssue(
                    code="mixed_script",
                    message=(
                        f"Row {index + 1} translation mixes Myanmar and Latin "
                        "script; check for untranslated text"
                    ),
                    severity=Severity.WARNING,
                    row_id=row.row_id,
                    field="burmese",
                )
            )

        # A row loaded from JSON may carry a plain string instead of the
        # Gender enum, so normalise before comparing.
        gender_value = getattr(row.gender, "value", row.gender)
        if gender_value not in {"male", "female", "unknown"}:
            issues.append(
                ValidationIssue(
                    code="invalid_gender",
                    message=(
                        f"Row {index + 1} has an invalid gender value; use "
                        "male, female or unknown"
                    ),
                    severity=Severity.ERROR,
                    row_id=row.row_id,
                    field="gender",
                )
            )

    return ValidationReport(issues=issues, checked_rows=len(rows))


def validate_narration(segments: Sequence[NarrationSegment]) -> ValidationReport:
    """Validate narrator segments (legacy ``narration_problems`` subset)."""
    issues: list[ValidationIssue] = []

    for segment in segments:
        narration = (segment.narration or "").strip()
        if not narration:
            issues.append(
                ValidationIssue(
                    code="empty_narration",
                    message=f"Segment {segment.segment_id} has empty narration",
                    severity=Severity.WARNING,
                    row_id=segment.segment_id,
                    field="narration",
                )
            )
            continue

        if segment.duration > 0 and len(narration) / segment.duration > 12:
            issues.append(
                ValidationIssue(
                    code="narration_too_long",
                    message=(
                        f"Segment {segment.segment_id} narration is too long for "
                        f"{segment.duration:.1f}s"
                    ),
                    severity=Severity.WARNING,
                    row_id=segment.segment_id,
                    field="narration",
                )
            )

        if _is_question(narration) and not segment.semantic_boundary:
            issues.append(
                ValidationIssue(
                    code="missing_semantic_boundary",
                    message=(
                        f"Segment {segment.segment_id} ends on a question but "
                        "has no semantic boundary"
                    ),
                    severity=Severity.INFO,
                    row_id=segment.segment_id,
                    field="semantic_boundary",
                )
            )

    return ValidationReport(issues=issues, checked_rows=len(segments))


def validate_source_duration(
    source_duration: float, measured_duration: float
) -> Optional[ValidationIssue]:
    """Block the render when the source duration drifted too much."""
    drift = abs(source_duration - measured_duration)
    if drift > MAX_DURATION_DRIFT:
        return ValidationIssue(
            code="source_duration_drift",
            message=(
                f"Source duration drift {drift:.3f}s exceeds "
                f"{MAX_DURATION_DRIFT}s tolerance"
            ),
            severity=Severity.ERROR,
            field="source_duration",
        )
    return None


def summarise(issues: Iterable[ValidationIssue]) -> str:
    """One-line human summary for a list of issues."""
    issues = list(issues)
    if not issues:
        return "OK"
    errors = sum(1 for i in issues if i.severity is Severity.ERROR)
    warnings = sum(1 for i in issues if i.severity is Severity.WARNING)
    return f"{errors} error(s), {warnings} warning(s)"

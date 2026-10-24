"""Per-mode coordinators.

Each mode owns its own working set and its own rules:

* **Narrator Mode** works on :class:`NarrationSegment` rows - a summarised,
  re-ordered narration track. Order matters and is expected to change.
* **Exact Dubbing Mode** works on :class:`ExactDubbingRow` rows - one row per
  source line, order immutable, nothing may be summarised or omitted.

The two coordinators deliberately share **no** base class and **no** row type.
A narrator edit must never be able to reach an exact-dubbing row and vice
versa, so the only shared surface is the small protocol below.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.enums import AppMode
from ..domain.models import (
    ExactDubbingRow,
    NarrationSegment,
    ProjectSession,
    ValidationReport,
)
from ..domain.validation import validate_exact_dubbing, validate_narration

__all__ = [
    "ModeCoordinator",
    "NarratorCoordinator",
    "ExactDubbingCoordinator",
    "SplitterCoordinator",
    "CommonEditingCoordinator",
    "build_coordinator",
]


@runtime_checkable
class ModeCoordinator(Protocol):
    """Common *shape* only - not a shared implementation base class."""

    mode: AppMode

    def row_count(self) -> int:  # pragma: no cover - protocol
        ...

    def validate(self) -> ValidationReport:  # pragma: no cover - protocol
        ...

    def can_leave(self) -> bool:  # pragma: no cover - protocol
        ...


class NarratorCoordinator:
    """Narrator Mode: a summarised, re-orderable narration track."""

    mode = AppMode.NARRATOR

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    def rows(self) -> list[NarrationSegment]:
        return self._session.narration_segments

    def row_count(self) -> int:
        return len(self._session.narration_segments)

    def update_narration(self, segment_id: str, text: str) -> bool:
        for segment in self._session.narration_segments:
            if segment.segment_id == segment_id:
                segment.narration = text
                segment.dirty = True
                return True
        return False

    def validate(self) -> ValidationReport:
        return validate_narration(self._session.narration_segments)

    def can_leave(self) -> bool:
        """Narrator mode may always be left, but unsaved edits are reported."""
        return True

    def dirty_count(self) -> int:
        return self._session.narrator_dirty_count

    def save(self) -> None:
        for segment in self._session.narration_segments:
            segment.dirty = False


class ExactDubbingCoordinator:
    """Exact Dubbing Mode: one immutable row per source line."""

    mode = AppMode.EXACT_DUBBING

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    def rows(self) -> list[ExactDubbingRow]:
        return self._session.exact_dubbing_rows

    def row_count(self) -> int:
        return len(self._session.exact_dubbing_rows)

    def update_translation(self, row_id: str, burmese: str) -> bool:
        for row in self._session.exact_dubbing_rows:
            if row.row_id == row_id:
                row.burmese = burmese
                row.edited = True
                return True
        return False

    def update_gender(self, row_id: str, gender: str) -> bool:
        for row in self._session.exact_dubbing_rows:
            if row.row_id == row_id:
                try:
                    from ..domain.enums import Gender

                    row.gender = Gender(gender)
                except ValueError:
                    return False
                row.edited = True
                return True
        return False

    def validate(self) -> ValidationReport:
        return validate_exact_dubbing(
            self._session.exact_dubbing_rows, self._session.transcript
        )

    def can_leave(self) -> bool:
        """Leaving is blocked only by *blocking* validation errors."""
        return self.validate().ok

    def dirty_count(self) -> int:
        return self._session.exact_dirty_count

    def save(self) -> None:
        for row in self._session.exact_dubbing_rows:
            row.edited = False


class SplitterCoordinator:
    """Splitter Mode: plans and toggles output parts."""

    mode = AppMode.SPLITTER

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    def parts(self):
        return self._session.split_parts

    def row_count(self) -> int:
        return len(self._session.split_parts)

    def validate(self) -> ValidationReport:
        issues = []
        for part in self._session.split_parts:
            if part.end <= part.start:
                from ..domain.enums import Severity
                from ..domain.models import ValidationIssue

                issues.append(
                    ValidationIssue(
                        code="invalid_part",
                        message=f"Part {part.number} ends before it starts",
                        severity=Severity.ERROR,
                        row_id=str(part.number),
                    )
                )
        return ValidationReport(issues=issues, checked_rows=len(self._session.split_parts))

    def can_leave(self) -> bool:
        return True

    def dirty_count(self) -> int:
        return 0


class CommonEditingCoordinator:
    """Common Video Editing: overlays, canvas settings and the timeline."""

    mode = AppMode.COMMON_EDITING

    def __init__(self, session: ProjectSession) -> None:
        self._session = session

    def overlays(self):
        return self._session.overlays

    def row_count(self) -> int:
        return len(self._session.overlays)

    def validate(self) -> ValidationReport:
        return ValidationReport(checked_rows=len(self._session.overlays))

    def can_leave(self) -> bool:
        return True

    def dirty_count(self) -> int:
        return 0


def build_coordinator(
    mode: AppMode, session: ProjectSession
) -> ModeCoordinator:
    """Return the coordinator for ``mode``.

    The returned objects share no implementation base class, so narrator
    behaviour can never leak into exact dubbing.
    """
    if mode is AppMode.NARRATOR:
        return NarratorCoordinator(session)  # type: ignore[return-value]
    if mode is AppMode.EXACT_DUBBING:
        return ExactDubbingCoordinator(session)  # type: ignore[return-value]
    if mode is AppMode.SPLITTER:
        return SplitterCoordinator(session)  # type: ignore[return-value]
    return CommonEditingCoordinator(session)  # type: ignore[return-value]

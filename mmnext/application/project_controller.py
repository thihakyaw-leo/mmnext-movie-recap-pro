"""Project/session orchestration.

Owns the current :class:`~mmnext.domain.models.ProjectSession`, the working
set of the active mode and the unsaved-change tracking used by the dirty
guard.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from ..domain.enums import AppMode, Gender
from ..domain.models import (
    ExactDubbingRow,
    NarrationSegment,
    ProjectSession,
    SourceMetadata,
    SplitPart,
    TranscriptRow,
    VideoSource,
)
from ..domain.validation import (
    validate_exact_dubbing,
    validate_narration,
    validate_source_duration,
)
from ..domain.models import ValidationReport
from ..services.protocols import MetadataService

__all__ = ["ProjectController"]


class ProjectController:
    """Holds the current project and mediates all edits to it."""

    def __init__(self, metadata_service: MetadataService) -> None:
        self._metadata_service = metadata_service
        self._session: Optional[ProjectSession] = None
        self._listeners: list[Callable[[str], None]] = []

    # -- observation ------------------------------------------------------- #
    def add_listener(self, callback: Callable[[str], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, reason: str) -> None:
        for callback in list(self._listeners):
            callback(reason)

    # -- session ----------------------------------------------------------- #
    @property
    def session(self) -> Optional[ProjectSession]:
        return self._session

    @property
    def has_project(self) -> bool:
        return self._session is not None

    def load(self, session: ProjectSession) -> ProjectSession:
        self._session = session
        self._notify("session_loaded")
        return session

    def clear(self) -> None:
        self._session = None
        self._notify("session_cleared")

    # -- source / metadata ------------------------------------------------- #
    def begin_local_transcript(self, source: VideoSource, output_folder: str) -> ProjectSession:
        """Explicit real-job boundary: never carry demo rows or prior plans."""
        session = ProjectSession(source=source, output_folder=output_folder,
                                 mode=self.mode, is_demo=False)
        return self.load(session)

    def apply_transcript(self, rows: list[TranscriptRow]) -> None:
        """Bind verbatim source and prepare exact rows, not a narrator recap.

        Narrator planning is a separate future stage; no conversion between
        narrator and exact-dubbing working sets is allowed.
        """
        if self._session is None or self._session.is_demo:
            raise ValueError("A real transcript session is required")
        self._session.transcript = [TranscriptRow(r.row_id, r.start, r.duration, r.text) for r in rows]
        self._session.exact_dubbing_rows = [
            ExactDubbingRow(r.row_id, r.start, r.duration, r.text) for r in rows
        ]
        self._session.narration_segments = []
        self._notify("transcript_loaded")

    def set_source(self, source: VideoSource) -> None:
        if self._session is None:
            from ..services.demo import demo_data

            self._session = demo_data.build_demo_session()
        if (not self._session.is_demo and self._session.source is not None
                and self._session.source.location != source.location):
            self._session.metadata = None
            self._session.transcript = []
            self._session.narration_segments = []
            self._session.exact_dubbing_rows = []
            self._session.split_parts = []
            self._session.overlays = []
        self._session.source = source
        self._notify("source_changed")

    def analyze(self, source: Optional[VideoSource] = None) -> SourceMetadata:
        """Run the metadata service and attach the result to the session."""
        if self._session is None:
            from ..services.demo import demo_data

            self._session = demo_data.build_demo_session()
        target = source or self._session.source
        if target is None:
            raise ValueError("No source to analyze")
        metadata = self._metadata_service.analyze(target)
        self._session.metadata = metadata
        self._session.source = target
        self._notify("metadata_loaded")
        return metadata

    # -- mode -------------------------------------------------------------- #
    @property
    def mode(self) -> AppMode:
        if self._session is None:
            return AppMode.COMMON_EDITING
        return self._session.mode

    def set_mode(self, mode: AppMode) -> None:
        if self._session is None:
            from ..services.demo import demo_data

            self._session = demo_data.build_demo_session()
        if self._session.mode is mode:
            return
        self._session.mode = mode
        self._notify("mode_changed")

    # -- narrator working set ---------------------------------------------- #
    def update_narration(self, segment_id: str, text: str) -> bool:
        if self._session is None:
            return False
        for segment in self._session.narration_segments:
            if segment.segment_id == segment_id:
                segment.narration = text
                segment.dirty = True
                self._notify("narration_changed")
                return True
        return False

    def mark_narration_clean(self) -> None:
        if self._session is None:
            return
        for segment in self._session.narration_segments:
            segment.dirty = False
        self._notify("narration_saved")

    def set_narration_segments(self, segments: List[NarrationSegment]) -> None:
        """Replace the narrator working set (plan result) and notify listeners."""
        if self._session is None:
            return
        self._session.narration_segments = list(segments)
        self._notify("narration_changed")

    def narrator_segments(self) -> list[NarrationSegment]:
        if self._session is None:
            return []
        return self._session.narration_segments

    # -- exact dubbing working set ----------------------------------------- #
    def update_exact_row(
        self,
        row_id: str,
        burmese: Optional[str] = None,
        gender: Optional[str] = None,
    ) -> bool:
        if self._session is None:
            return False
        for row in self._session.exact_dubbing_rows:
            if row.row_id == row_id:
                if burmese is not None:
                    row.burmese = burmese
                if gender is not None:
                    # The gender column is a Gender enum; a raw string coming
                    # from a combobox has to be coerced or every later
                    # validation of ``row.gender.value`` would blow up.
                    row.gender = Gender(gender)
                row.edited = True
                self._notify("exact_row_changed")
                return True
        return False

    def mark_exact_rows_clean(self) -> None:
        if self._session is None:
            return
        for row in self._session.exact_dubbing_rows:
            row.edited = False
        self._notify("exact_rows_saved")

    def set_exact_dubbing_rows(self, rows: List[ExactDubbingRow]) -> None:
        if self._session is None:
            raise ValueError("No project session")
        self._session.exact_dubbing_rows = list(rows)
        self._notify("exact_rows_changed")

    def exact_rows(self) -> list[ExactDubbingRow]:
        if self._session is None:
            return []
        return self._session.exact_dubbing_rows

    def set_split_parts(self, parts: List[SplitPart]) -> None:
        if self._session is None:
            raise ValueError("No project session")
        self._session.split_parts = list(parts)
        self._notify("split_parts_changed")

    def transcript(self) -> list[TranscriptRow]:
        if self._session is None:
            return []
        return self._session.transcript

    # -- validation -------------------------------------------------------- #
    def validate(self, mode: Optional[AppMode] = None) -> ValidationReport:
        active = mode or self.mode
        if self._session is None:
            return ValidationReport()
        if active is AppMode.EXACT_DUBBING:
            return validate_exact_dubbing(
                self._session.exact_dubbing_rows, self._session.transcript
            )
        if active is AppMode.NARRATOR:
            return validate_narration(self._session.narration_segments)
        return ValidationReport()

    def validate_source_duration(self, measured: float) -> Optional[object]:
        if self._session is None or self._session.metadata is None:
            return None
        return validate_source_duration(
            self._session.metadata.duration_s, measured
        )

    # -- dirty tracking ---------------------------------------------------- #
    def dirty_count(self, mode: Optional[AppMode] = None) -> int:
        if self._session is None:
            return 0
        active = mode or self._session.mode
        if active is AppMode.NARRATOR:
            return self._session.narrator_dirty_count
        if active is AppMode.EXACT_DUBBING:
            return self._session.exact_dirty_count
        return 0

    def has_unsaved_changes(self, mode: Optional[AppMode] = None) -> bool:
        return self.dirty_count(mode) > 0

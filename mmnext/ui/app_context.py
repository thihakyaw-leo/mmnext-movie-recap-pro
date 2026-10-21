"""The application context - the single object every screen talks to.

``AppContext`` owns the controllers and exposes them as **Qt signals** so
screens never reach into a controller directly. That keeps the GUI thread as
the only place where UI state changes.

``SelectionModel`` is the shared selection (current row) used by the segment
list, the timeline and the inspector, so all three stay in sync.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from ..application.download_controller import DownloadController, DownloadEvent
from ..application.job_manager import JobManager
from ..application.mode_coordinators import ModeCoordinator, build_coordinator
from ..application.narrator_coordinator import NarratorPlanCoordinator
from ..application.project_controller import ProjectController
from ..domain.enums import AppMode, JobState, Stage, TaskState
from ..domain.models import (
    DownloadItem,
    ExactDubbingRow,
    Job,
    LogEntry,
    NarrationSegment,
    ProjectSession,
    SourceMetadata,
    TranscriptRow,
    ValidationReport,
    VideoSource,
)
from ..services.adapters.narrator import NarratorPlanningService
from ..services.demo.demo_providers import DemoDownloadService, DemoMetadataService
from ..services.demo import demo_data

__all__ = ["AppContext", "SelectionModel", "DirtyGuard"]


class SelectionModel(QObject):
    """Shared selection for the workspace (row id + source kind)."""

    rowChanged = Signal(str, str)          # row_id, kind
    selectionCleared = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._row_id: str = ""
        self._kind: str = ""

    @property
    def row_id(self) -> str:
        return self._row_id

    @property
    def kind(self) -> str:
        return self._kind

    def select(self, row_id: str, kind: str) -> None:
        if row_id == self._row_id and kind == self._kind:
            return
        self._row_id = row_id
        self._kind = kind
        self.rowChanged.emit(row_id, kind)

    def clear(self) -> None:
        if not self._row_id and not self._kind:
            return
        self._row_id = ""
        self._kind = ""
        self.selectionCleared.emit()


class DirtyGuard(QObject):
    """Tracks unsaved edits per mode and asks before discarding them."""

    dirtyChanged = Signal(int, str)       # count, mode value

    def __init__(self, project: ProjectController, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._project = project
        self._counts: dict[str, int] = {}
        project.add_listener(self._on_project_event)

    def _on_project_event(self, reason: str) -> None:
        if reason in {
            "narration_changed",
            "exact_row_changed",
            "narration_saved",
            "exact_rows_saved",
        }:
            self.refresh()

    def refresh(self) -> None:
        for mode in AppMode:
            count = self._project.dirty_count(mode)
            key = mode.value
            if self._counts.get(key) != count:
                self._counts[key] = count
                self.dirtyChanged.emit(count, key)

    def count(self, mode: AppMode) -> int:
        return self._project.dirty_count(mode)

    def total_dirty(self) -> int:
        """Unsaved edits across **every** working set.

        A destructive action (restoring the demo project, closing the
        window) discards narrator *and* exact-dubbing edits, so the count
        used for the confirmation has to span all of them.
        """
        return sum(self._project.dirty_count(mode) for mode in AppMode)

    def has_unsaved(self, mode: Optional[AppMode] = None) -> bool:
        return self._project.has_unsaved_changes(mode)


class AppContext(QObject):
    """Owns the controllers and publishes their changes as signals."""

    # navigation / session
    sessionChanged = Signal()
    sourceChanged = Signal(object)            # VideoSource
    metadataChanged = Signal(object)         # SourceMetadata
    modeChanged = Signal(object)              # AppMode
    projectDirty = Signal(int)                # dirty row count (active mode)

    # downloads
    downloadUpdated = Signal(object)          # DownloadItem
    downloadStateChanged = Signal(object, object)  # DownloadItem, TaskState

    # jobs
    jobUpdated = Signal(object)               # Job
    jobStateChanged = Signal(object, object)  # Job, JobState
    logAppended = Signal(object)              # LogEntry
    validationChanged = Signal(object)        # ValidationReport

    transcriptProgress = Signal(object)
    transcriptStateChanged = Signal(str, str)
    transcriptReopened = Signal(object, str)  # session | None, error message

    # narrator heavy integration
    narratorProgress = Signal(object)          # ProgressEvent
    narratorStateChanged = Signal(str, str)

    def __init__(self, jobs_dir: Optional[str] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.metadata_service = DemoMetadataService()
        self.download_service = DemoDownloadService()

        self.project = ProjectController(self.metadata_service)
        self.downloads = DownloadController(self.download_service)
        self.jobs = JobManager(demo_data.build_demo_jobs())
        self.selection = SelectionModel(self)
        self.dirty = DirtyGuard(self.project, self)

        # Narrator plan coordinator (Qt-free). The legacy planner, when
        # available, is wrapped defensively; otherwise a deterministic
        # one-unit-per-row fallback is used. Never touches exact-dubbing rows.
        self._narrator_planner = NarratorPlanningService()
        self._narrator_coordinator = NarratorPlanCoordinator(self._narrator_planner)

        # Stable user-writable jobs directory
        from pathlib import Path
        if jobs_dir is None:
            import os
            jobs_dir = os.environ.get("MMNEXT_JOBS_DIR") or str(Path.home() / ".mmnext" / "jobs")
        self._jobs_dir = jobs_dir
        Path(self._jobs_dir).mkdir(parents=True, exist_ok=True)
        # Phase 2: repository-backed startup scan
        self._job_repository = None
        from ..infrastructure.repository.job_repository import JobRepository
        self._job_repository = JobRepository(self._jobs_dir)
        self._load_recoverable_jobs_from_repo()

        self._coordinator: Optional[ModeCoordinator] = None
        self._log_entries: list[LogEntry] = []

        self._transcript_thread = None
        self._transcript_session = None
        self._reopen_thread = None
        # The reopen request that is currently in flight, as
        # ``(job_id, source_path)``.  A reopen result is bound only while
        # this token still matches, so a load that finishes after the user
        # moved on can never overwrite the current project.
        self._reopen_token: Optional[tuple[str, str]] = None
        # Monotonic id of the newest reopen request.  It is only ever
        # replaced by a *new* request, never cleared, so a result can be
        # matched to its request without depending on the order in which
        # Qt delivers the result and the thread-finished signals.
        self._reopen_request_id = 0
        self.transcript_state = "idle"
        self.transcript_message = "No local transcript yet. Demo data is labelled DEMO."
        self.transcript_language = ""

        self._narrator_thread = None
        self.narrator_state = "idle"
        self.narrator_message = "No narrator run yet."

        self.project.add_listener(self._on_project_event)
        self.downloads.add_listener(self._on_download_event)
        self.jobs_changed = Signal()

    # -- session ----------------------------------------------------------- #
    def load_demo_project(self) -> ProjectSession:
        session = self.project.load(demo_data.build_demo_session())
        self._rebuild_coordinator()
        # A fresh session has no dirty rows; the guard caches per-mode
        # counts, so they have to be re-read or the chip keeps the number
        # from the previous project.
        self.dirty.refresh()
        self.sessionChanged.emit()
        return session

    @property
    def session(self) -> Optional[ProjectSession]:
        return self.project.session

    @property
    def has_project(self) -> bool:
        return self.project.has_project

    # -- source / metadata ------------------------------------------------- #
    def set_source(self, source: VideoSource) -> None:
        self.project.set_source(source)
        self.sourceChanged.emit(source)

    def analyze(self, source: Optional[VideoSource] = None) -> SourceMetadata:
        metadata = self.project.analyze(source)
        self.metadataChanged.emit(metadata)
        return metadata

    # -- mode -------------------------------------------------------------- #
    @property
    def mode(self) -> AppMode:
        return self.project.mode

    def set_mode(self, mode: AppMode) -> None:
        self.project.set_mode(mode)
        self._rebuild_coordinator()
        self.modeChanged.emit(mode)
        self.dirty.refresh()
        self.projectDirty.emit(self.dirty.count(mode))

    def _rebuild_coordinator(self) -> None:
        session = self.project.session
        if session is None:
            self._coordinator = None
            return
        self._coordinator = build_coordinator(self.project.mode, session)

    @property
    def coordinator(self) -> Optional[ModeCoordinator]:
        return self._coordinator

    # -- validation -------------------------------------------------------- #
    def validate(self, mode: Optional[AppMode] = None) -> ValidationReport:
        report = self.project.validate(mode)
        self.validationChanged.emit(report)
        return report

    # -- downloads --------------------------------------------------------- #
    def enqueue_download(
        self, source: VideoSource, quality: str = "1080p"
    ) -> str:
        return self.downloads.enqueue(source, quality)

    def download_items(self) -> list[DownloadItem]:
        return self.downloads.items()

    def _on_download_event(self, event: DownloadEvent) -> None:
        self.downloadUpdated.emit(event.item)
        self.downloadStateChanged.emit(event.item, event.state)

    # -- jobs / log -------------------------------------------------------- #
    def all_jobs(self) -> list[Job]:
        return self.jobs.all()

    def job(self, job_id: str) -> Job:
        return self.jobs.get(job_id)

    def transition_job(self, job_id: str, new_state: JobState) -> None:
        job = self.jobs.transition(job_id, new_state)
        self.jobStateChanged.emit(job, new_state)
        self.jobUpdated.emit(job)

    def update_job_progress(self, job_id: str, percent: float, message: str,
                            stage: Stage = Stage.IDLE) -> None:
        job = self.jobs.get(job_id)
        job.progress.percent = percent
        job.progress.message = message
        job.progress.stage = stage
        self.jobUpdated.emit(job)

    def append_log(self, entry: LogEntry) -> None:
        self._log_entries.append(entry)
        self.logAppended.emit(entry)

    def log_entries(self) -> list[LogEntry]:
        return list(self._log_entries)

    def _load_recoverable_jobs_from_repo(self) -> None:
        if not self._job_repository:
            return
        scan = self._job_repository.scan()
        for job, src_dir in scan.get("recoverable", []):
            try:
                self.jobs.add(job)
            except ValueError:
                pass
        # Completed REAL transcript jobs are discoverable for explicit reopen.
        for job, src_dir in scan.get("completed_real", []):
            try:
                self.jobs.add(job)
            except ValueError:
                pass
        for corrupt_path in scan.get("corrupt", []):
            self.append_log(LogEntry(message=f"Corrupt job record detected: {corrupt_path}", stage=Stage.IDLE))

    # -- internal ---------------------------------------------------------- #
    @property
    def transcript_running(self) -> bool:
        return self._transcript_thread is not None and self._transcript_thread.isRunning()

    def _set_transcript_state(self, state: str, message: str) -> None:
        self.transcript_state = state
        self.transcript_message = message
        self.transcriptStateChanged.emit(state, message)

    def start_local_transcript(self, media_path: str, language=None, auto_detect=True) -> None:
        """Explicit real action; no demo provider and no implicit cloud work."""
        from pathlib import Path
        from ..domain.models import VideoSource
        from ..infrastructure.transcript_adapter import WhisperTranscriptAdapter
        from .transcript_worker import TranscriptWorkerThread

        if self.transcript_running:
            raise RuntimeError("A transcript is already running")
        if not Path(media_path).is_file():
            raise ValueError("Choose an existing local media file")
        if self.dirty.total_dirty():
            raise ValueError("Discard unsaved edits explicitly before starting a new transcript")
        jobs_dir = str(self._jobs_dir)
        session = self.project.begin_local_transcript(VideoSource.local(media_path), jobs_dir)
        self.selection.clear()
        self._transcript_session = session
        self.transcript_language = ""
        provider = WhisperTranscriptAdapter(jobs_dir, media_path, mode=session.mode, is_demo=False)
        thread = TranscriptWorkerThread(provider, media_path, language, auto_detect, parent=self)
        self._transcript_thread = thread
        thread.progress.connect(self._on_transcript_progress)
        thread.error.connect(self._on_transcript_error)
        thread.stopped.connect(self._on_transcript_stopped)
        thread.result.connect(self._on_transcript_result)
        thread.finished.connect(self._on_transcript_thread_finished)
        self._rebuild_coordinator()
        self._set_transcript_state("running", "REAL local transcription: preparing audio/loading model; restart only, no resume.")
        thread.start()

    def stop_transcript(self) -> None:
        if self.transcript_running:
            self._transcript_thread.stop()
            self._set_transcript_state("stopping", "Stop requested; waiting for current operation/segment and durable checkpoint. No resume; restart only.")

    def plan_narration(self, video_duration: Optional[float] = None) -> list[NarrationSegment]:
        """Plan narrator segments from the current verbatim transcript.

        Runs the pure-Python planner off the GUI thread boundary (the planner
        itself is fast; heavy FFmpeg/Whisper work stays on the transcript
        worker). Results attach to the active session without touching the
        exact-dubbing working set.
        """
        if self.project.session is None:
            raise ValueError("No project session")
        session = self.project.session
        rows = self.project.transcript()
        if not rows:
            raise ValueError("No verbatim transcript rows to plan from")
        duration = float(video_duration) if video_duration is not None else session.total_duration()
        if duration <= 0:
            raise ValueError("No source duration to plan against")
        segments = self._narrator_coordinator.plan(rows, duration)
        self.project.set_narration_segments(segments)
        self.sessionChanged.emit()
        return segments

    def prepare_exact_dubbing(self) -> list[ExactDubbingRow]:
        """Prepare exact-dubbing rows from the current verbatim transcript.

        Source identity, text, start and duration are copied verbatim; only
        ``burmese`` and ``gender`` remain editable.  Narrator segments are
        never touched.
        """
        if self.project.session is None:
            raise ValueError("No project session")
        rows = self.project.transcript()
        if not rows:
            raise ValueError("No verbatim transcript rows to prepare from")
        exact_rows = [
            ExactDubbingRow(row_id=row.row_id, start=row.start, duration=row.duration, original=row.text)
            for row in rows
        ]
        self.project.set_exact_dubbing_rows(exact_rows)
        self.sessionChanged.emit()
        return exact_rows

    # -- narrator pipeline -------------------------------------------------- #
    @property
    def narrator_pipeline_running(self) -> bool:
        return self._narrator_thread is not None and self._narrator_thread.isRunning()

    def start_narrator_pipeline(self, video_path: str = "", output_path: str = "", settings: Optional[dict] = None) -> None:
        """Start the narrator heavy integration pipeline on a worker thread.

        The heavy stages (translation, speech synthesis, Smart Sync render)
        never run on the GUI thread.  The demo adapters are used until the
        REAL adapters are available, and the run is labelled DEMO so the UI
        never presents simulated work as real.
        """
        from ..application.narrator_pipeline_coordinator import NarratorPipelineCoordinator
        from ..services.adapters.narrator_render import (
            DemoSmartSyncRenderer,
            LegacySmartSyncRenderer,
        )
        from ..services.adapters.narrator_translation import (
            DemoTranslationProvider,
            LegacyNarratorTranslationAdapter,
        )
        from ..services.adapters.narrator_tts import (
            DemoSpeechSynthesizer,
            LegacyEdgeTtsAdapter,
        )
        from .narrator_pipeline_worker import NarratorPipelineThread

        if self.narrator_pipeline_running:
            raise RuntimeError("A narrator pipeline run is already in progress")
        session = self.project.session
        if session is None:
            raise ValueError("No project session")
        rows = self.project.transcript()
        if not rows:
            raise ValueError("No verbatim transcript rows to narrate from")
        duration = float(session.total_duration())
        if duration <= 0:
            raise ValueError("No source duration to narrate against")

        source_path = video_path or (session.source.location if session.source else "")
        target_path = output_path or str(
            Path(session.output_folder or self._jobs_dir) / "narrator_recap.mp4"
        )

        cache_dir = str(Path(self._jobs_dir) / "narrator_cache")

        translator = LegacyNarratorTranslationAdapter()
        tts = LegacyEdgeTtsAdapter(cache_dir=cache_dir)
        renderer = LegacySmartSyncRenderer()
        is_demo = not (
            translator.available() and tts.available() and renderer.available()
        )
        if is_demo:
            translator = DemoTranslationProvider()
            tts = DemoSpeechSynthesizer(cache_dir=cache_dir)
            renderer = DemoSmartSyncRenderer()

        coordinator = NarratorPipelineCoordinator(
            plan_coordinator=self._narrator_coordinator,
            translator=translator,
            tts=tts,
            renderer=renderer,
            is_demo=is_demo,
        )
        thread = NarratorPipelineThread(
            coordinator, rows, source_path, duration, target_path, settings or {}
        )
        self._narrator_thread = thread
        thread.progress.connect(self._on_narrator_progress)
        thread.log.connect(self._on_narrator_log)
        thread.result.connect(self._on_narrator_result)
        thread.error.connect(self._on_narrator_error)
        thread.finished.connect(self._on_narrator_thread_finished)
        self._set_narrator_state(
            "running",
            "DEMO narrator pipeline: plan -> translate -> synthesise -> render.",
        )
        thread.start()

    def stop_narrator_pipeline(self) -> None:
        if self.narrator_pipeline_running:
            self._narrator_thread.stop()
            self._set_narrator_state(
                "stopping",
                "Stop requested; the narrator pipeline stops at the next stage boundary.",
            )

    def _set_narrator_state(self, state: str, message: str) -> None:
        self.narrator_state = state
        self.narrator_message = message
        self.narratorStateChanged.emit(state, message)

    def _on_narrator_progress(self, event) -> None:
        self.narratorProgress.emit(event)

    def _on_narrator_log(self, message: str) -> None:
        self.append_log(LogEntry(message=message, stage=Stage.IDLE))

    def _on_narrator_result(self, result) -> None:
        segments = list(getattr(result, "segments", []) or [])
        if segments:
            self.project.set_narration_segments(segments)
            self.sessionChanged.emit()
        if getattr(result, "stopped", False):
            self._set_narrator_state("stopped", "Narrator pipeline stopped.")
        elif getattr(result, "ok", False):
            label = "DEMO" if getattr(result, "is_demo", True) else "REAL"
            self._set_narrator_state("done", f"{label} narrator pipeline finished.")
        else:
            self._set_narrator_state(
                "failed", getattr(result, "message", "") or "Narrator pipeline failed."
            )

    def _on_narrator_error(self, message: str) -> None:
        self._set_narrator_state("failed", f"Narrator pipeline failed: {message}")

    def _on_narrator_thread_finished(self) -> None:
        self._narrator_thread = None

    def prepare_transcript_from_job(
        self, job_id: str, source_path: str
    ) -> tuple[ProjectSession, list[TranscriptRow], str]:
        """Read and validate a completed REAL transcript artefact.

        This is the off-the-GUI-thread validation core: it reads the job
        record and the artefact and returns everything needed to apply the
        transcript, but it touches **no** project state.  The caller applies
        the result on the GUI thread, after checking that the request is
        still the current one.

        Returns ``(session, rows, language)``.
        """
        if self._job_repository is None:
            raise RuntimeError("Job repository not configured; cannot open transcript from jobs")
        if self.dirty.total_dirty():
            raise ValueError("Discard unsaved edits explicitly before opening a transcript")
        # Stale-request guard.  ``start_reopen_transcript`` records the
        # in-flight request; a request that no longer matches it belongs to a
        # job/source the user has already moved away from, so it is refused
        # before anything is applied.  A direct (non-threaded) call has no
        # token and is therefore not affected.
        if self._reopen_token is not None and self._reopen_token != (job_id, source_path):
            raise ValueError(
                "Stale reopen request: the selected job or source changed; reopen again."
            )
        job = self._job_repository.load(job_id, source_path)
        if job is None:
            raise FileNotFoundError(f"Job {job_id} not found for source {source_path}")
        # Validate job state
        from ..domain.enums import JobState
        if job.state != JobState.COMPLETE:
            raise ValueError(f"Job {job_id} is not complete (state={job.state.value})")
        if job.is_demo:
            raise ValueError("Demo transcripts cannot be opened as REAL data")
        if job.source is None:
            raise ValueError("Job has no source metadata")
        # Compute artifact path using repository layout
        from pathlib import Path
        job_dir = self._job_repository._job_dir(job_id, source_path)
        mode = job.mode
        artifact_dir = job_dir / mode.value / "transcripts"
        stem = Path(source_path).stem
        artifact_path = artifact_dir / f"{stem}.transcript.json"
        if not artifact_path.exists():
            raise FileNotFoundError(f"Transcript artifact missing at {artifact_path}")
        # Load and validate artifact atomically
        from ..domain.paths import read_json
        data = read_json(artifact_path)
        # The file may hold any JSON value.  Only a JSON object can carry the
        # contract, so anything else is a corrupt artefact - never a crash.
        if not isinstance(data, dict) or not data:
            raise ValueError("Transcript artifact is corrupt or unreadable")
        try:
            schema_version = int(data.get("schema_version", 0) or 0)
        except (TypeError, ValueError):
            schema_version = -1
        if schema_version != 1:
            raise ValueError(f"Unsupported transcript schema version {data.get('schema_version')}")
        if bool(data.get("is_demo", True)):
            raise ValueError("Artifact is marked as demo; REAL data required")
        # Source identity match
        #
        # The media must still be readable: comparing the identity of a file
        # that no longer exists cannot succeed, and the user needs a clear
        # "the media is gone" message rather than an OS error.
        from ..domain.fingerprint import is_canonical_fingerprint, is_source_available
        from ..infrastructure.repository.job_repository import compute_fingerprint

        artifact_source = str(data.get("source_path", ""))
        if not artifact_source:
            raise ValueError("Transcript artifact has no source path")
        if not is_source_available(job.source.location, job.source.source_type):
            raise ValueError(
                f"Source media is unavailable: {job.source.location}. "
                "Restore the file and reopen, or re-transcribe."
            )
        try:
            same_source = Path(artifact_source).resolve().samefile(
                Path(job.source.location)
            )
        except OSError:
            # The recorded source path no longer exists on disk.
            same_source = False
        if not same_source:
            raise ValueError("Artifact source path does not match job source")
        # Fingerprint validation.
        #
        # The artefact carries the *exact* fingerprint inputs that produced it
        # (``fingerprint_settings`` / ``fingerprint_source_type`` /
        # ``fingerprint_schema_version``).  Recomputing without them hashes a
        # different payload, so a real adapter-written artefact would never
        # match and every REAL reopen would be rejected.  Re-derive from the
        # artefact's own inputs instead.
        artifact_fp = str(data.get("fingerprint", "") or "")
        artifact_mode = str(data.get("mode", "") or "")
        fingerprint_settings = data.get("fingerprint_settings")
        fingerprint_source_type = str(data.get("fingerprint_source_type", "") or "")
        try:
            fingerprint_schema_version = int(data.get("fingerprint_schema_version", 0) or 0)
        except (TypeError, ValueError):
            fingerprint_schema_version = 0

        # A legacy artefact (pre-contract: no canonical fingerprint, or none
        # of the new keys) is unverifiable.  It is refused explicitly instead
        # of being silently accepted or silently repaired.
        if not is_canonical_fingerprint(artifact_fp):
            raise ValueError("Legacy transcript artifact - re-transcribe required")
        if not isinstance(fingerprint_settings, dict) or not fingerprint_settings:
            raise ValueError("Legacy transcript artifact - re-transcribe required")
        if not fingerprint_source_type or fingerprint_schema_version <= 0:
            raise ValueError("Legacy transcript artifact - re-transcribe required")

        # Mode match: the artefact must describe the same mode as the job it
        # is reopened as.  A narrator artefact must never be opened as exact
        # dubbing and vice versa.
        if artifact_mode != mode.value:
            raise ValueError(
                f"Artifact mode {artifact_mode!r} does not match job mode {mode.value!r}"
            )

        # Artifact path containment: the artefact must resolve inside this
        # job's own source directory.  A job id or source path that would
        # place the artefact outside the repository (for example a job id
        # containing path separators) is refused instead of being read.
        try:
            artifact_path.resolve().relative_to(
                self._job_repository._source_dir(source_path).resolve()
            )
        except ValueError:
            raise ValueError("Transcript artifact is outside the job directory")

        current_fp = compute_fingerprint(
            source_path,
            fingerprint_source_type,
            mode,
            settings=dict(fingerprint_settings),
            schema_version=fingerprint_schema_version,
        )
        if artifact_fp != current_fp:
            raise ValueError("Fingerprint mismatch between artifact and current source")
        # rows validation
        rows_raw = data.get("rows", [])
        if not isinstance(rows_raw, list) or not rows_raw:
            raise ValueError("Transcript artifact contains no rows")
        from ..domain.models import TranscriptRow, VideoSource, ProjectSession
        rows = []
        seen_ids = set()
        try:
            artifact_duration = float(data.get("duration_s", 0.0) or 0.0)
        except (TypeError, ValueError):
            artifact_duration = 0.0
        for r in rows_raw:
            try:
                row_id = str(r["row_id"])
                start = float(r["start"])
                row_duration = float(r["duration"])
                text = str(r["text"])
            except Exception as exc:
                raise ValueError(f"Invalid transcript row: {exc}")
            if not row_id:
                raise ValueError(f"Empty row_id in transcript artifact")
            if row_id in seen_ids:
                raise ValueError(f"Duplicate row_id {row_id} in transcript artifact")
            seen_ids.add(row_id)
            if not (math.isfinite(start) and start >= 0):
                raise ValueError(f"Invalid start time for row {row_id}: {start}")
            if not (math.isfinite(row_duration) and row_duration > 0):
                raise ValueError(f"Invalid duration for row {row_id}: {row_duration}")
            end = start + row_duration
            if not math.isfinite(end):
                raise ValueError(f"Invalid end time for row {row_id}: {end}")
            if artifact_duration > 0 and end > artifact_duration + 0.01:
                raise ValueError(f"Row {row_id} end {end}s exceeds artifact duration {artifact_duration}s")
            rows.append(TranscriptRow(row_id=row_id, start=start, duration=row_duration, text=text))
        # Build the session WITHOUT applying it: the caller applies it on the
        # GUI thread so the project is never mutated from a worker thread.
        source = VideoSource.local(job.source.location)
        output_folder = str(job_dir.parent.parent)
        session = ProjectSession(source=source, output_folder=output_folder, mode=mode, is_demo=False)
        return session, rows, str(data.get("language", ""))

    def open_transcript_from_job(self, job_id: str, source_path: str) -> None:
        """Load a completed REAL transcript artifact into the workspace with strict validation.

        Synchronous core: prepare and apply in one call.  The threaded path
        uses :meth:`prepare_transcript_from_job` off the GUI thread and
        applies the prepared result in a GUI-thread slot.
        """
        session, rows, language = self.prepare_transcript_from_job(job_id, source_path)
        self._apply_prepared_transcript(session, rows, language, job_id)

    def _apply_prepared_transcript(
        self, session, rows, language: str, job_id: str
    ) -> None:
        """Apply a validated transcript to the project.  GUI thread only."""
        # The unsaved-edit check happened when the artefact was *prepared*, on
        # the worker thread.  The user may have edited the working set while
        # the load was in flight, and ``project.load`` replaces the whole
        # session - which would silently discard those edits.  The check is
        # therefore repeated here, on the GUI thread, where it is
        # authoritative.
        if self.dirty.total_dirty():
            raise ValueError(
                "Unsaved edits appeared while the transcript was loading; "
                "discard them explicitly and reopen."
            )
        previous_mode = self.mode
        self.project.load(session)
        self.project.apply_transcript(rows)
        # ``project.load`` does not notify a mode change, so the workspace
        # mode switcher would keep showing the previous mode and the reopened
        # rows would be hidden behind the wrong panel.  Sync it explicitly.
        if previous_mode is not session.mode:
            self.set_mode(session.mode)
        self.transcript_language = language
        self._rebuild_coordinator()
        self._set_transcript_state(
            "complete",
            f"Opened REAL transcript from job {job_id}: {len(rows)} rows, language={language}",
        )

    def _on_transcript_progress(self, event) -> None:
        self.transcriptProgress.emit(event)

    def _on_transcript_error(self, event) -> None:
        self._set_transcript_state("failed", event.message + " " + event.detail)
        self.append_log(LogEntry(stage=Stage.TRANSCRIBE, message=event.message + " " + event.detail))

    def _on_transcript_stopped(self, message) -> None:
        self._set_transcript_state("stopped", message)

    def _register_job(self, job: Job) -> None:
        """Add (or replace) a job in the live manager and notify the Jobs screen."""
        try:
            self.jobs.add(job)
        except ValueError:
            self.jobs.remove(job.job_id)
            self.jobs.add(job)
        self.jobUpdated.emit(job)

    def _on_transcript_result(self, rows, language) -> None:
        if (self.session is not self._transcript_session
                or self.session.source is None
                or self.session.source.location != self._transcript_thread.media_path):
            self._set_transcript_state("failed", "Source/session changed; stale transcript was not applied. Restart for the current source.")
            return
        self.project.apply_transcript(rows)
        self.transcript_language = language
        self._rebuild_coordinator()
        provider = self._transcript_thread.provider
        # Persist Job metadata for restart discovery
        if self._job_repository is not None:
            try:
                from ..domain.enums import JobState
                from ..domain.models import Job, JobProgress, VideoSource
                from ..infrastructure.repository.job_repository import compute_fingerprint
                source_path = provider.source_path
                mode = provider.mode
                job_id = provider.job_id
                source_type = self.session.source.source_type.value if self.session.source else ""
                fp = getattr(provider, "fingerprint", "") or compute_fingerprint(
                    source_path, source_type, mode, schema_version=1
                )
                artifact_path = str(provider.artifact_path) if hasattr(provider, "artifact_path") else ""
                job = Job(
                    job_id=job_id,
                    title=Path(source_path).name,
                    mode=mode,
                    state=JobState.COMPLETE,
                    is_demo=False,
                    source=VideoSource.local(source_path),
                    progress=JobProgress(percent=100.0),
                    fingerprint=fp,
                    output_path=artifact_path,
                    artifact_path=artifact_path,
                )
                self._job_repository.save(job, source_path)
                self._register_job(job)
            except Exception as exc:
                self._set_transcript_state("failed", f"Failed to persist transcript job: {exc}")
                self.append_log(LogEntry(stage=Stage.TRANSCRIBE, message=f"Job persistence failed: {exc}"))
                return
        self._set_transcript_state("complete", f"REAL transcript: {len(rows)} rows, language={language}. Artifact: {provider.artifact_path}. Narrator plan not generated.")

    def start_reopen_transcript(self, job_id: str, source_path: str) -> None:
        """Reopen a completed REAL transcript off the GUI thread.

        Emits ``transcriptReopened(session, error)`` when done. The synchronous
        ``open_transcript_from_job`` remains the validation core and is used by
        tests and by the worker.
        """
        if self._reopen_thread is not None and self._reopen_thread.isRunning():
            raise RuntimeError("A transcript reopen is already running")
        if self.dirty.total_dirty():
            raise ValueError("Discard unsaved edits explicitly before opening a transcript")
        from .reopen_transcript_worker import ReopenTranscriptThread

        # Record the in-flight request so a result can be bound only while it
        # is still the request the user is waiting for.
        self._reopen_token = (job_id, source_path)
        self._reopen_request_id += 1
        thread = ReopenTranscriptThread(self, job_id, source_path, parent=self)
        thread.request_id = self._reopen_request_id
        self._reopen_thread = thread
        # Bound methods only: a self-capturing closure connected to a signal
        # would keep the context alive until interpreter shutdown and abort
        # the process in Qt teardown.
        thread.result.connect(self._on_reopen_result)
        thread.error.connect(self._on_reopen_error)
        thread.finished.connect(self._on_reopen_finished)
        thread.start()

    def _on_reopen_result(self, payload) -> None:
        """Bound slot for the reopen worker's success signal (GUI thread)."""
        # The result is matched to its request by id, not by "is the thread
        # still the current one".  The id is only replaced by a *new* request,
        # so the binding does not depend on the order in which Qt delivers
        # the result and the thread-finished signals.
        thread = self.sender()
        request_id = getattr(thread, "request_id", None)
        if request_id is None or request_id != self._reopen_request_id:
            self.transcriptReopened.emit(
                None,
                "Stale reopen result: the selected job or source changed during the load.",
            )
            return
        try:
            session, rows, language = payload
        except (TypeError, ValueError):
            self.transcriptReopened.emit(None, "Reopen failed: malformed result")
            return
        job_id = getattr(thread, "job_id", "")
        try:
            self._apply_prepared_transcript(session, rows, language, job_id)
        except Exception as exc:  # noqa: BLE001 - surfaced to UI
            self.transcriptReopened.emit(None, str(exc))
            return
        self.transcriptReopened.emit(session, "")

    def _on_reopen_error(self, message: str) -> None:
        """Bound slot for the reopen worker's failure signal."""
        self.transcriptReopened.emit(None, message)

    def _on_reopen_finished(self) -> None:
        """Bound slot for the reopen thread finishing."""
        thread = self.sender()
        if thread is self._reopen_thread:
            self._reopen_thread = None
            self._reopen_token = None
        if thread is not None:
            thread.deleteLater()

    def _on_transcript_thread_finished(self) -> None:
        thread = self.sender()
        if thread is self._transcript_thread:
            self._transcript_thread = None
        thread.deleteLater()
        self.transcriptStateChanged.emit(self.transcript_state, self.transcript_message)

    def _on_project_event(self, reason: str) -> None:
        if reason in {"session_loaded", "session_cleared"}:
            self.sessionChanged.emit()
        elif reason == "transcript_loaded":
            self.sessionChanged.emit()
        elif reason == "source_changed":
            source = self.project.session.source if self.project.session else None
            if source is not None:
                self.sourceChanged.emit(source)
        elif reason == "metadata_loaded":
            metadata = self.project.session.metadata if self.project.session else None
            if metadata is not None:
                self.metadataChanged.emit(metadata)
        elif reason == "mode_changed":
            self.modeChanged.emit(self.project.mode)
        elif reason in {
            "narration_changed",
            "exact_row_changed",
            "narration_saved",
            "exact_rows_saved",
        }:
            self.projectDirty.emit(self.dirty.count(self.project.mode))

    def reset(self) -> None:
        """Restore the pristine demo project (used by the demo-mode switch)."""
        self.log_entries_clear()
        self.jobs.clear()
        for job in demo_data.build_demo_jobs():
            self.jobs.add(job)
        self.load_demo_project()
        self.projectDirty.emit(0)

    def log_entries_clear(self) -> None:
        self._log_entries.clear()

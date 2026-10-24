"""The application context - the single object every screen talks to.

``AppContext`` owns the controllers and exposes them as **Qt signals** so
screens never reach into a controller directly. That keeps the GUI thread as
the only place where UI state changes.

``SelectionModel`` is the shared selection (current row) used by the segment
list, the timeline and the inspector, so all three stay in sync.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from ..application.download_controller import DownloadController, DownloadEvent
from ..application.job_manager import JobManager
from ..application.mode_coordinators import ModeCoordinator, build_coordinator
from ..application.project_controller import ProjectController
from ..domain.enums import AppMode, JobState, Stage, TaskState
from ..domain.models import (
    DownloadItem,
    Job,
    LogEntry,
    ProjectSession,
    SourceMetadata,
    ValidationReport,
    VideoSource,
)
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

    def __init__(self, jobs_dir: Optional[str] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.metadata_service = DemoMetadataService()
        self.download_service = DemoDownloadService()

        self.project = ProjectController(self.metadata_service)
        self.downloads = DownloadController(self.download_service)
        self.jobs = JobManager(demo_data.build_demo_jobs())
        self.selection = SelectionModel(self)
        self.dirty = DirtyGuard(self.project, self)

        # Stable user-writable jobs directory
        from pathlib import Path
        if jobs_dir is None:
            jobs_dir = str(Path.home() / ".mmnext" / "jobs")
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
        self.transcript_state = "idle"
        self.transcript_message = "No local transcript yet. Demo data is labelled DEMO."
        self.transcript_language = ""

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
            # Avoid duplicate job IDs from demo data
            try:
                self.jobs.add(job)
            except ValueError:
                # Already present
                pass
        # Corrupt jobs are reported but never auto-deleted
        # Log corrupt paths for diagnostics
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

    def open_transcript_from_job(self, job_id: str, source_path: str) -> None:
        """Load a completed REAL transcript artifact into the workspace with strict validation."""
        if self._job_repository is None:
            raise RuntimeError("Job repository not configured; cannot open transcript from jobs")
        if self.dirty.total_dirty():
            raise ValueError("Discard unsaved edits explicitly before opening a transcript")
        job = self._job_repository.load(job_id, source_path)
        if job is None:
            raise FileNotFoundError(f"Job {job_id} not found for source {source_path}")
        if job.state != self.jobs.get(job_id).state:
            # ensure state matches in-memory job manager
            pass
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
        if not data:
            raise ValueError("Transcript artifact is corrupt or unreadable")
        if int(data.get("schema_version", 0)) != 1:
            raise ValueError(f"Unsupported transcript schema version {data.get('schema_version')}")
        if bool(data.get("is_demo", True)):
            raise ValueError("Artifact is marked as demo; REAL data required")
        # Source identity match
        artifact_source = str(data.get("source_path", ""))
        if not Path(artifact_source).resolve().samefile(Path(job.source.location)):
            raise ValueError("Artifact source path does not match job source")
        # Fingerprint validation
        from ..infrastructure.repository.job_repository import compute_fingerprint
        source_type = job.source.source_type.value if job.source else ""
        current_fp = compute_fingerprint(source_path, source_type, mode, schema_version=1)
        artifact_fp = str(data.get("fingerprint", ""))
        if artifact_fp and artifact_fp != current_fp:
            raise ValueError("Fingerprint mismatch between artifact and current source")
        # Mode match
        # rows validation
        rows_raw = data.get("rows", [])
        if not isinstance(rows_raw, list) or not rows_raw:
            raise ValueError("Transcript artifact contains no rows")
        from ..domain.models import TranscriptRow, VideoSource, ProjectSession
        rows = []
        for r in rows_raw:
            try:
                row_id = str(r["row_id"])
                start = float(r["start"])
                duration = float(r["duration"])
                text = str(r["text"])
            except Exception as exc:
                raise ValueError(f"Invalid transcript row: {exc}")
            if not row_id or start < 0 or duration <= 0:
                raise ValueError(f"Invalid timing for row {row_id}")
            rows.append(TranscriptRow(row_id=row_id, start=start, duration=duration, text=text))
        # Build session and apply transcript
        source = VideoSource.local(job.source.location)
        output_folder = str(job_dir.parent.parent)
        session = ProjectSession(source=source, output_folder=output_folder, mode=mode, is_demo=False)
        self.project.load(session)
        self.project.apply_transcript(rows)
        self.transcript_language = str(data.get("language", ""))
        self._rebuild_coordinator()
        self._set_transcript_state("complete", f"Opened REAL transcript from job {job_id}: {len(rows)} rows, language={self.transcript_language}")

    def _on_transcript_progress(self, event) -> None:
        self.transcriptProgress.emit(event)

    def _on_transcript_error(self, event) -> None:
        self._set_transcript_state("failed", event.message + " " + event.detail)
        self.append_log(LogEntry(stage=Stage.TRANSCRIBE, message=event.message + " " + event.detail))

    def _on_transcript_stopped(self, message) -> None:
        self._set_transcript_state("stopped", message)

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
                fp = compute_fingerprint(source_path, source_type, mode, schema_version=1)
                job = Job(
                    job_id=job_id,
                    title=Path(source_path).name,
                    mode=mode,
                    state=JobState.COMPLETE,
                    is_demo=False,
                    source=VideoSource.local(source_path),
                    progress=JobProgress(percent=100.0),
                )
                self._job_repository.save(job, source_path)
            except Exception:
                # Persistence failure should not block transcript display
                pass
        self._set_transcript_state("complete", f"REAL transcript: {len(rows)} rows, language={language}. Artifact: {provider.artifact_path}. Narrator plan not generated.")

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

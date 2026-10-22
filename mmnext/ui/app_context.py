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
from ..application.job_service import JobService
from ..application.mode_coordinators import ModeCoordinator, build_coordinator
from ..application.narrator_coordinator import NarratorPlanCoordinator
from ..application.project_controller import ProjectController
from ..application.runtime_service import RuntimeService
from ..domain.enums import AppMode, JobState, Stage, TaskState
from ..domain.events import ProgressEvent
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

    # splitter
    splitterProgress = Signal(object)
    splitterStateChanged = Signal(str, str)

    # exact dubbing render
    exactRenderProgress = Signal(object)
    exactRenderStateChanged = Signal(str, str)

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
        self._jobs = JobService(self._jobs_dir)
        self._runtime = RuntimeService()
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

        self._exact_render_thread = None
        self.exact_render_state = "idle"
        self.exact_render_message = "No exact dubbing render yet."

        self._splitter_thread = None
        self.splitter_state = "idle"
        self.splitter_message = "No splitter run yet."

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

    @property
    def _job_repository(self):
        """Backwards-compatible view onto the application job facade."""
        return self._jobs.repository

    @_job_repository.setter
    def _job_repository(self, repository) -> None:
        self._jobs.repository = repository

    def detect_dependencies(self) -> dict:
        return self._runtime.detect()

    def _load_recoverable_jobs_from_repo(self) -> None:
        if not self._job_repository:
            return
        scan = self._jobs.scan()
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
        provider = self._jobs.create_transcript_provider(
            media_path, session.mode, is_demo=False
        )
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

    def export_exact_dubbing(self, output_path: Optional[str] = None) -> str:
        if self.project.session is None:
            raise ValueError("No project session")
        report = self.validate(AppMode.EXACT_DUBBING)
        if report.errors:
            raise ValueError(f"Exact dubbing validation failed: {report.summary}")
        rows = self.project.session.exact_rows
        if not rows:
            raise ValueError("No exact-dubbing rows to export")
        payload = [
            {
                # The legacy contract uses the positional index as ``id``; the
                # source row id travels in the extra ``row_id`` key, which the
                # legacy reader tolerates.
                "id": index,
                "row_id": row.row_id,
                "start": row.start,
                "duration": row.duration,
                "original": row.original,
                "burmese": row.burmese,
                "gender": getattr(row.gender, "value", row.gender),
            }
            for index, row in enumerate(rows)
        ]
        from pathlib import Path

        from ..domain.paths import atomic_write_json

        if output_path is None:
            target_dir = Path(self.project.session.output_folder or self._jobs_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            path = target_dir / "translated_gender.json"
        else:
            path = Path(output_path)
        atomic_write_json(path, payload)
        return str(path)

    @property
    def exact_render_running(self) -> bool:
        return self._exact_render_thread is not None and self._exact_render_thread.isRunning()

    def start_exact_dubbing_render(self, video_path: str = "", output_path: str = "", settings: Optional[dict] = None) -> None:
        if self.exact_render_running:
            raise RuntimeError("An exact dubbing render is already in progress")
        session = self.project.session
        if session is None:
            raise ValueError("No project session")
        rows = self.project.session.exact_rows
        if not rows:
            raise ValueError("No exact-dubbing rows to render")
        report = self.validate(AppMode.EXACT_DUBBING)
        if report.errors:
            raise ValueError(f"Exact dubbing validation failed: {report.summary}")
        duration = float(session.total_duration())
        if duration <= 0:
            raise ValueError("No source duration to render against")
        source_path = video_path or (session.source.location if session.source else "")
        target_path = output_path or str(
            Path(session.output_folder or self._jobs_dir) / "final_exact_gender_dub.mp4"
        )
        cache_dir = str(Path(self._jobs_dir) / "exact_dubbing_tts")
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        from ..application.exact_dubbing_service import ExactDubbingService
        from .exact_dubbing_render_worker import ExactDubbingRenderThread

        settings = dict(settings or {})
        settings.setdefault("tts_cache_dir", cache_dir)
        settings.setdefault("voice", "my-MM-NilarNeural")
        settings.setdefault("rate", 1.0)
        # The caller's duration travels as a claim: the renderer compares it
        # with the probed media and reports a source change.
        settings.setdefault("total_duration", duration)

        # The UI never imports infrastructure: the application facade owns the
        # real FFmpeg renderer and the real Edge TTS synthesiser.  The log
        # callback is handed to both, so a REAL failure keeps its reason.
        service = ExactDubbingService(self._jobs_dir)

        # ``translated_gender.json`` is the contract between the translation
        # step and the render step.  The render consumes the exported file, so
        # a drifted or unreadable translation refuses the render instead of
        # producing a dub that does not match the source rows.
        translation_path = str(
            Path(self._jobs_dir) / "exact_dubbing" / "translated_gender.json"
        )
        self.export_exact_dubbing(translation_path)
        service.validate_translation(translation_path, rows)

        coordinator = service.create_coordinator(
            settings=settings, log=self._on_exact_render_log
        )
        # A demo session can never be announced as a REAL render.
        is_demo = bool(session.is_demo) or coordinator.is_demo
        thread = ExactDubbingRenderThread(
            coordinator, rows, source_path, duration, target_path, settings, parent=self
        )
        self._exact_render_thread = thread
        thread.progress.connect(self._on_exact_render_progress)
        thread.log.connect(self._on_exact_render_log)
        thread.result.connect(self._on_exact_render_result)
        thread.error.connect(self._on_exact_render_error)
        thread.finished.connect(self._on_exact_render_finished)
        self._set_exact_render_state("running", f"{'DEMO' if is_demo else 'REAL'} exact dubbing render: TTS -> fit -> render.")
        thread.start()

    def stop_exact_dubbing_render(self) -> None:
        if self.exact_render_running:
            self._exact_render_thread.stop()
            # The stop is honoured between synthesis rows and after the render
            # stage; FFmpeg itself is never killed mid-flight.
            self._set_exact_render_state(
                "stopping",
                "Stop requested; the run stops at the next stage boundary.",
            )

    def _set_exact_render_state(self, state: str, message: str) -> None:
        self.exact_render_state = state
        self.exact_render_message = message
        self.exactRenderStateChanged.emit(state, message)

    def _on_exact_render_progress(self, event) -> None:
        self.exactRenderProgress.emit(event)

    def _on_exact_render_log(self, message: str) -> None:
        self.append_log(LogEntry(message=message, stage=Stage.IDLE))

    def _on_exact_render_result(self, result) -> None:
        # The speed-fit warnings are part of the result and must reach the
        # user: a segment that needed 1.4x speed is a translation problem.
        for warning in getattr(result, "warnings", []) or []:
            self.append_log(LogEntry(message=str(warning), stage=Stage.RENDER))
        if getattr(result, "stopped", False):
            self._set_exact_render_state("stopped", "Exact dubbing render stopped.")
        elif getattr(result, "ok", False):
            label = "DEMO" if getattr(result, "is_demo", True) else "REAL"
            self._set_exact_render_state("done", f"{label} exact dubbing render finished: {getattr(result, 'output_path', '')}")
        else:
            self._set_exact_render_state("failed", getattr(result, "message", "") or "Exact dubbing render failed.")

    def _on_exact_render_error(self, message: str) -> None:
        self._set_exact_render_state("failed", f"Exact dubbing render failed: {message}")

    def _on_exact_render_finished(self) -> None:
        thread = self.sender()
        if thread is self._exact_render_thread:
            self._exact_render_thread = None
        if thread is not None:
            thread.deleteLater()

    @property
    def splitter_running(self) -> bool:
        return self._splitter_thread is not None and self._splitter_thread.isRunning()

    def plan_splitter(
        self,
        part_seconds: Optional[float] = None,
        max_extra_wait: float = 5.0,
        smart_cut: bool = False,
        pause_times: Optional[list[float]] = None,
    ) -> list:
        if self.project.session is None:
            raise ValueError("No project session")
        duration = float(self.project.session.total_duration())
        if duration <= 0:
            raise ValueError("No source duration to plan against")
        part_seconds = float(part_seconds or 60.0)
        from ..services.adapters.splitter import DemoSplitterPlanner

        planner = DemoSplitterPlanner()
        parts = planner.plan(duration, part_seconds, max_extra_wait, pause_times or [], smart_cut)
        self.project.set_split_parts(parts)
        self.sessionChanged.emit()
        return parts

    def start_splitter_render(self, video_path: str = "", output_dir: str = "", settings: Optional[dict] = None) -> None:
        if self.splitter_running:
            raise RuntimeError("A splitter render is already in progress")
        session = self.project.session
        if session is None:
            raise ValueError("No project session")
        parts = self.project.session.split_parts
        selected = [part for part in parts if getattr(part, "include", True)]
        if not selected:
            raise ValueError("No selected parts to render")
        source_path = video_path or (session.source.location if session.source else "")
        target_dir = output_dir or str(Path(session.output_folder or self._jobs_dir) / "splitter")
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        from ..services.adapters.splitter import DemoSplitterPlanner, DemoSplitterRenderer, LegacySplitterRenderer
        from .splitter_render_worker import SplitterRenderThread
        from ..application.splitter_render_coordinator import SplitterRenderCoordinator

        renderer = LegacySplitterRenderer() if not session.is_demo else DemoSplitterRenderer()
        is_demo = session.is_demo or not renderer.available()
        if is_demo:
            renderer = DemoSplitterRenderer()
        coordinator = SplitterRenderCoordinator(planner=DemoSplitterPlanner(), renderer=renderer, is_demo=is_demo)
        settings = dict(settings or {})
        settings.setdefault("ratio", session.output_ratio.value)
        settings.setdefault("fill", session.frame_fill.value)
        thread = SplitterRenderThread(coordinator, parts, source_path, target_dir, settings, parent=self)
        self._splitter_thread = thread
        thread.progress.connect(self._on_splitter_progress)
        thread.log.connect(self._on_splitter_log)
        thread.result.connect(self._on_splitter_result)
        thread.error.connect(self._on_splitter_error)
        thread.finished.connect(self._on_splitter_finished)
        self._set_splitter_state("running", f"{'DEMO' if is_demo else 'REAL'} splitter render: plan -> render parts.")
        thread.start()

    def stop_splitter_render(self) -> None:
        if self.splitter_running:
            self._splitter_thread.stop()
            self._set_splitter_state("stopping", "Stop requested; finishing current part.")

    def _set_splitter_state(self, state: str, message: str) -> None:
        self.splitter_state = state
        self.splitter_message = message
        self.splitterStateChanged.emit(state, message)

    def _on_splitter_progress(self, event) -> None:
        self.splitterProgress.emit(event)

    def _on_splitter_log(self, message: str) -> None:
        self.append_log(LogEntry(message=message, stage=Stage.IDLE))

    def _on_splitter_result(self, result) -> None:
        if getattr(result, "stopped", False):
            self._set_splitter_state("stopped", "Splitter render stopped.")
        elif getattr(result, "ok", False):
            label = "DEMO" if getattr(result, "is_demo", True) else "REAL"
            self._set_splitter_state("done", f"{label} splitter render finished: {len(getattr(result, 'output_paths', []))} parts.")
        else:
            self._set_splitter_state("failed", getattr(result, "message", "") or "Splitter render failed.")

    def _on_splitter_error(self, message: str) -> None:
        self._set_splitter_state("failed", f"Splitter render failed: {message}")

    def _on_splitter_finished(self) -> None:
        thread = self.sender()
        if thread is self._splitter_thread:
            self._splitter_thread = None
        if thread is not None:
            thread.deleteLater()

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

        translator = LegacyNarratorTranslationAdapter(api_key=None)
        tts = LegacyEdgeTtsAdapter(cache_dir=cache_dir)
        renderer = LegacySmartSyncRenderer()
        is_demo = not (
            translator.available() and tts.available() and renderer.available()
        )
        if is_demo:
            translator = DemoTranslationProvider()
            tts = DemoSpeechSynthesizer(cache_dir=cache_dir)
            renderer = DemoSmartSyncRenderer()

        settings = dict(settings or {})
        settings.setdefault("tts_cache_dir", cache_dir)
        settings.setdefault(
            "translation_checkpoint",
            str(Path(self._jobs_dir) / "narrator_translation_checkpoint.json"),
        )
        settings.setdefault("context", "")
        settings.setdefault("glossary", {})

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
            f"{'DEMO' if is_demo else 'REAL'} narrator pipeline: plan -> translate -> synthesise -> render.",
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
        """Validate a completed REAL transcript off the GUI thread.

        Delegates all repository/artifact validation to the application job
        service and touches **no** project state.  The caller applies the result
        on the GUI thread after checking that the request is still current.

        Returns ``(session, rows, language)``.
        """
        if self.dirty.total_dirty():
            raise ValueError("Discard unsaved edits explicitly before opening a transcript")
        if self._reopen_token is not None and self._reopen_token != (job_id, source_path):
            raise ValueError(
                "Stale reopen request: the selected job or source changed; reopen again."
            )
        return self._jobs.prepare_transcript_from_job(job_id, source_path)

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

    def _reset_transcript_progress_after_persistence_failure(self, exc: Exception) -> None:
        """Never leave a stale 100% progress bar after a persistence failure."""
        self.transcriptProgress.emit(
            ProgressEvent(
                percent=0.0,
                stage=Stage.TRANSCRIBE,
                message="Transcript wrote, but job metadata could not be persisted; restart required.",
            )
        )
        self._set_transcript_state("failed", f"Failed to persist transcript job: {exc}")

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
                job = self._jobs.persist_completed_transcript(provider)
                self._register_job(job)
            except Exception as exc:
                self._reset_transcript_progress_after_persistence_failure(exc)
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

"""Main window for MMNext Movie Recap Pro.

The shell follows the global-shell contract in ``Agent.md`` section 6.1:

* a left navigation rail,
* a top bar carrying the project / job name, the source status, the
  GPU / FFmpeg status, the language, the save indicator and a global stop
  action,
* a central page stack,
* an optional bottom log drawer that expands without blocking the workspace,
* a consistent set of keyboard shortcuts and an explicit focus order.

Every screen receives the shared :class:`~mmnext.ui.app_context.AppContext`
and talks to it through signals only.
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..domain.enums import AppMode, JobState, TaskState
from ..domain.models import Job, ValidationReport
from .app_context import AppContext
from .navigation.nav_rail import NavRail, NavTarget
from .screens.analyze_screen import AnalyzeScreen
from .screens.download_screen import DownloadScreen
from .screens.home_screen import HomeScreen
from .screens.import_screen import ImportScreen
from .screens.jobs_screen import JobsScreen
from .screens.settings_screen import SettingsScreen
from .theme.palette import Palette
from .theme.stylesheet import build_stylesheet
from .widgets.confirm import confirm_before_discard
from .widgets.status_chip import StatusChip
from .workspace.log_drawer import LogDrawer
from .workspace.workspace_screen import WorkspaceScreen
from .workers import DownloadWorkerThread

__all__ = ["MainWindow"]


#: ``(shortcut, nav target)`` for the page stack.
_PAGE_SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Ctrl+1", NavTarget.HOME),
    ("Ctrl+2", NavTarget.IMPORT),
    ("Ctrl+3", NavTarget.ANALYZE),
    ("Ctrl+4", NavTarget.DOWNLOADS),
    ("Ctrl+5", NavTarget.JOBS),
    ("Ctrl+6", NavTarget.WORKSPACE),
    ("Ctrl+7", NavTarget.SETTINGS),
)


class MainWindow(QMainWindow):
    """Application main window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MMNext Movie Recap Pro")
        self.setMinimumSize(1180, 760)

        self.context = AppContext()
        self.context.load_demo_project()

        self._screens: Dict[str, QWidget] = {}
        self._shortcuts: list[QShortcut] = []
        self._current_job: Optional[Job] = None
        self._validation: Optional[ValidationReport] = None

        self._setup_ui()
        self._setup_shortcuts()
        self._bind_context()

        self.navigate_to(NavTarget.HOME)

    # --------------------------------------------------------------------- #
    # UI construction
    # --------------------------------------------------------------------- #
    def _setup_ui(self) -> None:
        self.setStyleSheet(build_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        main_area = QWidget()
        main_layout = QHBoxLayout(main_area)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.nav = NavRail()
        self.nav.navigate.connect(self.navigate_to)
        main_layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        self._register_screens()
        main_layout.addWidget(self.stack, 1)

        root.addWidget(main_area, 1)

        # The drawer must be free to reach its 240px expanded height, so no
        # maximum height is imposed here.
        self.log_drawer = LogDrawer()
        self.log_drawer.clearRequested.connect(self._clear_log)
        root.addWidget(self.log_drawer)

    def _build_top_bar(self) -> QWidget:
        top = QWidget()
        top.setObjectName("topBar")
        top.setStyleSheet(
            f"""
            QWidget#topBar {{
                background: {Palette.BG_TOOLBAR};
                border-bottom: 1px solid {Palette.BORDER};
            }}
            """
        )

        layout = QHBoxLayout(top)
        layout.setContentsMargins(14, 7, 14, 7)
        layout.setSpacing(8)

        self.title_label = QLabel("MMNext")
        self.title_label.setStyleSheet(
            f"color: {Palette.TEXT}; font-weight: 800; font-size: 14px;"
        )
        layout.addWidget(self.title_label)

        self.project_label = QLabel("No project")
        self.project_label.setProperty("role", "h3")
        self.project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.project_label)

        self.demo_badge = QLabel("DEMO")
        self.demo_badge.setStyleSheet(
            f"color: {Palette.WARNING}; font-weight: 800; font-size: 10px;"
        )
        layout.addWidget(self.demo_badge)

        layout.addStretch(1)

        # -- status chips ---------------------------------------------------- #
        self.job_chip = StatusChip("Job", "none", Palette.TEXT_FAINT)
        layout.addWidget(self.job_chip)

        self.source_chip = StatusChip("Source", "none", Palette.TEXT_FAINT)
        layout.addWidget(self.source_chip)

        self.ffmpeg_chip = StatusChip("FFmpeg", "not installed", Palette.TEXT_FAINT)
        layout.addWidget(self.ffmpeg_chip)

        self.gpu_chip = StatusChip("GPU", "not detected", Palette.TEXT_FAINT)
        layout.addWidget(self.gpu_chip)

        self.language_chip = StatusChip("Language", "-", Palette.TEXT_MUTED)
        layout.addWidget(self.language_chip)

        self.save_chip = StatusChip("Saved", "yes", Palette.SUCCESS)
        layout.addWidget(self.save_chip)

        # -- actions --------------------------------------------------------- #
        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("variant", "danger")
        self.stop_button.setToolTip("Stop every running job and download")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._global_stop)
        layout.addWidget(self.stop_button)

        self.reset_button = QPushButton("Reset demo")
        self.reset_button.setProperty("variant", "ghost")
        self.reset_button.setToolTip("Restore the pristine demo project")
        self.reset_button.clicked.connect(self._reset_demo)
        layout.addWidget(self.reset_button)

        return top

    # --------------------------------------------------------------------- #
    # Screens
    # --------------------------------------------------------------------- #
    def _register_screens(self) -> None:
        screen_map: list[Type[QWidget]] = [
            HomeScreen,
            ImportScreen,
            AnalyzeScreen,
            DownloadScreen,
            JobsScreen,
            WorkspaceScreen,
            SettingsScreen,
        ]
        for cls in screen_map:
            screen = cls()
            if hasattr(screen, "bind"):
                screen.bind(self.context)
            self.stack.addWidget(screen)
            key = getattr(screen, "screen_key", None)
            if key:
                self._screens[key] = screen

        self._workspace = self._screens.get(NavTarget.WORKSPACE)

    def navigate_to(self, target: str) -> None:
        """Public navigation used by the rail, the screens and the shortcuts."""
        screen = self._screens.get(target)
        if screen is None:
            target = NavTarget.HOME
            screen = self._screens.get(target)
        if screen is None:
            return
        self.nav.set_active(target)
        self.stack.setCurrentWidget(screen)
        if hasattr(screen, "on_activate"):
            screen.on_activate()
        title = self._screen_title(target)
        self.setWindowTitle(f"MMNext Movie Recap Pro - {title}")

    def _screen_title(self, target: str) -> str:
        return {
            NavTarget.HOME: "Home",
            NavTarget.IMPORT: "Import",
            NavTarget.ANALYZE: "Analyze",
            NavTarget.DOWNLOADS: "Downloads",
            NavTarget.JOBS: "Jobs",
            NavTarget.WORKSPACE: "Workspace",
            NavTarget.SETTINGS: "Settings",
        }.get(target, "Home")

    # --------------------------------------------------------------------- #
    # Keyboard shortcuts and focus order
    # --------------------------------------------------------------------- #
    def _setup_shortcuts(self) -> None:
        for sequence, target in _PAGE_SHORTCUTS:
            shortcut = QShortcut(QKeySequence(sequence), self)
            # The target travels on the shortcut itself rather than in a
            # lambda closure: a closure capturing ``self`` would create a
            # reference cycle that survives interpreter shutdown.
            shortcut.setProperty("navTarget", target)
            shortcut.activated.connect(self._on_shortcut_activated)
            self._shortcuts.append(shortcut)

        drawer = QShortcut(QKeySequence("Ctrl+J"), self)
        drawer.activated.connect(self.log_drawer.toggle)
        self._shortcuts.append(drawer)

        collapse = QShortcut(QKeySequence("Esc"), self)
        collapse.activated.connect(self._collapse_drawer)
        self._shortcuts.append(collapse)

        save = QShortcut(QKeySequence("Ctrl+S"), self)
        save.activated.connect(self._save_working_set)
        self._shortcuts.append(save)

        stop = QShortcut(QKeySequence("Ctrl+."), self)
        stop.activated.connect(self._global_stop)
        self._shortcuts.append(stop)

        # Explicit focus order: the rail, then the page stack, then the
        # drawer. This keeps keyboard navigation predictable.
        order = [self.nav, self.stack, self.log_drawer]
        for first, second in zip(order, order[1:]):
            QWidget.setTabOrder(first, second)

    def _on_shortcut_activated(self) -> None:
        """Bound slot for the page-navigation shortcuts."""
        shortcut = self.sender()
        if not isinstance(shortcut, QShortcut):
            return
        raw = shortcut.property("navTarget")
        if not raw or not NavTarget.is_valid(raw):
            return
        self.navigate_to(raw)

    # --------------------------------------------------------------------- #
    # Context binding
    # --------------------------------------------------------------------- #
    def _bind_context(self) -> None:
        context = self.context

        context.modeChanged.connect(self._on_mode_changed)
        context.sessionChanged.connect(self._on_session_changed)
        context.sourceChanged.connect(self._on_source_changed)
        context.metadataChanged.connect(self._on_metadata_changed)
        context.logAppended.connect(self.log_drawer.append_log)
        context.jobUpdated.connect(self._on_job_updated)
        context.jobStateChanged.connect(self._on_job_state_changed)
        context.validationChanged.connect(self._on_validation_changed)
        context.downloadStateChanged.connect(self._on_download_state_changed)
        context.dirty.dirtyChanged.connect(self._on_dirty_changed)
        context.transcriptStateChanged.connect(self._on_transcript_state)
        context.transcriptReopened.connect(self._on_transcript_reopened)

        # The download simulation runs on a worker thread.
        self._worker = DownloadWorkerThread(context.downloads, parent=self)
        self._worker.itemUpdated.connect(self._on_worker_item)
        self._worker.stateChanged.connect(self._on_worker_state)
        self._worker.message.connect(self.log_drawer.set_status)
        self._worker.start()

        self._refresh_dependencies()
        self._on_mode_changed(context.mode)
        self._on_session_changed()
        self._on_dirty(context.dirty.count(context.mode))

    def _refresh_dependencies(self) -> None:
        deps = self.context.detect_dependencies()
        ffmpeg = deps.get("ffmpeg")
        if ffmpeg is not None:
            self.ffmpeg_chip.set_state(
                ffmpeg.display,
                Palette.SUCCESS if ffmpeg.available else Palette.TEXT_FAINT,
            )
        gpu = deps.get("nvidia")
        if gpu is not None:
            self.gpu_chip.set_state(
                gpu.display,
                Palette.SUCCESS if gpu.available else Palette.TEXT_FAINT,
            )

    # -- context slots ------------------------------------------------------ #
    def _on_transcript_state(self, state, message) -> None:
        self.demo_badge.setText("DEMO" if self.context.session and self.context.session.is_demo else "REAL")
        active = self.context.transcript_running or state in {"running", "stopping"}
        self.reset_button.setEnabled(not active)
        self.job_chip.set_state(f"transcript: {state}", Palette.TEXT_MUTED)
        self.log_drawer.set_status(message)
        self._update_stop_state()

    def _on_transcript_reopened(self, session, error: str) -> None:
        """A reopened transcript is landed in the workspace.

        This completes the Jobs -> Workspace flow: the transcript is only
        useful where the rows and the mode panels are, so a successful reopen
        navigates there instead of leaving the user on the job list.
        """
        if error or session is None:
            self.log_drawer.set_status(f"Open failed: {error or 'no transcript was loaded'}")
            return
        self.log_drawer.set_status(
            f"REAL transcript opened: {len(session.transcript)} row(s)"
        )
        self.navigate_to(NavTarget.WORKSPACE)


    def _on_mode_changed(self, mode: AppMode) -> None:
        if self._workspace is not None and hasattr(self._workspace, "set_mode"):
            self._workspace.set_mode(mode)
        self._on_dirty(self.context.dirty.count(mode))

    def _on_session_changed(self) -> None:
        session = self.context.session
        self.demo_badge.setText("DEMO" if session is None or session.is_demo else "REAL")
        if session is not None and session.source is not None:
            self.project_label.setText(session.source.name)
        else:
            self.project_label.setText("No project")
        self._on_source_changed(session.source if session else None)
        if session is not None and session.metadata is not None:
            self._on_metadata_changed(session.metadata)

    def _on_source_changed(self, source) -> None:
        if source is None:
            self.source_chip.set_state("none", Palette.TEXT_FAINT)
            return
        kind = "YouTube" if source.is_remote else "Local"
        self.source_chip.set_state(f"{kind} - {source.name}", Palette.TEXT_MUTED)

    def _on_metadata_changed(self, metadata) -> None:
        if metadata is None:
            return
        self.language_chip.set_state(metadata.language or "-", Palette.TEXT_MUTED)

    def _on_job_updated(self, job: Job) -> None:
        self._current_job = job
        self.log_drawer.show_job(job)
        self.job_chip.set_state(job.job_id, Palette.TEXT_MUTED)
        self.job_chip.setToolTip(f"{job.title} - {job.state.value}")
        self._update_stop_state()

    def _on_job_state_changed(self, job: Job, _state) -> None:
        self._on_job_updated(job)

    def _on_validation_changed(self, report: ValidationReport) -> None:
        self._validation = report
        self.log_drawer.set_status(f"Validation: {report.summary}")
        self.log_drawer.set_expanded(True)

    def _on_download_state_changed(self, item, state) -> None:
        self.log_drawer.set_status(
            f"Download {item.item_id}: {state.value.replace('_', ' ')}"
        )
        self._update_stop_state()

    def _on_worker_item(self, item) -> None:
        self.log_drawer.set_status(f"Download {item.item_id}: {item.percent:.0f}%")
        self._update_stop_state()

    def _on_worker_state(self, item, state) -> None:
        self._update_stop_state()

    def _on_dirty(self, count: int) -> None:
        if count > 0:
            self.save_chip.set_state(f"{count} unsaved", Palette.WARNING)
        else:
            self.save_chip.set_state("yes", Palette.SUCCESS)

    def _on_dirty_changed(self, count: int, mode_value: str) -> None:
        """Show the unsaved count of the **active** mode only.

        The guard reports every mode separately, so an edit in the exact
        dubbing working set must not light up the chip while the narrator
        mode is on screen.
        """
        if mode_value != self.context.mode.value:
            return
        self._on_dirty(count)

    # --------------------------------------------------------------------- #
    # Commands
    # --------------------------------------------------------------------- #
    def _save_working_set(self) -> None:
        """Ctrl+S - mark the active working set as saved."""
        mode = self.context.mode
        if mode is AppMode.NARRATOR:
            self.context.project.mark_narration_clean()
        elif mode is AppMode.EXACT_DUBBING:
            self.context.project.mark_exact_rows_clean()
        self.log_drawer.set_status("Working set saved")
        self._on_dirty(self.context.dirty.count(mode))

    def _global_stop(self) -> None:
        """Stop every running download and request a stop on active jobs."""
        stopped = 0
        if self.context.transcript_running:
            self.context.stop_transcript()
            stopped += 1
        for item in self.context.download_items():
            if item.state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED):
                self.context.downloads.stop(item.item_id)
                stopped += 1

        for job in self.context.all_jobs():
            if job.is_demo:
                # Demo presets are static snapshots, not live work.
                continue
            if job.state is JobState.RENDERING:
                self.context.transition_job(job.job_id, JobState.STOP_REQUESTED)
                stopped += 1
            elif job.state in (JobState.PREPARING, JobState.VALIDATING):
                self.context.transition_job(job.job_id, JobState.CANCELLED)
                stopped += 1

        self.log_drawer.set_status(
            "Stop requested" if stopped else "Nothing is running"
        )
        self._update_stop_state()

    def _reset_demo(self) -> None:
        """Restore the pristine demo project.

        This throws away every unsaved edit, so the user is asked first.
        *Cancel* leaves the project exactly as it was.
        """
        if self.context.transcript_running:
            self.log_drawer.set_status("Stop transcription and wait for its checkpoint before resetting.")
            return
        if not confirm_before_discard(
            self, self.context, action="the demo project", allow_save=False
        ):
            self.log_drawer.set_status("Reset cancelled - nothing was discarded")
            return
        self.context.reset()
        self._current_job = None
        self.job_chip.set_state("none", Palette.TEXT_FAINT)
        self.log_drawer.show_job(None)
        self.log_drawer.set_status("Demo project restored")
        self.navigate_to(NavTarget.HOME)

    def _clear_log(self) -> None:
        self.context.log_entries_clear()
        self.log_drawer.set_log_text("")

    def _collapse_drawer(self) -> None:
        if self.log_drawer.expanded:
            self.log_drawer.set_expanded(False)

    def _update_stop_state(self) -> None:
        running = any(
            item.state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED)
            for item in self.context.download_items()
        )
        active_jobs = any(
            not job.is_demo
            and job.state in (JobState.RENDERING, JobState.PREPARING, JobState.VALIDATING)
            for job in self.context.all_jobs()
        )
        self.stop_button.setEnabled(running or active_jobs or self.context.transcript_running)

    # --------------------------------------------------------------------- #
    # Shutdown
    # --------------------------------------------------------------------- #
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self.context.transcript_running:
            self.context.stop_transcript()
            self.log_drawer.set_status("Stop requested. Wait for the current operation and checkpoint, then close again.")
            event.ignore()
            return
        # Closing the window throws away the unsaved edits, so ask first.
        if not confirm_before_discard(
            self, self.context, action="the current project"
        ):
            event.ignore()
            return
        worker = getattr(self, "_worker", None)
        if worker is not None:
            worker.shutdown()
        super().closeEvent(event)

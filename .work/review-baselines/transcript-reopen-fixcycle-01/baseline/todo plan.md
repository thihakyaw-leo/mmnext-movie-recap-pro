# MMNext Movie Recap Pro — Todo Plan

## Product strategy

Build the product in vertical milestones. The first milestone is UI-first and must be usable with demo data. Real media services are connected only after the UI contract, domain models, and job state model are stable.

## Current verified status — 2026-10-21

The project is **not complete**. The PySide6 shell, separate mode/domain contracts, job/checkpoint repository components, and local Whisper transcript slice exist. Strict real-media and live-UI transcript acceptance is documented in `checklist.md` § N.

Fresh verification for this documentation update: `pytest tests -q --confcutdir=tests -p no:cacheprovider` with the approved local media/model fixture and project-local FFmpeg tools enabled: **291 passed in 63.32s**. Focused saved-transcript tests: `pytest tests/test_transcript_open.py -q --confcutdir=tests -p no:cacheprovider` → **6 passed in 0.27s**. This does not establish full product or clean-machine readiness.

The Jobs screen and `AppContext.open_transcript_from_job()` contain an explicit open path, but it is **not yet a complete restart-to-Workspace flow**: normal `MainWindow` construction does not pass a persistent jobs directory, the transcript adapter writes transcript/checkpoint artifacts but does not create completed Job metadata, and the saved transcript fingerprint is not checked when reopening. Artifact JSON is also read synchronously from the UI action. Treat this as partially implemented, not end-to-end complete.

### Highest-priority next work: make persisted transcript reopening/recovery real end to end

- [ ] First obtain an independent, read-only NVIDIA Nemotron review of the current Step-5 transcript-reopen code using `outputs/nemotron-review-prompt-step5-transcript-reopen.md`; treat reported claims as unverified until checked against source/tests.
- [ ] Configure and document one persistent, user-writable jobs root in normal application startup; keep demo mode explicit.
- [ ] Persist a versioned REAL transcript Job record, including COMPLETE state and the committed artifact location, only after transcript validation and atomic artifact commit succeed.
- [ ] Make repository-backed Jobs listing include eligible completed REAL transcript jobs as well as recoverable incomplete jobs; opening remains explicit and must never auto-resume.
- [ ] Harden reopen validation: source identity and fingerprint, mode, job/artifact schema, completion state, row uniqueness, and timing bounds. Reject failures without demo fallback or source-row mutation.
- [ ] Move artifact reading/validation off the GUI thread and bind results only if the selected job/source is still current.
- [ ] Add UI/integration tests for normal startup, completed-job discovery, explicit open, corrupt/missing/incompatible artifacts, source/fingerprint/mode mismatch, no demo fallback, off-GUI-thread loading, and Exact Dubbing invariants.

Do not begin translation, TTS, or final video rendering until this persistence/recovery slice has a truthful end-to-end acceptance path. After it, prioritize a real Narrator vertical slice, then Exact Dubbing, Splitter, Common Editing, and release hardening.

## Phase 0 — Baseline and decisions

- [ ] Create a clean feature branch or isolated worktree for MMNext.

- [ ] Confirm whether the target root remains `recap-en-to-mm-main` or moves to a new `mmnext` package.

- [ ] Record Python version, supported Windows versions, PySide6 version, mpv integration approach, FFmpeg discovery strategy, and packaging target.

- [ ] Decide whether job metadata uses versioned JSON files, SQLite, or a hybrid. Prefer a small repository abstraction so the choice can change without UI rewrites.

- [ ] Define the canonical output/job-folder convention for narrator, exact dubbing, splitter, and common editing modes.

- [ ] Document which legacy behavior is preserved as-is and which behavior is intentionally redesigned.

- [ ] Add a migration note explaining that existing Tkinter/Tk worker modules and movie-recap CLI stages are reference/compatibility implementations during the transition.

## Phase 1 — UI-first shell (first implementation milestone)

> **Status: UI-shell milestone complete.** The original milestone run had 145
> passing tests; that count is historical, not current. The latest full-suite
> result is **291 passed** in the current status section above. Evidence is
> cited in `checklist.md` §§ B, K, N, and O.

### Application shell

- [x] Create a PySide6 entry point and main window.
  - `mmnext/main.py`, `mmnext/bootstrap.py`, `mmnext/ui/main_window.py`.

- [x] Add left navigation: Home, Import, Download, Workspace, Jobs, Settings.
  - `mmnext/ui/nav_rail.py`; targets `home, import, analyze, downloads, jobs,
  workspace, settings` (`NavTarget`).

- [x] Add top status bar with project name, source status, runtime status, and current task state.
  - `MainWindow` top bar: project label, demo badge, Source / FFmpeg / GPU /
  Language chips, save chip, job chip, global Stop button.

- [x] Add collapsible bottom log/progress drawer.
  - `mmnext/ui/widgets/log_drawer.py`; two tabs (Log / Progress), collapsed
  height 38, expanded 240, `Ctrl+J` toggles it.

- [x] Add a dark theme with readable contrast, keyboard focus, and scalable layouts.
  - `mmnext/ui/theme/stylesheet.py` (one global stylesheet),
  `mmnext/ui/theme/palette.py` (tokens); every screen is a `QScrollArea`.

- [x] Add application-level actions and shortcuts: open source, save, undo/redo placeholder, play/pause, stop, open job folder.
  - `MainWindow._setup_shortcuts()`; "open job folder" is the one item
  still open — the Jobs screen has Resume / Retry / Cancel but no
  Explorer action (see `checklist.md` § L).

### Demo mode

- [x] Create demo project data with a sample video metadata object, transcript rows, plan rows, split parts, and fake task progress events.
  - `mmnext/services/demo/demo_data.py` — 24 narration segments, 24 exact
  rows, split parts, overlays, deterministic metadata.

- [x] Add a “Demo Mode” indicator so simulated work is never confused with real production.
  - The `DEMO` badge in the top bar plus the `demo_badge` widget.

- [x] Provide deterministic fake jobs for downloading, preparing, validating, rendering, stopped, failed, and complete states.
  - `build_demo_jobs()` → 6 preset jobs covering those states.

- [x] Make the complete UI navigable without API keys, media files, FFmpeg, Whisper, or mpv.
  - `test_demo_mode_needs_no_api_key_or_network`,
  `test_context_uses_demo_services_only`,
  `test_architecture_gates.py::test_no_external_api_clients_in_milestone_one`.

### Import screen

- [x] Implement local-video picker.
  - `ImportScreen._browse()`.

- [ ] Implement drag-and-drop for local video.
  - Not implemented; the picker plus URL paste covers the milestone.

- [x] Implement YouTube URL input and basic URL validation.
  - `ImportScreen._import_clicked()` rejects non-YouTube hosts.

- [x] Add source-type cards and a clear Continue/Analyze action.
  - `ImportScreen` local / YouTube cards and the Import button.

- [x] Show accepted formats, file size, and initial source validation messages.
  - The picker filter lists the accepted extensions
  (`*.mp4 *.mkv *.mov *.avi *.webm *.m4v`), the card states that the path is
  validated but never opened, and the status line reports the validation
  result. File size is not shown yet.

### Analyze screen

- [x] Create metadata card with thumbnail placeholder, title, uploader, duration, URL, and available quality list.
  - `mmnext/ui/screens/analyze_screen.py`; the thumbnail is a placeholder
  widget, the quality list comes from `SourceMetadata.qualities`.

- [x] Keep Analyze separate from Download.
  - `AnalyzeScreen` and `DownloadScreen` are different screens.

- [ ] Add output-folder picker.
  - The output folder is a **Settings** field (`SettingsScreen.output_edit`),
  not a picker on the Analyze screen.

- [x] Add quality selection with a safe default.
  - `AnalyzeScreen.quality_combo`, populated from the metadata, first entry
  selected by default.

- [x] Add explicit Download button.
  - `AnalyzeScreen.download_button` → `context.enqueue_download(...)`.

- [x] Add a “Use local file” path that skips download.
  - `ImportScreen` accepts a local path; the local source is recorded without
  an enqueue.

### Download screen

- [x] Create a queue model and download task cards.
  - `DownloadScreen` + `mmnext/ui/widgets/progress_card.py` over a
  `QAbstractTableModel`/card list.

- [x] Implement visible percentage, bytes, speed, ETA, destination, and current filename using demo events.
  - `test_download_queue.py::test_card_shows_progress_metrics`.

- [x] Implement Pause, Resume, Stop, Retry, Open Folder button states.
  - `progress_card._update_buttons` derives each control from the task state.
  - "Open in workspace" is enabled for `COMPLETE` only.

- [x] Implement safe-stop confirmation only when necessary.
  - Stop is immediate in the demo; the destructive confirmations are reserved
  for discarding edits.

- [x] Add a task log drawer.
  - The bottom `LogDrawer` shows the job log and the progress tab.

- [ ] Add a resume capability label based on adapter support.
  - The demo pause is simulated and resumes from the last chunk index, not a
  byte-range resume. The label must be added with the real adapter.

### Production workspace

- [x] Build the Subtitle Edit-like workspace layout.
  - `mmnext/ui/workspace/workspace_screen.py`.

- [x] Left: segment/part list.
  - `mmnext/ui/workspace/segment_table.py` (narration, exact rows, parts,
  overlays — one `QTableView` per kind).

- [x] Center: mpv placeholder player with play/pause, seek, timecode, volume, fit/zoom.
  - `mmnext/ui/workspace/preview.py`; play/pause, a seek slider and a
  timecode label are present. **Volume and fit/zoom are not implemented.**

- [x] Bottom: timeline with playhead and segment markers.
  - `mmnext/ui/workspace/timeline.py`.

- [x] Right: inspector/settings panel.
  - `mmnext/ui/workspace/inspector.py` — mode-specific sections for
  narration and exact dubbing, plus a generic section.

- [x] Bottom drawer: logs, warnings, validation results, and progress.
  - `mmnext/ui/workspace/log_drawer.py`.

- [x] Preserve selection while panels refresh.
  - `test_selection_survives_a_data_refresh`.

- [x] Add mode switcher for Common Editing, Splitter, Narrator, and Exact Dubbing.
  - `mmnext/ui/workspace/mode_switcher.py`.

- [x] Add empty-state guidance for projects with no transcript or plan yet.
  - `DownloadScreen._update_empty_state` and the tables' empty states.

### Mode pages

- [x] Common Editing page with trim/range, overlays, ratio, fill, title, logo, extra text, and export placeholders.
  - `mode_panels/common_editing_panel.py` — ratio combo, fill combo, output
  folder, "Add overlay", "Render". Trim/range and the individual overlay
  kinds (title / logo / extra text) are **not** wired yet.

- [x] Splitter page with duration, smart cut, maximum wait, cut-plan table, overlay controls, and output folder.
  - `mode_panels/splitter_panel.py` — part count, selected duration, a
  selection badge, "Re-plan parts", "Select all", "Render parts", and the
  cut-plan table in the left segment table.
  - Smart cut, maximum extra wait, overlay controls and the output folder
  field are **not** wired yet.

- [x] Narrator page with transcript/plan list, narration editor, voice/rate controls, Smart Sync summary, and render action.
  - `mode_panels/narrator_panel.py` + the narration inspector section:
  transcript/plan list, narration editor, "Translate to Myanmar",
  "Regenerate summary", "Validate", "Save narration".
  - Voice/rate controls and the Smart Sync summary are **not** wired yet.

- [x] Exact Dubbing page with locked ID/start/duration/original columns, Burmese text editor, gender selector, validation summary, and render action.
  - `mode_panels/exact_dubbing_panel.py` + the exact inspector section:
  the ID/start/duration/original columns are read-only, the Burmese editor
  is editable, the gender selector maps to the voice, and Validate / Save
  translations are present.
  - The render action and the validation summary panel are **not** wired yet.

### Phase 1 acceptance gate

- [x] App launches and closes cleanly.
  - `test_window_builds`; `scripts/check_shell.py` → exit 0; the
  interpreter-exit crash was fixed earlier by replacing self-capturing
  lambdas with bound methods.

- [x] All navigation paths work with demo data.
  - `test_every_screen_can_be_opened` (all 7 targets),
  `test_navigation_from_the_rail`, `test_unknown_navigation_target_falls_back_to_home`.

- [x] No long-running demo task blocks the UI.
  - `test_download_progress_runs_on_a_worker_thread`,
  `test_workers.py::test_worker_runs_off_gui_thread`.

- [x] Pause/Resume/Stop buttons reflect task state correctly.
  - `test_download_queue.py::test_button_availability_per_state` and
  `test_global_stop_button_is_disabled_when_idle`.

- [x] Segment selection, timeline selection, and inspector selection stay synchronized.
  - `test_selecting_a_row_updates_the_inspector`,
  `test_selection_is_shared_with_the_context`,
  `test_selection_survives_a_data_refresh`,
  `test_timeline_seek_moves_the_preview`.

- [x] Unsaved-edit prompt works.
  - `mmnext/ui/widgets/confirm.py`; wired into `MainWindow._reset_demo`,
  `MainWindow.closeEvent` and `SettingsScreen._reset_demo`.
  - `test_unsaved_edits_prompt_before_a_destructive_reset`,
  `test_reset_confirms_and_then_discards`,
  `test_no_prompt_when_there_is_nothing_to_discard`,
  `test_the_prompt_counts_edits_in_every_working_set`,
  `test_closing_the_window_asks_before_discarding`.
  - A **mode switch needs no prompt** because narrator and exact dubbing are
  separate working sets (`test_mode_switching_keeps_unsaved_edits`).

- [x] The UI clearly distinguishes demo state from real state.
  - The `DEMO` badge in the top bar; the source chip shows "(demo)";
  `test_top_bar_shows_the_demo_state`.

- [x] PySide6 UI tests and basic smoke test pass.
  - Historical Phase 1 baseline: **145 passed**. Current full-suite result:
  **291 passed**, recorded in `checklist.md` § O.
  - `python scripts\check_shell.py` → exit 0.

## Phase 2 — Domain models and job state

> **Status: partially implemented and not fully wired into normal startup.**
> `JobRepository` provides versioned metadata/checkpoints, atomic writes,
> fingerprints, recovery scanning, and resume-eligibility checks. `AppContext`
> creates/scans it only when `jobs_dir` is supplied; `MainWindow` currently
> constructs `AppContext()` without one. The transcript adapter saves its
> artifact and checkpoint but does not persist completed Job metadata.

- [x] Define typed models and enums.
  - `mmnext/domain/models.py` (18 dataclasses), `mmnext/domain/enums.py`
  (12 enums), `mmnext/domain/events.py` (6 event dataclasses).

- [x] Define `ProgressEvent`, `LogEvent`, `ValidationIssue`, and `JobStateChanged` event contracts.
  - `ProgressEvent`, `LogEvent`, `StateEvent` (the job-state event),
  `ValidationEvent`, `ResultEvent`, `ErrorEvent` in
  `mmnext/domain/events.py`; `ValidationIssue` in `models.py`.

- [x] Define job state transitions and illegal-transition errors.
  - `mmnext/application/job_manager.py`;
  `test_illegal_transition_is_refused`, `test_every_allowed_transition_is_reachable`.

- [x] Implement project/job repository abstraction.
  - `mmnext/infrastructure/repository/job_repository.py` implements versioned
  disk-backed metadata/checkpoint persistence. Normal startup and completed
  transcript Job creation/listing remain unwired; see the priority slice above.

- [x] Implement schema versioning for current records.
  - Job metadata uses schema v1, checkpoints use the domain checkpoint schema,
  and transcript artifacts use schema v1. Migration hooks between versions
  are **not** implemented.

- [x] Implement atomic JSON/checkpoint writes.
  - `mmnext/domain/paths.py::atomic_write_text`;
  `test_workers.py::test_checkpoint_write_is_atomic`.

- [x] Implement source/settings/mode/schema fingerprint helpers.
  - `compute_fingerprint()` covers source identity and local file size/mtime,
  mode, schema version, and settings; the transcript adapter records its own
  source/model/language fingerprint. Reopen does **not** compare the saved
  transcript fingerprint with the current source; general artifact reuse and
  invalidation are incomplete.

- [x] Implement repository scan for recoverable and corrupt job records.
  - `JobRepository.scan()` discovers incomplete records and corrupt metadata.
  `AppContext` invokes it only when configured with `jobs_dir`; standard
  `MainWindow` startup does not currently supply that configuration.

- [ ] Wire repository-discovered jobs into the normal Jobs screen, including
  completed REAL transcript records.
  - The Jobs screen displays jobs already held by `JobManager`, and `AppContext`
  can add recoverable jobs after a configured scan. Normal startup does not
  configure the repository, and the scan does not add completed records.

## Phase 3 — Runtime adapters

### Media tools

- [ ] Implement FFmpeg/FFprobe discovery with configured path, bundled path, PATH, and clear error reporting.
  - Runtime status probing and transcript-specific FFmpeg/FFprobe calls exist,
  but configurable/bundled tool discovery and user-facing local-tool settings
  are not complete.

- [x] Implement local-file metadata probe adapter.
  - `services/adapters/metadata.py::LocalFileMetadataService` probes with
  FFprobe; the standard `AppContext` still uses `DemoMetadataService`.

- [x] Implement mpv playback adapter with a placeholder fallback.
  - `mmnext/infrastructure/player.py` → `create_player()` returns an mpv
  player when the binary is present and a `PlaceholderPlayer` otherwise.
  - The preview panel shows a friendly placeholder and a player label.

- [ ] Verify Windows process termination and cleanup behavior.
  - *Not started* — no child process is spawned yet.

### YouTube/download

- [x] Implement metadata-only yt-dlp extraction adapter.
  - `services/adapters/metadata.py::YouTubeMetadataService` requests metadata
  without downloading; it is not wired into standard `AppContext` startup.

- [ ] Implement quality/format mapping.
  - The demo provider supplies a deterministic `VideoQuality` list and the
  Analyze screen maps it to a combo; the yt-dlp mapping is not written.

- [ ] Implement download task adapter with structured progress.
  - The `DownloadService` protocol and the typed progress events exist;
  the yt-dlp adapter does not.

- [ ] Implement pause/resume only if the downloader can safely support it.
  - The demo simulates a pause. The real adapter must relabel the control
  if the downloader cannot byte-range resume.

- [ ] Persist download state and partial file information.
  - *Not started* — the checkpoint model has a `partial_path` field but
  nothing is written yet.

- [ ] Redact sensitive URL parameters from logs.
  - The demo never echoes the URL; the real helper is not written.

### Transcription

- [x] Wrap local faster-whisper transcription behind the transcript provider boundary.
  - Real FFprobe/FFmpeg/faster-whisper work runs through the transcript adapter
  and worker; it does not invoke translation or narrator planning.

- [x] Preserve explicit source-language selection and auto-detection.
  - Workspace language controls and detected-language results are covered by
  transcript tests.

- [x] Persist transcript artifact with source fingerprint and model metadata.
  - Versioned JSON is written atomically under source/mode/job-scoped paths.
  Loading after a normal application restart is still blocked by the wiring
  gaps above.

- [x] Add a verbatim read-only transcript preview and explicit source-row rules.
  - Raw transcript rows are not editable; Exact Dubbing preparation preserves
  source identity/text/timing and keeps Burmese blank. Saved transcript editing
  is not supported.

### Translation/planning

- [ ] Wrap existing narrator planner as an application service.

- [ ] Preserve glossary/story context, batching, audit, retries, and fallback behavior.

- [ ] Keep exact-dubbing translation as a separate contract.

- [ ] Do not route exact-dubbing through narrator summarization.

- [ ] Ensure external model credentials are optional in demo/offline mode.

### TTS/render

- [ ] Wrap Edge TTS behind `SpeechSynthesizer`.

- [ ] Add voice discovery/configuration.

- [ ] Preserve text/voice cache signatures.

- [ ] Wrap Smart Sync renderer.

- [ ] Wrap exact-duration renderer.

- [ ] Wrap splitter renderer.

- [ ] Use partial outputs and final validation before rename.

## Phase 4 — Narrator mode integration

- [ ] Connect source → Whisper → plan → translation → TTS → Smart Sync stages.

- [ ] Add stage progress and structured logs.

- [ ] Add safe stop at stage and segment boundaries.

- [ ] Add resume/reuse detection.

- [ ] Add batch-folder queue.

- [ ] Add narration editor save/re-render for selected segment.

- [ ] Show translation audit findings and unresolved issues.

- [ ] Add final video validation and output reveal.

## Phase 5 — Exact Dubbing mode integration

- [ ] Implement the complete prepare stage for YouTube captions, Whisper fallback, local transcript, and metadata.
  - Local REAL Whisper preparation exists. YouTube-caption preparation and
  end-to-end metadata persistence are not implemented.

- [x] Render source segments in a locked table.
  - The Exact Dubbing UI locks source ID, original text, start, and duration.

- [x] Implement Burmese translation editing with speaker-gender selection.
  - Editing is local UI/domain behavior only; no translation service is wired.

- [ ] Implement schema-compatible export to `translated_gender.json`.

- [x] Implement Exact Dubbing validation for missing/reordered/changed rows, Burmese text, gender, and source-duration drift.
  - The validation contract is tested. The UI gate stays closed until validation
  succeeds, but no production TTS/render adapter is connected.

- [ ] Connect exact TTS/render adapter with cache and speed fitting.

- [ ] Validate output duration and audio stream.

- [ ] Show `status.json`/`render_report.json` information in the UI.

- [ ] Add explicit warning that exact dubbing does not summarize or omit dialogue.

## Phase 6 — Splitter mode integration

- [ ] Connect split planner and audio pause detection.

- [ ] Show planned parts before render.

- [ ] Show cut reason: exact, pause, breath, quietest, or end.

- [ ] Add per-part output status and resume behavior.

- [ ] Add preview of ratio, fill, text, and part number.

- [ ] Add fingerprint-based skip/rebuild logic.

- [ ] Add batch splitter queue.

## Phase 7 — Common editing workspace

- [ ] Implement non-destructive timeline/range model.

- [ ] Add trim and range selection.

- [ ] Add overlay model and preview positioning.

- [ ] Add title/logo/extra text/blur-box support.

- [ ] Add ratio/fill/zoom/flip controls.

- [ ] Add export preset model.

- [ ] Add export validation and final artifact inspection.

## Phase 8 — Reliability, packaging, and release

- [ ] Add startup diagnostics for Python/runtime, FFmpeg, mpv, GPU/NVENC, TTS connectivity, and optional translation credentials.

- [ ] Add a user-facing diagnostics report.

- [ ] Add crash-safe recovery and orphan partial-file cleanup.

- [ ] Add structured log export.

- [ ] Add end-to-end tests using small fixture media.

- [ ] Add packaging strategy for Windows.

- [ ] Test on CPU-only machine and NVIDIA machine.

- [ ] Test non-ASCII paths and Myanmar text.

- [ ] Test pause/stop/resume across every major mode.

- [ ] Write user guide and migration notes.

- [ ] Run the complete checklist before beta tagging.

## Priority order

1. UI shell and demo mode.

1. Typed domain/state model.

1. Source intake and metadata flow.

1. Download queue.

1. Production workspace and mode pages.

1. Exact-dubbing adapter and validator.

1. Narrator adapter and Smart Sync.

1. Splitter adapter.

1. Common editing/export.

1. Packaging, diagnostics, and release hardening.

## Explicit non-goals for the first release

- Do not build a full nonlinear editor comparable to Premiere.

- Do not silently merge the exact-dubbing and narrator contracts.

- Do not add unsupported cloud upload or media sharing.

- Do not depend on a paid external API for the UI milestone.

- Do not rewrite all legacy processing code before proving the new UI and adapter boundaries.

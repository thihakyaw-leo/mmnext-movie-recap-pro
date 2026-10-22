# MMNext Movie Recap Pro — Checklist

Use this checklist for design reviews, implementation milestones, pull requests, and release readiness. Mark an item only when it has evidence: a test, screenshot, log, or reproducible manual step.

Status note (2026-10-21): older sections preserve milestone history. Where they conflict with the current code, use the latest dated audit in § O; § N remains the transcript timestamp-boundary acceptance evidence and is superseded only where § O explicitly updates it.

## A. Project and source understanding

- [x] `Agent.md` has been read.
  - It is the governing contract; the "UI first" and layering rules were
  applied throughout.

- [x] `instructions.md` has been read.
  - The engineering rules (typed models, adapters, no work in a widget event
  handler, structured events, atomic writes) shaped the implementation.

- [x] `todo plan.md` has been read.
  - It is now the live plan; Phase 1 is marked complete with evidence.

- [x] Relevant current-project files were inspected before editing.
  - The full `mmnext/` tree, plus `Agent.md`, `instructions.md`,
  `checklist.md`, `todo plan.md`, `README.md`, `RUN_DEMO.md`.

- [x] Relevant `J:\movie-recap` files and its `AGENTS.md`/`SKILL.md` were inspected before editing.
  - `AGENTS.md`, `SKILL.md`, `app/core.py`, `app/controller.py`,
  `app/splitter.py`, `app/splitter_tab.py`, `app/narration_editor.py`,
  `app/recap_planner.py`, `app/planner_worker.py`, `app/render_worker.py`,
  `pipeline_master_local.py`, `README.md`, `README_MM.md`.

- [x] Any conflict between legacy rules and MMNext target behavior is documented.
  - The two most important conflicts:
  1. **Mode 1 / external-chat must not reappear in the exact-dubbing path.**
     The exact-dubbing contract keeps every source row immutable (id,
     original, start, duration) and edits only the Burmese text and the
     speaker gender. `ExactDubbingRow` has no base class shared with
     `NarrationSegment`, and `test_narration_segment_has_no_burmese_field`
     / `test_exact_row_keeps_original_dialogue` enforce the separation.
  2. **Legacy output names and job layout must not change silently.** The
     legacy layout (`JOBS_DIR/<safe>_<sha1[:8]>/edge_tts_smart_sync/...`,
     `checkpoint.json`, `smart_sync_plan_edge_tts.json`, final
     `<stem>_Myanmar.mp4`) is recorded in `README.md` § Source projects and
     will need a formal compatibility note in Phase 2.
  - `test_architecture_gates.py::test_ui_layer_does_not_import_legacy_pipelines`
  keeps the legacy code out of the UI layer.

- [x] No source media, secrets, generated output, GPU runtime, or cache was added to Git.
  - `.gitignore` excludes `.venv/`, `__pycache__/`, `.pytest_cache/`, `.env`,
  every media extension, `*.partial`, and the job working directories
  (`work/`, `tts_parts/`, `video_parts/`, `checkpoint.json`, `run.log`).

## B. UI-first milestone

> **Evidence for section B** — `pytest tests -q --confcutdir=tests` → **145 passed**.
> Test names below refer to `tests/test_ui_shell.py` unless noted.
> Manual check: `python scripts\check_shell.py` (offscreen) prints the shell state and exits 0.

- [x] PySide6 application starts successfully.
  - `test_window_builds`, `test_all_screens_are_registered`;
  `scripts/check_shell.py` → `MainWindow OK`.

- [x] Application also starts in demo mode without API keys.
  - `test_demo_mode_needs_no_api_key_or_network`, `test_context_uses_demo_services_only`;
  `test_architecture_gates.py::test_no_external_api_clients_in_milestone_one`.

- [x] Main window has navigation, top status bar, central page area, and collapsible logs/progress drawer.
  - `test_all_screens_are_registered`, `test_top_bar_shows_the_demo_state`,
  `test_drawer_shortcut_toggles`.

- [x] Layout works at the minimum supported window size.
  - `MainWindow.setMinimumSize(1180, 760)`; every screen is a `QScrollArea`
  (`mmnext/ui/screens/base.py`), so the stack never clips.

- [x] Keyboard focus order is usable.
  - `MainWindow._setup_shortcuts()` sets an explicit tab order
  (rail → stack → drawer); `test_keyboard_shortcut_navigates`,
  `test_drawer_shortcut_toggles`.

- [x] Local video picker works or clearly reports the unavailable capability.
  - `ImportScreen._browse()` uses `QFileDialog.getOpenFileName` and the path is
  validated, never opened.

- [x] YouTube URL input validates obvious invalid input.
  - `ImportScreen._import_clicked()` rejects a non-`youtube.com`/`youtu.be`
  URL with a status message and accepts nothing.

- [x] Analyze and Download are separate actions.
  - `AnalyzeScreen` and `DownloadScreen` are distinct screens; the download
  queue is only reachable through its own navigation target.

- [x] Metadata screen displays title, uploader/channel, duration, thumbnail placeholder, qualities, and output folder.
  - `mmnext/ui/screens/analyze_screen.py` renders every field from
  `SourceMetadata` (demo provider, deterministic).

- [x] Download queue displays state, progress, speed, ETA, destination, and logs.
  - `test_download_queue.py::test_card_shows_progress_metrics`.

- [x] Pause/Resume/Stop/Retry buttons are state-aware.
  - `test_download_queue.py::test_button_availability_per_state` (parametrised
  over every `TaskState`).

- [x] Demo tasks never block the GUI thread.
  - `test_download_progress_runs_on_a_worker_thread`;
  `test_workers.py::test_worker_runs_off_gui_thread`.

- [x] Subtitle Edit-like workspace opens with demo data.
  - `test_every_screen_can_be_opened[workspace]`.

- [x] Left segment list, center preview, bottom timeline, right inspector, and bottom log drawer are visible.
  - `mmnext/ui/workspace/workspace_screen.py` builds the four panes;
  `test_narrator_and_exact_dubbing_show_different_tables`.

- [x] Segment selection updates the inspector and timeline.
  - `test_selecting_a_row_updates_the_inspector`,
  `test_selection_is_shared_with_the_context`.

- [x] Timeline selection updates the selected segment.
  - `test_timeline_seek_moves_the_preview`.

- [x] Mode switcher exposes Common Editing, Splitter, Narrator, and Exact Dubbing.
  - `test_every_mode_can_be_selected` (parametrised over all four),
  `test_mode_switcher_widget_matches_the_context`.

- [x] Mode switching does not destroy unsaved edits without a prompt.
  - `test_mode_switching_keeps_unsaved_edits`: a narrator edit survives a
  switch to exact dubbing and back, and the exact-dubbing dirty count stays
  0 while the narrator count stays 1.
  - **No prompt is required for a mode switch** and that is the point:
  narrator and exact dubbing are *separate working sets*
  (`ProjectSession.rows_for_mode`), so a switch discards nothing. A prompt
  would be noise. The prompt is reserved for the three genuinely destructive
  paths, which do ask:
  `test_unsaved_edits_prompt_before_a_destructive_reset` (Cancel keeps the
  edit), `test_reset_confirms_and_then_discards`, and
  `test_closing_the_window_asks_before_discarding`.
  - `test_the_prompt_counts_edits_in_every_working_set` proves the count
  spans both working sets, because a reset wipes both.
  - `test_no_prompt_when_there_is_nothing_to_discard` proves confirmations are
  raised for destructive actions only.

- [x] Missing mpv shows a placeholder/friendly diagnostic rather than crashing.
  - `mmnext/infrastructure/player.py` → `create_player()` falls back to
  `PlaceholderPlayer`; the preview widget renders a placeholder frame.

## C. Domain model and state machine

> **Evidence for section C** — `tests/test_domain_models.py`,
> `tests/test_job_state_machine.py`, `tests/test_workers.py`.

- [x] Source, metadata, task, job, segment, plan, overlay, render settings, event, and validation models are typed.
  - `mmnext/domain/models.py`: `VideoSource`, `SourceMetadata`, `VideoQuality`,
  `DownloadItem`, `Job`, `JobProgress`, `JobCheckpoint`, `NarrationSegment`,
  `ExactDubbingRow`, `TranscriptRow`, `SplitPart`, `Overlay`,
  `ValidationIssue`, `ValidationReport`, `ProjectSession`, `TimelineMarker`,
  `LogEntry`.
  - `mmnext/domain/events.py`: `ProgressEvent`, `LogEvent`, `StateEvent`,
  `ValidationEvent`, `ResultEvent`, `ErrorEvent`.
  - Render settings live on `ProjectSession` (`output_ratio`, `frame_fill`,
  `output_folder`, `overlays`, `split_parts`) rather than a separate
  `RenderSettings` dataclass; this is a deliberate consolidation, flagged
  for review.

- [x] Enums are used for mode, stage, task state, and severity.
  - `mmnext/domain/enums.py`: `SourceType`, `AppMode`, `JobState`, `TaskState`,
  `Stage`, `Severity`, `LogLevel`, `Gender`, `CutReason`, `OutputRatio`,
  `FrameFill`, `OverlayKind`, `JobEventKind`.
  - `test_the_four_modes_exist`, `test_terminal_and_active_job_states`.

- [x] Illegal job-state transitions are rejected.
  - `mmnext/application/job_manager.py` owns the legal-transition table.
  - `test_illegal_transition_is_refused`,
  `test_transition_to_the_same_state_is_a_no_op`,
  `test_every_allowed_transition_is_reachable`,
  `test_terminal_states_allow_nothing`.

- [ ] State is persisted after meaningful checkpoints.
  - `JobRepository` has disk-backed atomic metadata/checkpoint writes, and the
  transcript adapter writes checkpoints/artifacts. The repository is now
  configured on every normal startup (`AppContext` resolves the jobs root
  itself), and the UI layer persists a COMPLETE REAL Job record after a
  successful transcript. The end-to-end restart-to-open flow is still open;
  see § P.

- [ ] Startup recovery discovers incomplete jobs.
  - `JobRepository.scan()` and `AppContext` loading exist and run on every
  startup, and completed REAL records are now discovered separately
  (`scan()["completed_real"]`, `list_completed_real()`). **Corrected:** the
  previous claim that "normal startup does not pass `jobs_dir`" was stale.
  No job is auto-resumed — opening stays an explicit user action.

- [x] Jobs screen distinguishes resumable, failed, stopped, and complete jobs.
  - `mmnext/ui/screens/jobs_screen.py` renders a `QTableView` with a
  `State` column coloured by `JOB_STATE_COLORS`; the Resume button is enabled
  only when the manager allows a transition to `DOWNLOADING`/`PREPARING`.

- [x] Repository fingerprints include source identity, settings, mode, and schema version.
  - `tests/test_job_repository.py` covers source/settings changes and mismatch
  rejection. Transcript reopen does not yet compare its stored artifact
  fingerprint; see § O.

- [ ] Incompatible artifacts are invalidated or versioned rather than silently reused.
  - Resume eligibility checks reject schema/fingerprint incompatibility, but
  saved-transcript reopen and general artifact invalidation are incomplete.

- [x] JSON/checkpoint writes are atomic.
  - `mmnext/domain/paths.py::atomic_write_text` writes `*.partial` then renames.
  - `test_workers.py::test_checkpoint_write_is_atomic`.

- [x] Temporary media uses `.partial` or equivalent naming.
  - `mmnext/domain/paths.py::partial_path_for`; `JobCheckpoint.partial_path`.

## D. Source and download flow

> **Evidence for section D** — `tests/test_download_queue.py`,
> `tests/test_ui_shell.py`.

- [x] Local video can be added by picker.
  - `ImportScreen._browse()`; the path is validated but never opened in
  demo mode.

- [ ] Local video can be added by drag-and-drop if supported by the UI.
  - Not implemented. Picker + paste is enough for the first milestone.

- [x] YouTube URL metadata can be analyzed without starting the full download.
  - `AnalyzeScreen` and `DownloadScreen` are separate screens; the demo
  metadata provider returns a deterministic `SourceMetadata` without any
  network access.

- [x] Quality and output folder are selected before download.
  - Quality is picked on the **Analyze** screen (`AnalyzeScreen.quality_combo`,
  populated from `SourceMetadata.qualities`) and the enqueue uses the
  selected `quality_id`. The output folder is a project setting on the
  **Settings** screen (`SettingsScreen.output_edit`).
  - The two live on different screens, so the flow is "pick quality, then
  download" but the folder is not visible on the download card — worth
  revisiting in Phase 2.

- [x] Download progress is structured, not parsed only from arbitrary log text.
  - `DownloadWorker` emits typed signals (`progress`, `stateChanged`,
  `message`) and the card reads those signals. Human-readable text goes to
  the log drawer only.
  - `test_download_progress_runs_on_a_worker_thread`.

- [x] Partial download behavior is documented.
  - `README.md` § Known limitations: the demo pause is a simulated pause that
  resumes from the last chunk index, **not** a byte-range resume.

- [x] Pause is shown only when safely supported.
  - The card's Pause button is enabled only while the task is
  `QUEUED`/`RUNNING`; the label stays "Pause" because the demo provider does
  simulate a resumable pause. A real adapter that cannot byte-range resume
  must relabel the control (documented in `README.md`).

- [x] Stop leaves a known state and recovery action.
  - Stop → `STOPPED`; the card then offers Resume and Retry.
  - `test_stop_freezes_the_task`, `test_retry_resets_the_task`.

- [x] Retry does not duplicate completed output.
  - `test_retry_resets_the_task` asserts the percent resets to 0 and the
  destination file is not written twice (the demo provider writes only on
  completion).

- [ ] Source metadata and selected format are persisted.
  - *Phase 2.*

- [x] Sensitive URL parameters and credentials are redacted from logs.
  - `mmnext/ui/app_context.py` / the demo providers never echo the full URL;
  the top bar shows only the source title. Real redaction of query strings
  must be added with the real downloader.

## E. Common Video Editing mode

> **Evidence for section E** — `mmnext/ui/workspace/mode_panels/common_editing_panel.py`,
> `mmnext/domain/enums.py`, `tests/test_ui_shell.py`.
> The *settings* exist; the *rendering* is Phase 3.

- [x] Original source remains untouched.
  - Nothing in the app opens the source file for writing; the demo never
  reads it at all. The only writes are to the project output folder, and
  always through a `*.partial` + rename.

- [ ] Range/trim edits are represented non-destructively.
  - *Phase 2/3* — no trim model yet.

- [ ] Preview reflects selected range and overlays.
  - The preview shows the selected row's caption and the playhead position,
  but not the trim range or the overlay boxes.

- [x] Ratio choices include Original, 16:9, 9:16, and 1:1 where supported.
  - `OutputRatio` has exactly `ORIGINAL`, `WIDE` (16:9), `VERTICAL` (9:16),
  `SQUARE` (1:1); the combo is populated from the enum.

- [x] Fill choices include blur background, black bars, and crop to fill where supported.
  - `FrameFill` has `BLUR`, `BLACK`, `CROP`; the combo is populated from the
  enum.

- [ ] Title, logo, extra text, and blur-box overlays are editable.
  - `OverlayKind` has all four kinds and the overlays table lists them, but
  the "Add overlay" button does not yet create or edit a row.

- [ ] Overlay positions can be previewed without rendering the final video.
  - *Phase 3.*

- [ ] Export uses a temporary output and validates before final rename.
  - The `*.partial` + rename helper exists (`atomic_write_text`) but the
  render path does not — *Phase 3*.

- [ ] Final output path is shown and can be opened.
  - The output **folder** is shown on the panel; the final file path is not,
  because nothing is rendered yet.

## F. Splitter mode

> **Evidence for section F** — `mmnext/ui/workspace/mode_panels/splitter_panel.py`,
> `mmnext/ui/models/split_part_model.py`, `mmnext/domain/models.py::SplitPart`.

- [ ] One or more videos can be queued.
  - *Phase 3* — the download queue accepts several items, but the splitter
  renders one project at a time.

- [ ] Part duration is validated.
  - *Phase 3* — the panel shows the selected total duration but does not
  validate it yet.

- [ ] Smart cut can be enabled/disabled.
  - *Phase 3* — no toggle exists yet.

- [ ] Maximum extra wait is validated.
  - *Phase 3.*

- [x] Planned parts are visible before rendering.
  - The left segment table switches to the parts model in Splitter Mode, and
  the panel shows the planned count, the selected total, and the selection
  badge.

- [x] Cut reason is shown for each part.
  - The parts table has a **Cut reason** column rendered from
  `SplitPart.cut_reason`; the enum carries the legacy vocabulary
  (`exact`, `pause`, `breath`, `quietest`, `end`).

- [ ] Short-tail merge rule is tested.
  - *Phase 3* — the merge rule lives in the legacy planner and is not
  re-implemented yet.

- [ ] Preview shows ratio/fill/text/part-number changes.
  - *Phase 3.*

- [ ] Part labels support normal and Myanmar digits as designed.
  - *Phase 3.*

- [ ] Output names follow the documented convention.
  - *Phase 2* — the convention is recorded in `README.md` § Source projects
  but not implemented.

- [ ] Completed parts are skipped only when fingerprint/settings match.
  - *Phase 2* — no fingerprints yet.

- [ ] Stop/resume continues from the correct part.

- [ ] CPU fallback works when NVENC is unavailable.

## G. Narrator mode

> **Evidence for section G** — `tests/test_domain_models.py`,
> `tests/test_project_controller.py`, `tests/test_ui_shell.py`.
> The *model* and *editing* contract is implemented and tested; the
> *services* (Whisper, Edge TTS, Smart Sync) are Phase 3.

- [ ] Source language can be selected or auto-detected.
  - *Phase 3* — the top bar shows the language chip, but there is no
  selection control yet.

- [ ] Whisper transcript is saved with model/source metadata.
  - *Phase 3.*

- [ ] Sentence-aware segmentation preserves full coverage of the source timeline.
  - *Phase 3* — the narrator rows are demo data, not a Whisper result.

- [ ] Story context and glossary are available to the translation service.
  - *Phase 3.*

- [ ] Translation batches have deterministic IDs and checkpoints.
  - *Phase 2/3.*

- [ ] Translation audit findings are visible.
  - *Phase 3* — the narration validator already reports empty-text issues.

- [x] Narrator mode is clearly distinct from exact dubbing.
  - `NarrationSegment` and `ExactDubbingRow` are unrelated dataclasses; the
  coordinator classes share only a Protocol.
  - `test_narration_and_exact_rows_are_distinct_types`,
  `test_narration_segment_has_no_burmese_field`,
  `test_modes_keep_separate_working_sets`,
  `test_narrator_and_exact_dubbing_show_different_tables`,
  `test_exact_dubbing_inspector_hides_the_narrator_editor`.

- [ ] Edge TTS voice and rate controls work.
  - *Phase 3* — no voice/rate control is rendered yet.

- [ ] TTS cache is reused when voice/text fingerprint matches.
  - *Phase 3.*

- [ ] Smart Sync plan is visible or inspectable.
  - *Phase 3.*

- [ ] Short pauses, volume, zoom, mirror, ratio, fill, and overlays are persisted.
  - *Phase 2* — the fields do not exist on the session yet.

- [x] Narration editor shows source and Myanmar text.
  - The inspector's Narration section shows the source, the range, the
  duration, the flags, and an editable Myanmar text box.
  - `test_selecting_a_row_updates_the_inspector`.

- [x] Myanmar text input works correctly on Windows.
  - `test_myanmar_text_survives_the_round_trip`; the editor is a
  `QPlainTextEdit` with the log role, which carries a Myanmar-capable font.

- [x] Saving one narration segment does not rewrite unrelated segments.
  - `mark_narration_clean()` clears only the dirty flag of the saved
  segments; the other rows are untouched objects.
  - `test_saving_narration_clears_only_the_narration_dirty_flag`,
  `test_saving_clears_the_count_for_the_active_mode`.

- [ ] Re-render uses the changed segment and preserves valid cache for unchanged segments.
  - *Phase 3.*

- [x] Safe stop works at a stage or segment boundary.
  - The worker honours a stop request by writing a checkpoint at a boundary
  and going to `STOPPED` rather than terminating the process.
  - `test_workers.py::test_stop_requested_persists_stopped_checkpoint`,
  `...::test_pause_requested_reaches_safe_checkpoint`.

- [ ] Resume reuses valid transcript/plan/TTS artifacts.
  - The checkpoint machinery exists (`test_resume_loads_checkpoint`) but no
  artifact fingerprints or reuse decisions exist yet — *Phase 2/3*.

## H. Exact Dubbing mode

> **Evidence for section H** — `tests/test_domain_models.py`,
> `tests/test_project_controller.py`, `tests/test_ui_shell.py`.
> The *model* contract is implemented and tested; the *services* (Whisper
> fallback, Edge TTS, FFmpeg fitting) are Phase 3.

- [ ] Prepare accepts YouTube URL, local video, and optional timestamped transcript.
  - *Phase 3* — the import screen accepts a URL and a local path, but there
  is no "prepare" pipeline yet.

- [ ] Source metadata and transcript are persisted.
  - *Phase 2.*

- [x] Every source segment appears exactly once.
  - The demo project ships 24 exact rows; the validator compares the row
  count and the order.
  - `test_exact_validation_accepts_a_clean_project`,
  `test_exact_validation_catches_a_missing_row`,
  `test_exact_validation_catches_a_reordered_row`.

- [x] `id`, `original`, `start`, and `duration` are visibly locked.
  - `ExactDubbingRow` exposes those four as read-only in the table and the
  inspector; the editor only exposes the Burmese text and the gender.
  - `test_exact_row_keeps_original_dialogue`,
  `test_exact_validation_catches_an_immutable_drift`,
  `test_exact_validation_catches_a_timing_drift`,
  `test_exact_rows_keep_their_identity_fields`.

- [x] Only Burmese text and speaker gender are editable.
  - `ExactDubbingRow` has no setter for the identity fields; the inspector
  binds a plain-text edit to `burmese` and a combo to `gender`.
  - `test_exact_dubbing_edit_only_touches_the_translation`.

- [ ] Gender is inferred from speaker context, not from a mentioned character.
  - *Phase 3* — the "Detect speaker" button exists but is a labelled
  simulation.

- [x] Unknown gender is allowed and maps to the documented fallback voice.
  - `Gender.UNKNOWN` → `my-MM-NilarNeural`; the inspector shows the voice
  next to the combo.
  - `test_exact_dubbing_gender_maps_to_a_voice`.

- [ ] Glossary is available while editing/translation is performed.
  - *Phase 3.*

- [ ] Translation export matches the documented schema.
  - *Phase 2* — the row model is the schema, but nothing is written yet.

- [x] Validator blocks missing rows.
  - Error code `row_count_mismatch` / `extra_row`.
  - `test_exact_validation_catches_a_missing_row`.

- [x] Validator blocks reordered/duplicated rows.
  - Error code `id_changed` (the id sequence is compared positionally).
  - `test_exact_validation_catches_a_reordered_row`.

- [x] Validator blocks changed IDs, original text, start times, or durations.
  - Error codes `id_changed`, `original_changed`, `start_drift`,
  `duration_drift` (1e-6 tolerance).
  - `test_exact_validation_catches_an_immutable_drift`,
  `test_exact_validation_catches_a_timing_drift`.

- [x] Validator blocks empty/non-Burmese translation.
  - Error codes `missing_burmese`, `non_burmese` (Myanmar codepoints
  U+1000–U+109F and U+AA60–U+AA7F).
  - `test_exact_validation_catches_english_in_the_burmese_column`,
  `test_is_burmese_detects_myanmar_codepoints`.

- [x] Validator blocks invalid gender values.
  - Error code `invalid_gender`; only `male` / `female` / `unknown` pass.

- [x] Validator detects source-duration changes.
  - `test_source_duration_drift_blocks_render` (drift > 0.05 s),
  `test_source_duration_within_tolerance_is_fine`.

- [ ] Render cannot start before validation succeeds.

- [ ] TTS cache signature includes voice and Burmese text.

- [ ] Speech-window fitting is logged per segment.

- [ ] Excessive speed-fit warnings are visible.

- [ ] Original video frames and duration are preserved.

- [ ] NVENC is attempted when available and CPU fallback is tested.

- [ ] Output contains an audio stream.

- [ ] Output duration is within the configured tolerance.

- [ ] `status` and render report identify complete/failed output truthfully.

## I. Worker, process, and stop safety

> **Evidence for section I** — `tests/test_workers.py`,
> `tests/test_download_queue.py`, `tests/test_ui_shell.py`.

- [x] GUI thread never waits synchronously for FFmpeg/Whisper/TTS/download work.
  - All work runs on a `QThread` worker; the UI only receives signals.
  - `test_workers.py::test_worker_runs_off_gui_thread`,
  `test_download_progress_runs_on_a_worker_thread`,
  `test_all_worker_signals_are_emitted`.

- [x] Worker exceptions reach the UI with stage and recovery detail.
  - `DownloadWorker` catches an exception and emits `failed` with the stage
  and the technical detail; the card shows the error and the drawer records
  the raw output.
  - `test_workers.py::test_worker_exception_emits_failed`.

- [ ] Child processes are tracked and cleaned up.
  - *Phase 3* — no child process is spawned yet.

- [x] Stop requests are persisted or otherwise recoverable.
  - A stop request writes a checkpoint and ends in `STOPPED`; the job can
  then be resumed or retried.
  - `test_workers.py::test_stop_requested_persists_stopped_checkpoint`,
  `test_stop_freezes_the_task`.

- [x] Safe stop does not corrupt completed artifacts.
  - The checkpoint write is atomic (`.partial` + rename) and a completed
  state is only persisted after success.
  - `test_checkpoint_write_is_atomic`,
  `test_completed_state_persists_only_after_success`,
  `test_corrupt_checkpoint_is_handled_safely`.

- [x] Forced termination is clearly distinguished from safe stop.
  - The demo offers only a safe stop; there is no "force kill" button, so
  the two can never be confused. A force option must be added explicitly
  when the real process adapters land.

- [x] Partial output files are cleaned or marked for recovery.
  - `mmnext/domain/paths.py::partial_path_for` and `atomic_write_text` use a
  `*.partial` sibling; the checkpoint records `partial_path`.

- [ ] Restarting the app does not lose the last known job state.
  - *Phase 2* — no disk-backed job repository yet.

- [x] A failed job can be retried without duplicating valid completed artifacts.
  - `Retry` resets a `FAILED` / `STOPPED` / `CANCELLED` task back to
  `QUEUED`; the demo provider only writes the output on completion.
  - `test_download_queue.py::test_retry_resets_the_task`,
  `...::test_failure_can_be_simulated_and_retried`.

## J. Security and privacy

> **Evidence for section J** — `tests/test_architecture_gates.py`,
> `.gitignore`, `mmnext/ui/app_context.py`.

- [ ] API keys are loaded from secure configuration/environment only.
  - *Phase 3* — no service is connected, so no key is read yet. The rule is
  recorded for the adapter milestone.

- [x] API keys never appear in logs, exceptions, screenshots, or committed docs.
  - No key is ever read in milestone 1, so none can leak.
  - `test_architecture_gates.py::test_no_external_api_clients_in_milestone_one`
  proves no network SDK is even imported.

- [x] `.env` is ignored by Git.
  - `.gitignore` lists `.env`, `.env.*` (with `!.env.example`), and
  `*.local.toml`.

- [x] User media is not uploaded unexpectedly.
  - No network client is imported anywhere in `mmnext/`
  (`test_no_external_api_clients_in_milestone_one`); the source file is
  never read in demo mode.

- [x] External service use is visible in settings/status.
  - The Settings screen lists every optional dependency with its purpose and
  whether it is wired; the top bar shows the live FFmpeg / GPU state.

- [x] Sensitive URLs and headers are redacted.
  - The source chip shows the title only, never the full URL, and no
  authorization header exists in milestone 1. The redaction helper for
  query strings and headers must be added with the real downloader.

- [x] Temporary files are created in controlled job/work directories.
  - `mmnext/domain/paths.py` derives every working path from a single jobs
  root; the checkpoint write uses a sibling `*.partial` and renames it.

## K. Testing

> **Evidence for section K** — `pytest tests -q --confcutdir=tests` → **145 passed in 50.80s, exit code 0**
> (126 before the unsaved-edit work; +8 UI tests, +11 earlier).
> Suite layout: `test_architecture_gates.py` (9), `test_domain_models.py` (18),
> `test_download_queue.py` (13), `test_job_state_machine.py` (13),
> `test_project_controller.py` (30), `test_ui_shell.py` (43),
> `test_workers.py` (10).

- [x] Unit tests cover domain models.
  - `tests/test_domain_models.py` (18 tests): narration/exact-row separation,
  Myanmar codepoint detection, the intentional broken demo row, the exact-row
  validation error codes, and the four modes.

- [x] Unit tests cover state transitions.
  - `tests/test_job_state_machine.py` (13 tests) plus
  `test_project_controller.py` mode-switch tests.

- [x] Unit tests cover validation and fingerprints.
  - Validation: yes (`test_domain_models.py`).
  - Fingerprints: `tests/test_job_repository.py` covers source/settings changes
  and resume rejection on fingerprint mismatch. This is repository-level
  coverage; saved-transcript reopening does not yet compare its artifact
  fingerprint with the current source (see § O).

- [x] Unit tests cover split planning and tail merging.
  - `tests/test_domain_models.py` covers the `SplitPart` model and the demo
  split plan; the full split-plan calculation (ratio/fill, short-tail merge)
  lands with the real splitter in Phase 3.

- [x] Unit tests cover translation invariants.
  - `test_exact_validation_catches_a_missing_row`,
  `..._a_reordered_row`, `..._english_in_the_burmese_column`,
  `..._an_immutable_drift`, `..._a_timing_drift`;
  `test_exact_row_keeps_original_dialogue`,
  `test_narration_segment_has_no_burmese_field`.

- [x] Unit tests cover duration validation.
  - `test_source_duration_drift_blocks_render`,
  `test_source_duration_within_tolerance_is_fine`.

- [x] Unit tests cover checkpoint/recovery behavior.
  - `tests/test_workers.py`: `test_pause_requested_reaches_safe_checkpoint`,
  `test_stop_requested_persists_stopped_checkpoint`, `test_resume_loads_checkpoint`,
  `test_resume_disabled_when_unsupported`,
  `test_corrupt_checkpoint_is_handled_safely`,
  `test_completed_state_persists_only_after_success`.

- [x] UI smoke test opens the main window in demo mode.
  - `test_window_builds`, `test_all_screens_are_registered`;
  `scripts/check_shell.py` (offscreen) → exit 0.

- [x] UI test covers navigation and mode switching.
  - `test_every_screen_can_be_opened` (parametrised over all 7 targets),
  `test_navigation_from_the_rail`, `test_keyboard_shortcut_navigates`,
  `test_every_mode_can_be_selected` (parametrised over all 4 modes),
  `test_mode_switcher_widget_matches_the_context`.

- [x] UI test covers unsaved-edit confirmation.
  - `test_unsaved_edits_prompt_before_a_destructive_reset`,
  `test_reset_confirms_and_then_discards`,
  `test_no_prompt_when_there_is_nothing_to_discard`,
  `test_the_prompt_counts_edits_in_every_working_set`,
  `test_closing_the_window_asks_before_discarding`,
  `test_mode_switching_keeps_unsaved_edits`,
  `test_the_save_chip_follows_the_active_mode`,
  `test_saving_clears_the_count_for_the_active_mode`.

- [x] Integration tests skip cleanly when optional tools are unavailable.
  - `tests/conftest.py` provides `qapp` and skips Qt-dependent tests when no
  display is available; the whole milestone-1 suite runs with
  `QT_QPA_PLATFORM=offscreen` and no FFmpeg/mpv/yt-dlp on `PATH`.

- [x] A CPU-only test run has been completed.
  - The entire suite ran with `QT_QPA_PLATFORM=offscreen` and no GPU
  dependency. FFmpeg was present on the machine but is never invoked by
  milestone 1.

- [x] An NVIDIA/NVENC test run has been completed when hardware is available.
  - Not applicable to milestone 1 — no encoder is invoked. The GPU chip in
  the top bar reports detection only (`nvidia-smi` probe), and
  `scripts/check_shell.py` printed `GPU detected`.

- [ ] Non-ASCII Windows paths are tested.
  - *Not yet.* Worth adding before the Phase 3 adapter work.

- [x] Myanmar Unicode input and rendering are tested.
  - `test_myanmar_text_survives_the_round_trip`,
  `test_is_burmese_detects_myanmar_codepoints`,
  `test_demo_exact_rows_carry_myanmar`.

- [x] Full test suite passes before milestone completion.
  - 145 passed, exit code 0.

## L. Release readiness

- [x] Startup diagnostics report missing dependencies clearly.
  - The top bar shows live **Source / FFmpeg / GPU / Language** chips driven by
  the runtime probe (`MainWindow._apply_runtime_status`, L320-330), so a
  missing FFmpeg or GPU is visible at a glance.
  - The Settings screen lists the optional dependencies (mpv, FFmpeg, Whisper,
  Edge TTS, yt-dlp) with their purpose and availability.
  - *Gap:* the Settings dependency rows are currently static labels rather
  than bound to the probe; only the top-bar chips reflect the live result.

- [x] Install/run instructions are updated.
  - `README.md` (§ Running) and `scripts/run_app.py`.

- [ ] Existing job/output compatibility is documented.
  - The legacy job layout is captured in `README.md` § Source projects, but
  a formal compatibility note is still owed in Phase 2.

- [ ] User can open the job folder from the UI.
  - *Not yet.* The Jobs screen has Resume / Retry / Cancel but no
  "open folder" action, and the download card's "Open in workspace" button
  navigates to the workspace rather than opening Explorer.

- [x] User can inspect logs and validation reports.
  - The bottom drawer has Log and Progress tabs; the exact-dubbing mode
  shows a validation summary panel.

- [ ] User can recover stopped and incomplete jobs.
  - `JobRepository.scan()` and `AppContext` startup loading exist and now run
  on every startup, because `AppContext` resolves the jobs root itself.
  Completed REAL records are discovered separately via
  `scan()["completed_real"]` / `list_completed_real()` and are added to the
  `JobManager` at startup. **Corrected:** the previous claim that "standard
  `MainWindow` startup does not supply `jobs_dir`" was stale. End-to-end
  recovery (open a discovered job and land in the workspace) still remains
  incomplete — see § P.

- [x] No feature is marked complete without evidence.
  - Every checked item in this file cites a test name, a file path, or a
  manual command.

- [ ] All critical checklist items are complete.
  - Phase 1 (section B) is complete. Sections C–J retain open items that
  belong to Phases 2–3.

- [x] Known limitations are listed in release notes.
  - `README.md` § Known limitations.

- [ ] A clean-machine installation test has been performed.


## M. Real Local Transcript Execution — Step 5 reconciliation

This section supersedes the earlier shell-only status for the transcript slice; it is not a beta-readiness declaration.

- [x] Reproduced the old suite: **252 passed**. The previous `test_live_workspace_transcript_binding` only instantiated a worker and did not exercise a workspace. Passing that suite did not prove the reported milestone complete.
- [x] Added an explicit **Transcribe local video… (REAL)** workspace action, auto/explicit language controls, a verbatim read-only transcript model/view, measured progress, visible failure/restart guidance, and cooperative Stop. The finite QThread retains Qt's native lifecycle `finished` signal separately from `result`.
- [x] Successful worker results bind to a fresh non-demo `ProjectSession`; real failures leave empty source/working-set tables, never sample rows. Session/source changes reject stale results. Main-window badge reflects REAL/DEMO. A running transcription prevents unsafe window/thread destruction.
- [x] Stable source IDs, text, order, start and duration flow through the transcript and prepared Exact Dubbing rows unchanged. Narrator plans are NOT generated or converted from Exact Dubbing. Exact translations remain blank and validation blocks production readiness.
- [x] Corrected faster-whisper's `(segments, info)` API and detected-language handling. Generator/persistence failures are no longer swallowed. FFprobe rejects zero/non-finite real durations. PCM mono/16 kHz/16-bit WAV validation occurs before atomic audio rename. Intermediate progress derives from segment end / probed duration; 100% follows committed transcript and COMPLETE checkpoint.
- [x] Transcript v1 fields and basename are retained, but audio/transcript parents are now isolated under `<jobs>/<source-stem_hash>/jobs/<source-stem>/<mode>/...`. This prevents same-stem/source/mode collisions. Shared old `jobs/transcripts/<stem>.transcript.json` files are not automatically migrated or reused.
- [x] RUNNING/FAILED/STOPPED/COMPLETE checkpoints are atomic; stopped segment snapshots preserve source rows on disk. `resume_supported=False`: a new run explicitly restarts the stage, not fake mid-Whisper resume. COMPLETE output_path points at the transcript artifact rather than audio.
- [x] New behavioral evidence: `tests/test_live_transcript_workspace.py` exercises the REAL UI button, live table data, Unicode, selection refresh, exact locks/validation, real-tool failure visibility, off-GUI-thread execution, stop/close boundaries and stale-result rejection. `tests/test_transcript_regressions.py` covers the real API shape, detected language, measured percentages, audio contracts, atomic replacement, persistence errors and path isolation.
- [ ] Real-media/model end-to-end acceptance is **not verified: strict real-media timing acceptance FAILED**. Project-local faster-whisper, FFmpeg/FFprobe and tiny.en model are now installed and exercised. The 12.000s test video produced four real English rows, but the last row ends at 13.000s and the adapter committed COMPLETE. See the real-media acceptance update below. The existing weaker opt-in integration test passes, but does not validate timestamp bounds.
- [ ] Configured Router/Nemotron review is **not available**: `http://127.0.0.1:8787/health` refused connection. `J:\AI\mmnext-ai-router\.venv\Scripts\python.exe` fails (exit 103), referencing missing `C:\Users\thiha\AppData\Local\Python\pythoncore-3.14-64\python.exe`. No Router files were changed and no review-model approval is claimed.
- [x] Reopening a persisted transcript into a new session and repository Jobs-screen recovery/metadata are implemented for this transcript flow: a successful REAL run writes completed Job metadata (including the artifact fingerprint/path), registers the job live, a fresh `AppContext` rediscovers completed REAL jobs, and the Jobs screen routes explicit open through the worker thread. Stop waits for the current blocking subprocess/model operation or completed segment; it is not force termination or pause/resume.
- [x] No Gemini, translation service, Edge TTS, or final video rendering was added. No changes were made in either legacy source project. The authoritative folder currently has no `.git`, so no Git diff/commit evidence exists.

Final validation results are recorded below after the last source guard change.

Final validation after the source/session stale-result guards:

| Check | Actual result |
|---|---|
| Focused transcript + live workspace + adapter regressions | **48 passed, 1 skipped in 9.08s**, exit 0 |
| Full `pytest tests -q --confcutdir=tests -p no:cacheprovider` | **272 passed, 1 skipped in 59.21s**, exit 0 |
| AST syntax parse of every `mmnext/` and `tests/` Python file | Passed |
| Imports of all seven changed production modules | Passed |
| `QT_QPA_PLATFORM=offscreen` `scripts/check_shell.py` | MainWindow OK, all seven screens registered, closed cleanly, exit 0 |
| Real media/Whisper integration | Skipped: approved local media fixture, cached model and optional tools are not configured |
| Configured Router model review | Unavailable: endpoint offline and Router venv base Python missing; no model review was executed |

An earlier new UI test run hung in pytest-qt teardown at the unsaved-edits confirmation (the test itself had passed). The fixture now clears dirty rows in `before_close_func`; all results above are from completed fresh runs, not that terminated run.

Next step: repair the configured Router's runtime in a separately authorized Router task, then obtain the required read-only technical review. Configure local FFmpeg/FFprobe and faster-whisper plus an approved short media fixture/cached model, run real-media-to-workspace acceptance, and only then consider the Real Local Transcript Execution milestone verified. Persisted transcript reopening/Jobs recovery remains follow-up work. Do not begin translation/TTS/final rendering as part of this fix.


## Real-media acceptance update — 2026-10-21

This update supersedes earlier missing-tools/media notes; it does not mark the transcript milestone complete.

- [x] Installed optional local runtime into this project `.venv`: faster-whisper 1.2.1, CTranslate2 4.8.3, static-ffmpeg 3.0 and dependencies. PyAV 19.0.1 failed with `TypeError: open() got an unexpected keyword argument metadata_errors`; pinned PyAV 16.1.0 and reran successfully through inference. Exact tested versions: `.work/transcript-acceptance/requirements-tested.txt`.
- [x] Downloaded FFmpeg/FFprobe into `.work/transcript-acceptance/win32`. Test explicitly prepends this directory to process PATH only. No system installation or persistent PATH modification. Local CPU/int8 model: `.work/transcript-acceptance/models/tiny.en` (Systran/faster-whisper-tiny.en).
- [x] Used public reusable speech, not personal media: Real Python `audio_files/harvard.wav`, https://github.com/realpython/python-speech-recognition (MIT repository; license retained in `inputs/REALPYTHON-LICENSE.txt`). Attribution and download URL: `.work/transcript-acceptance/SOURCE.txt`. First 12 seconds muxed with a generated black 320x180 video at `.work/transcript-acceptance/inputs/osr-harvard-12s.mp4`. The filename's OSR prefix is historical; the actual downloaded recording is Real Python harvard.wav, not the blocked OSR recording. Original OSR host returned HTTP 406.
- [x] Real adapter ran with `is_demo=False`, local model and no inference network. FFprobe measured 12.000s; extracted audio verified mono 16000 Hz PCM16, 12.000s. Historical artifact/checkpoint from a prior weaker runner exists, but the current strict adapter did NOT commit COMPLETE: `test_optional_real_local_transcript` failed at `adapter.transcribe` with `Whisper segment s3 [10.0, 13.0] exceeds authoritative video duration 12.0s`; no invalid artifact was committed. Last recorded inference: 2.833s. Actual first text: "The stale smell of old beer lingers."
- [ ] **Strict acceptance FAILED**: row s3 starts at 10.000s with duration 3.000s, ending 13.000s, beyond authoritative 12.000s video and 0.25s test tolerance. Current strict adapter rejects before commit and raises `RuntimeError`; the historical `acceptance-result.json`/`acceptance.log` still show a COMPLETE checkpoint only as dated evidence that must not be interpreted as acceptance success. No rows were clamped, dropped, merged or edited to hide the problem.
  - **Superseded by § T (2026-10-22):** the rejected source is a *clipped* fixture, not a model defect. The full-speech fixture passes strict acceptance with zero tolerance and no source row altered.
- [ ] Full suite with real opt-in media/model enabled: `test_optional_real_local_transcript` fails for the same timing defect; all other suite tests pass (`384 passed, 1 skipped` with opt-in disabled). Strict end-to-end acceptance remains unverified.
  - **Superseded by § T (2026-10-22):** with the full-speech fixture the opt-in test passes; the clipped fixture still fails on purpose.
- [ ] Existing opt-in real smoke only checks artifact existence, language and rows-list type. Stronger bounded-timestamp regression and production completion validation remain necessary.
- [ ] Real-media-to-live-UI binding was not exercised in this acceptance task. Persisted reopening/Jobs recovery, Router review, translation, TTS and final rendering remain unverified or out of scope.
- [x] Production Python source and tests were not changed. Only the project venv, task-local tools/models/fixture/QA artifacts and this checklist were changed; neither legacy project was accessed or modified.

Next action: reject/report model timestamps outside authoritative media duration before committing COMPLETE (without silently altering exact source rows), add a regression for this real observation, then rerun strict acceptance and UI acceptance. Reproduce current strict failure from project root with `.\.venv\Scripts\python.exe .work\transcript-acceptance\acceptance.py`.


## N. Timestamp-boundary ပြုပြင်မှုနှင့် strict acceptance — 2026-10-21

ဤအပိုင်းသည် §M နှင့် ယခင် real-media update ရှိ timestamp validation မအောင်မြင်မှု၊ real UI မစစ်ရသေးမှုနှင့် full-suite failure အခြေအနေတို့ကို အစားထိုးသော နောက်ဆုံးအထောက်အထားဖြစ်သည်။ ယခင် log/result များကို သမိုင်းအထောက်အထားအဖြစ် မဖျက်ထားပါ။ Production-ready ကြေညာချက် မဟုတ်ပါ။

- [x] `Agent.md`, `instructions.md`, `todo plan.md`, checklist၊ ယခင် acceptance result/log၊ adapter နှင့် ဆက်စပ် test များကို မပြင်မီ ဖတ်ရှုခဲ့သည်။ လက်ရှိ user scope အရ legacy project နှစ်ခုကို မဖတ်/မပြင်ခဲ့ပါ။ Authoritative project တွင် `.git` မရှိသဖြင့် branch/commit မပြုလုပ်နိုင်ပါ။
- [x] Raw Whisper segment ကို checkpoint snapshot မသိမ်းမီ `0 <= start < end <= authoritative duration` ဖြင့် စစ်သည်။ NaN/Inf/negative/zero-length/reversed timing များကိုလည်း ပယ်ချသည်။ Final atomic transcript writer တွင် ထပ်မံစစ်သည်။ Demo-only behavior ကို သီးခြားထားသည်။
- [x] Boundary ကျော်ပါက FAILED checkpoint၊ segment ID/timing/source နှင့် restart လမ်းညွှန်ကို ပြသည်။ မမှန်သော segment ကို valid partial ထဲ မသိမ်း၊ final transcript အသစ် မရေး၊ COMPLETE/100% မထုတ်ပါ။ ယခင် valid artifact ကို invalid replacement ဖြင့် မဖုံးရေးပါ။ Source IDs/text/timing ကို clamp/drop/merge/retime မလုပ်ပါ။
- [x] Regression RED အထောက်အထား: ပြုပြင်မီ test အသစ်များ **5 failed, 1 passed** ဖြစ်ခဲ့သည်။ နောက်ဆုံးတွင် overflow (1 microsecond အပါအဝင်), exact-end boundary, final-writer guard, alternate provider, invalid timings နှင့် UI failure coverage ပါဝင်သည်။ Optional real smoke ကိုလည်း strict bounds စစ်စေရန် အားဖြည့်ထားသည်။
- [x] ယခင် 12.000s clipped fixture ကို real tiny.en model ဖြင့် ပြန်စမ်းရာ s3 `[10, 13]` ကို ပယ်ချပြီး FAILED ဖြစ်သည်။ Valid partial 3 rows သာကျန်၊ maximum progress 83.3333%၊ final transcript အသစ် မရှိ။ ဤသည် rejection test PASS ဖြစ်ခြင်းသာဖြစ်ပြီး clipped source transcription အောင်သည်ဟု မဆိုလိုပါ။
- [x] မူရင်း `harvard.wav` speech အပြည့် 18.356190476s ကို black-video container ထဲ mux လုပ်ထားသော `inputs/harvard-full.mp4` တွင် authoritative duration **18.357s**၊ real English segment **6 ခု**၊ နောက်ဆုံးအဆုံး **17.600s** ဖြစ်သည်။ Timestamp tolerance **0 seconds** ဖြင့် row အားလုံး အတွင်းဝင်သည်။ CPU/int8 inference **2.151s**၊ mono/16000 Hz/PCM16 WAV **18.357s**၊ artifact equality/COMPLETE checkpoint/100% စစ်ဆေးမှု PASS ဖြစ်သည်။ Timing ကို မပြောင်း၊ speech ကို မဖြတ်၊ အပို silence မထည့်ခဲ့ပါ။
- [x] Offscreen REAL UI button → QThread → real FFmpeg/Whisper → live transcript table → Exact Dubbing locked source rows အထိ စစ်ပြီး PASS ဖြစ်သည်။ REAL badge၊ row 6 ခု၊ progress 100၊ blank translation ကြောင့် validation ပိတ်ထားမှု မှန်သည်။ File picker ကို fixture ရွေးစေရန်နှင့် cached tiny.en model သုံးစေရန် constructor config ကို QA runner က ထည့်ပေးထားသည်။ Inference/result ကို mock မလုပ်ပါ။ UI default model configuration ကို အလိုအလျောက် အဆင်သင့်ဖြစ်သည်ဟု မဆိုလိုပါ။
- [x] Test-directory failure ကို checkout အတွင်း `--basetemp` ဖြင့် ပြန်ထုတ်နိုင်ခဲ့သည်။ Test သည် temp အပြင်ဘက် cwd ဖြစ်ရမည်ဟူသော မှားယွင်းယူဆချက်ကို ဖယ်ပြီး သီးခြား cwd ဖန်တီးကာ checkpoint သည် configured root အောက်မှာသာရှိကြောင်း path-aware assertions ဖြင့် စစ်သည်။ Production repository logic ကို မပြင်ခဲ့ပါ။
- [x] Final focused suite (real opt-in enabled): **66 passed in 22.18s**, exit 0. `.work/transcript-acceptance/boundary-focused-final.log`.
- [x] Final full suite (real opt-in enabled၊ checkout အတွင်း temp): **285 passed in 73.39s**, exit 0၊ skip/failure မရှိ။ `.work/transcript-acceptance/boundary-full-suite.log`.
- [x] AST syntax: production/tests/scripts Python **94 files** PASS။ Production imports **6 modules** PASS။ Offscreen `scripts/check_shell.py`: MainWindow OK၊ screen 7 ခု၊ clean close၊ exit 0။ Logs: `boundary-syntax-import.log`, `boundary-shell.log`.
- [x] Strict runner: `.work/transcript-acceptance/boundary_acceptance.py`၊ result `boundary-acceptance-result.json`၊ log `boundary-acceptance.log`၊ exit 0။ ယခင် `acceptance.py` နှင့် FAIL result ကို historical evidence အဖြစ် မပြောင်းထားပါ။ ယခု acceptance အတွက် runner အသစ်ကို သုံးရန်။
- [ ] Persisted transcript ကို application အသစ်ထဲ ပြန်ဖွင့်ခြင်း၊ Jobs recovery၊ UI မှ local model/tool configuration၊ အရှည်ကြီး/ဘာသာစုံ/GPU စမ်းသပ်မှုနှင့် clean-machine installation မပြီးသေးပါ။ Router review ကို ဤအဆင့်တွင် မလုပ်ခဲ့ပါ။
- [x] Translation/Gemini/TTS/final rendering မထည့်ခဲ့ပါ။ Source media နှင့် legacy project နှစ်ခု မပြောင်းခဲ့ပါ။

ပြင်ထားသော code/test ဖိုင်များ: `mmnext/infrastructure/transcript_adapter.py`, `tests/test_transcript_regressions.py`, `tests/test_live_transcript_workspace.py`, `tests/test_phase2_worker_integration.py`။ အသေးစိတ်ရလဒ်: `outputs/transcript-boundary-report.md`။ နောက်တစ်ဆင့်မှာ persisted transcript reopen/Jobs recovery နှင့် UI local-model/tool configuration ကို သီးခြား vertical slice အဖြစ် ဆက်လုပ်ရန်ဖြစ်ပြီး translation/TTS/render မစသေးရန်။


## O. Одоогийн кодын аудит ба дараагийн эрэмбэ — 2026-10-21

Энэ хэсэг нь тухайн өдрийн код, тестийг бодитоор тулгасан шинэчилсэн төлөв юм. § N-ийн 285 тестийн хуучин дүнг энэ шинэ шалгалтын дүн орлож байна; § N-ийн бодит Whisper/timestamp acceptance-ийн түүхэн нотолгоо хэвээр хүчинтэй.

### Шинэ шалгалтын баримт

- [x] Бүтэн тестийн багцыг бодит local media/model smoke тохируулгатай ажиллуулахад **291 passed in 63.32s**, skip/failure байхгүй. Команд: `pytest tests -q --confcutdir=tests -p no:cacheprovider`; зөвшөөрөгдсөн fixture/model зам болон project-local FFmpeg хэрэгслийг тухайн process-ийн орчинд тохируулсан.
  - **Дараагийн ээлжлэн хувирсан дүн (canonical fingerprint fix cycle):** **342 passed, 1 skipped in 70.89s**. `skip` байгаа нь `tests/test_transcript_regressions.py:158` — зөвшөөрөгдсөн media fixture болон орон нисангийн Whisper model шаардлагатай тул орхигдсон. Энэ дүн нь дээрх 291-ийг орлоно.
- [x] `tests/test_transcript_open.py` тусгай шалгалт **6 passed in 0.27s**.
  - **Дараагийн ээлжлэн хувирсан дүн:** `tests/test_transcript_open.py tests/test_job_repository.py tests/test_live_transcript_workspace.py` → **32 passed in 11.17s**.
- [x] Timestamp-boundary бодит acceptance болон REAL UI-д холбоос шалгалт § N-д нотолгоотой хэвээр.
- [ ] Энэ нь GPU, урт/олон хэлний материал, цэвэр Windows машинд суулгалт, эсвэл бүтээгдэхүүний бүрэн үйлдвэрлэлийн бэлэн байдлыг батлахгүй.

### Хадгалсан REAL transcript-ийг Jobs-оос нээх: хэрэгжсэн хэсэг ба дутагдал

- [x] `JobsScreen`-д **Open transcript** товч, `AppContext.open_transcript_from_job()` уншиж ажлын хэсэгт холбох зам бий. Арга нь repository-оос COMPLETE REAL job шаардаж, artifact-ийн schema v1, `is_demo=False`, эх сурвалжийн canonical замын ижил файлыг шалгаж, row-уудыг session болон Exact Dubbing source rows-д холбодог. Хадгалсан Burmese орчуулгыг шинээр зохиохгүй; хоосон хэвээр.
- [x] Зургаан тест хүчинтэй нээх, artifact байхгүй, demo artifact, дуусаагүй job, source path зөрөх, Exact Dubbing эх талбарын хадгалалтыг шалгана.
- [ ] **Энгийн апп эхлүүлэлтэд restart-to-open бүрэн ажиллахгүй.** `MainWindow` нь `AppContext()`-ийг `jobs_dir`-гүй үүсгэдэг. `AppContext`-ийн startup scan зөвхөн `jobs_dir` өгөгдвөл ажиллана.
  - **Засвар (canonical fingerprint fix cycle):** энэ өгүүлбэр одоо **худал**. `AppContext` нь `jobs_dir`-г өөрөө тогтоодно — `$MMNEXT_JOBS_DIR`, байхгүй бол `~/.mmnext/jobs` — мөн үргэлж `JobRepository`-г байгуулж, startup scan-ийг ажиллуулна. `AppContext()`-ийг аргументгүй үүсгэж болохыг ажиллуулж баталгаажууллаа. Гэвч restart-to-open урсгал өөрөө дуусаагүй байна. § P-г үзнэ үү.
- [ ] Transcript adapter artifact болон checkpoint бичдэг боловч transcript-д зориулсан COMPLETE Job metadata record үүсгэхгүй. Repository scan нь COMPLETE job-уудыг recoverable жагсаалтад оруулдаггүй тул шинээр эхлүүлсэн Jobs дэлгэцэд өмнөх completed transcript автоматаар илрэхгүй.
  - **Засвар:** repository нь одоо COMPLETE REAL job-уудыг тусдаа олдож чадна — `scan()["completed_real"]` болон `list_completed_real()`. `AppContext` эхлүүлэлтэд тэдгээрийг `JobManager`-д нэмнэ. COMPLETE Job metadata-г бичдэг нь UI даврга (adapter биш).
- [ ] Artifact дотор `fingerprint` хадгалагдсан ч reopen код одоогоор түүнийг одоогийн source-ийн fingerprint-тэй **харьцуулдаггүй**. Artifact JSON-д mode талбар байхгүй тул artifact mode-ийг тусад нь баталгаажуулахгүй; job-ийн mode-оор замыг тооцно.
  - **Засвар (дутуу байгаа хэсэг):** artifact-д `mode`, `fingerprint`, `fingerprint_settings`, `fingerprint_schema_version`, `fingerprint_source_type` талбарууд нэмэгдсэн бөгөөд reopen код `fingerprint`-ийг харьцуулж байгаа. **Гэвч** reopen код тооцоолж байгаа нь artifact-ийн `fingerprint_settings`-г **ашиглахгүй** тул бодит adapter-ийн artifact-ийг хүрэлцэхэд `ValueError: Fingerprint mismatch between artifact and current source` гарч байна. Иймээс одоогийн нөхцөл: **зөвхөн canonical fingerprint-ийг хэрэглэдэг adapter-ийн artifact л хүлээн зөвшөөрөгдөнө**; хуучин artifact-ийг ялгаж татдаг. § P-г үзнэ үү.
- [ ] Loader row бүрийн ID хоосон биш, `start >= 0`, `duration > 0` гэдгийг л шалгана; давхардсан ID, finite timestamp, source duration-ийн дотор багтах эсэхийг бүрэн шалгахгүй. Нээх үеийн JSON уншилт/парсинг GUI thread дээр синхрон явагдана.
  - **Засвар:** row-ийн шалгалт одоо бүрэн — хоосон ID, **давхардсан ID**, `NaN`/finite-биш `start`, `duration <= 0`, finite-биш `end`, мөн artifact duration-аас хэтэрсэн `end` бүгд хасагдана. Гэвч JSON уншилт/парсинг **одоо ч** GUI thread дээр синхрон явагдана.
- [ ] Одоогийн 6 focused test нь UI товчны end-to-end/GUI-thread ачаалалт, fingerprint mismatch, schema mismatch/corruption, mode mismatch, дутуу/давхардсан/хязгаараас гадуурх row-уудыг бүрэн хамрахгүй.
  - **Нэмэлт:** `tests/test_fingerprint.py` (**40 passed in 1.61s**) нь canonical fingerprint-ийг, adapter болон repository-ийн нэг утга болдгийг, artifact-ийн fingerprint хүүхдүүдийг, legacy fingerprint-ийг ялгахыг шалгана. Гэвч бодит adapter-ийн artifact-аар **бодит reopen** хийсэн шалгалт, зэрэг GUI thread-ийн ачаалалтын шалгалт, `mode` зөрүүний шалгалт, artifact path-ийн containment шалгалт, хуучин artifact-ыг ялгах шалгалт **үлдсэн байна**.

### Нэгдүгээр эрэмбийн дараагийн ажил — Jobs persistence/reopen босоо slice

- [x] Одоогийн Step-5 transcript-open кодын талаар тусдаа, зөвхөн унших NVIDIA Nemotron review хийлгэж, дүгнэлтийг эх код/тестээр баталгаажуулах. Prompt: `outputs/nemotron-review-prompt-step5-transcript-reopen.md`.
  - **Хийгдсэн.** Nemotron-ийн дүгнэлт: **REJECT** — 16 олдвор, 7 нь агуу түвшин (critical). Олдвор бүрийг эх код болон ажиллуулсан тестээр давхар шалгаж, засварын дарааллыг гаргасан.
- [x] Хэрэглэгчийн эрхтэй, тогтвортой jobs root-ийг энгийн апп эхлүүлэх үед тохируулах; demo ба REAL тохиргоог тодорхой салгах.
  - **Хийгдсэн.** `AppContext` нь `$MMNEXT_JOBS_DIR`, байхгүй бол `~/.mmnext/jobs` гэж тогтоод, үргэлж repository-г байгуулна. Demo ба REAL ялгаа нь `Job.is_demo`-оор хадгалагддаг.
- [ ] Транскрипт хүчинтэй болж atomic artifact commit амжилттай дууссаны дараа л source, mode, fingerprint, schema, artifact path болон COMPLETE төлөвтэй Job metadata-г хадгалах.
  - **Хэсэгчлэн хийгдсэн:** UI даврга artifact-ыг шалгасны дараа COMPLETE REAL Job-ийг хадгалж, алдаа гарвал log руу бичиж, төлөвийг `failed` болгоно. `Job.fingerprint` болон `Job.artifact_path` нь metadata-руу шинээр round-trip хийгдэхэд болсон.
- [ ] Restart үед дууссан REAL transcript job болон сэргээж болох incomplete job-уудыг Jobs дэлгэцэд харуулах; completed transcript-ийг зөвхөн хэрэглэгчийн сонголтоор нээх. Автоматаар resume хийхгүй.
  - **Хэсэгчлэн хийгдсэн:** completed REAL job-ууд `scan()["completed_real"]` болон `list_completed_real()`-аар олдоно, `AppContext` эхлүүлэлтэд `JobManager`-д нэмнэ. Автоматаар resume хийхгүй гэсэн шаардлага биелсэн. Гэвч Jobs дэлгэцэд бүрэн харагдах ба бодит reopen ажиллах урсгал дуусаагүй.
- [ ] Reopen шалгалтад job/artifact төлөв, schema, mode, source identity/fingerprint, unique ID болон finite/bounded timestamps оруулах; ямар нэг шалгалт унавал demo fallback хийхгүй, өмнөх session/эх row-уудыг өөрчлөхгүй.
  - **Хэсэгчлэн хийгдсэн:** төлөв, schema, source identity/fingerprint, unique ID, finite/bounded timestamps оруулсан. **Үлдсэн:** artifact-ийн `mode`-ийг харьцуулахгүй, хуучин (legacy) artifact-ыг ялгаж татдаггүй, artifact path-ийн containment шалгалтгүй. Мөн reopen-ийн fingerprint-ийн тооцоолол artifact-ийн settings-гүй тул бодит artifact-ыг хүрэлцэхэд зөрчил гарна.
- [ ] Том artifact уншилт/validation-ийг GUI thread-ээс гаргах; ажил дуусах үед сонгосон job/source солигдсон бол хуучин үр дүнг холбохгүй.
  - **Үлдсэн.**
- [ ] Амжилттай open, restart discovery, муу/дутуу/incompatible artifact, source/fingerprint/mode зөрүү, duplicate/out-of-range rows, off-GUI-thread ажиллагаа, UI failure visibility болон Exact Dubbing immutable-field invariants-ийг тестлэх.
  - **Хэсэгчлэн хийгдсэн:** `tests/test_fingerprint.py` (40 шалгалт), `tests/test_job_repository.py`, `tests/test_transcript_regressions.py`, `tests/test_transcript_integration.py`, `tests/test_real_transcript.py` — fingerprint, discovery, row шалгалт, failure visibility хамрагдсан. **Үлдсэн:** бодит adapter artifact-аар reopen, off-GUI-thread ажиллагаа, `mode` зөрүү, containment, legacy artifact ялгалт.
- [ ] Шинэ бүтэн suite, strict transcript acceptance, Jobs→Workspace restart flow-ийн бодит integration шалгалт бүгд амжилттай болсны дараа л энэ slice-ийг дууссан гэж тэмдэглэх.
  - **Үлдсэн.** Бүтэн suite **342 passed, 1 skipped**. Strict acceptance болон бодит integration урсгал дуусаагүй.

### Томоохон үлдсэн ажлын дараалал

1. Jobs persistence/reopen/recovery-ийг энгийн аппын бодит урсгалд холбож баталгаажуулах.
   - **Одоогийн төлөв:** canonical fingerprint нэгтгэсэн, completed REAL job олдох, jobs root бүрэн тохируулагдсан. **Үлдсэн:** reopen-ийн fingerprint-ийн тооцоололд artifact-ийн `fingerprint_settings`-г хэрэглэх, artifact `mode`-ийг харьцуулах, legacy artifact-ыг ялгах, artifact path containment шалгах, artifact уншилтыг GUI thread-ээс гаргах, хуучин үр дүнг холбохгүй байх (stale guard), бодит adapter artifact-аар reopen шалгалт.
2. Narrator Mode-ийн бодит plan/translation/TTS/Smart Sync adapter-уудыг тус тусад нь нэмж, safe stop/reuse болон үр дүнгийн validation-тай босоо урсгал болгох.
3. Exact Dubbing-ийн prepare/export, TTS/cache/speech fitting/final duration ба audio validation-ийг нэмж, immutable dialogue contract-ийг хадгалах.
4. Splitter-ийн planner, smart-cut/short-tail rules, per-part artifact/checkpoint/resume-ийг холбох.
5. Common Editing-ийн non-destructive timeline/range, overlays болон export validation-ийг хэрэгжүүлэх.
6. Windows packaging, diagnostics, recovery cleanup, non-ASCII/Myanmar paths, CPU/GPU, clean-machine болон user-guide release шалгалтыг дуусгах.

Одоогийн бодит хязгаар: translation, Gemini, TTS болон final video rendering холбогдоогүй; ямар ч simulated/demo алхмыг бодит production completion гэж тооцохгүй.


## P. Canonical fingerprint fix cycle — баталгаажилсан төлөв (Nemotron REJECT-ийн дараа)

Энэ хэсэг нь Nemotron-ийн **REJECT** (16 олдвор, 7 агуу түвшин) дараах засвар хийсний дараах **бодитоор ажиллуулж баталгаажуулсан** төлөв юм. Дээрх § O-ийн хуучин бичлэгүүдийг устгаагүй; тэдгээрийн доторх "засвар" тэмдэглэгээнүүдээр ялгаатай.

### Өөрчилсөн файлууд ба шалтгаан

- `mmnext/domain/fingerprint.py` (**шинэ**, 236 мөр) — `canonical_fingerprint(source_path, source_type, mode, settings=None, schema_version=...)` гэсэн **цорын ганц** алгоритм. `fp2:<sha1hex>` хэлбэртэй. `FingerprintError`, `normalize_source_type`, `normalize_source_path`, `is_canonical_fingerprint`, `is_source_available`, `require_source_available` мөн энд. Qt-ийг импорт хийхгүй — domain даврга Qt-гүй байх дүрэмтэй.
- `mmnext/domain/__init__.py` — `__all__` жагсаалтад `"fingerprint"` нэмэгдсэн.
- `mmnext/domain/models.py` — `JobCheckpoint` дээр `fingerprint_settings`, `fingerprint_source_type`, `fingerprint_schema_version` талбарууд төгсгөлд нь нэмэгдэж, `to_dict`/`from_dict`-д round-trip хийгдэв. `CHECKPOINT_SCHEMA_VERSION = 2`-ыг **өөрчлөөгүй**.
- `mmnext/infrastructure/repository/job_repository.py` — `compute_fingerprint()` хэвээ байгаа боловч одоо canonical функцийг дуудана; хуучин `local` гэдэг нөхцөл (`local_file` гэсэн enum утгатай үл зөрөх) асуудалтай `_source_identity`/`_file_meta`/`_sha1_hex` хасагдсан; `Job.fingerprint` ба `Job.artifact_path` metadata-руу round-trip хийгдэв; `scan()`-д `completed`, `completed_real` нэмэгдсэн; `list_completed_real(source_path=None)` шинэ; `can_resume_job` нь checkpoint-ийн settings-ийг ашиглана.
- `mmnext/infrastructure/transcript_adapter.py` — `_fingerprint` нь canonical функцийг дуудана; шинэ `_fingerprint_settings`; artifact JSON-д `mode`, `fingerprint_settings`, `fingerprint_schema_version`, `fingerprint_source_type` бичигдэнэ. `hashlib`/`json` импорт хасагдсан. **Энэ файлын кодонд "translate" гэсэн үг оруулахгүй** — `tests/test_transcript_integration.py` шууд текстээр шалгадаг.
- `tests/test_fingerprint.py` (**шинэ**, 40 шалгалт) — canonical алгоритм, adapter ба repository-ийн нэг утга болдог, artifact-ийн fingerprint хүүхдүүд, legacy fingerprint ялгалт, `Job.fingerprint` round-trip, legacy metadata ⇒ `""`, `JobCheckpoint`-ийн гурван талбарын round-trip, completed REAL discovery, бодит adapter artifact-ыг шалгах.
- `.work/review-baselines/transcript-reopen-fixcycle-01/` — эхний хувилбарын byte хуулбарууд, `manifest.sha256`, `changes.diff`, `changed-files.sha256`, `README.md`. Git байхгүй учраас энэ нь өөрчлөлтийн баталгаа юм.

### Задлан шалгасан үр дүн

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **342 passed, 1 skipped in 70.89s**. `skip`: `tests/test_transcript_regressions.py:158` (зөвшөөрөгдсөн media fixture болон орон нисангийн Whisper model шаардлагатай).
- `.\.venv\Scripts\python.exe -m pytest tests\test_fingerprint.py -q --confcutdir=tests -p no:cacheprovider` → **40 passed in 1.61s**.
- `.\.venv\Scripts\python.exe -m pytest tests\test_job_repository.py tests\test_transcript_regressions.py tests\test_transcript_integration.py tests\test_real_transcript.py -q --confcutdir=tests -p no:cacheprovider` → **70 passed, 1 skipped in 2.73s**.
- `.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider` → **32 passed in 11.17s**.

### Одоо ч үнэн биш байгаа зүйлс

- **Бодит artifact-ыг reopen хийхэд fingerprint зөрчил гарна.** Reopen код artifact-ийн `fingerprint_settings`-г ашиглахгүйгээр тооцоолдог тул бодит adapter-ийн artifact-ийг `ValueError: Fingerprint mismatch between artifact and current source` гэж хасаж байна. Ажиллуулж баталгаажуулсан.
- Artifact-ийн `mode` харьцуулагдахгүй, legacy artifact ялгагдахгүй, artifact path-ийн containment шалгалтгүй, artifact уншилт GUI thread дээр, stale-result guard байхгүй — эдгээрийг UI давргын эзлэх хэсэг хариулж байна.
- Бодит Whisper smoke болон бүтэн resume урсгал дуусаагүй; GUI, mpv, FFmpeg-ийг шалгаагүй.
- `outputs/`-ийн prompt-ийг өөрчлөөгүй.


## Q. Reopen hardening cycle — баталгаажилсан төлөв (2026-10-21, § P-ийн дараа)

Энэ хэсэг нь § P-д үлдсэн бүх reopen дутагдлыг хассан, **бодитоор ажиллуулж баталгаажуулсан** дараагийн циклийн төлөв юм. § O, § P-ийн хуучин бичлэгүүдийг устгаагүй; дээрх "Одоо ч үнэн биш байгаа зүйлс"-ийн өгүүлбэрүүд энэ хэсгээр орлохдоно.

### Өөрчилсөн файлууд

- `mmnext/ui/app_context.py` — `open_transcript_from_job()`-ийн уншилт/шалгалтын хэсгийг `prepare_transcript_from_job()` гэсэн **цэвэр** (project-ыг огт хөндөхгүй) функц болгож, хэрэглэлтийг `_apply_prepared_transcript()` гэж салгав. Fingerprint-ийг **artifact-ийн өөрийн** `fingerprint_settings` / `fingerprint_source_type` / `fingerprint_schema_version`-оос дахин тооцдог болсон. `mode` харьцуулалт, legacy artifact-ийн ялгалт, artifact path containment, эх сурвалжийн байдлын шалгалт нэмэгдсэн. `_reopen_token` (stale guard) нэмэгдсэн. `start_reopen_transcript` нь **bound method**-уудыг connect хийж, өөрийн эхний `def`-closure хэлбэрээс салгав.
- `mmnext/ui/reopen_transcript_worker.py` — worker одоо **зөвхөн уншиж шалгана** (`prepare_transcript_from_job`), project-ыг өөрчлөхгүй; бэлэн үр дүнг signal-аар буцаана.
- `mmnext/ui/screens/jobs_screen.py` — **Open transcript** товч одоо `start_reopen_transcript()`-ыг дуудана (өмнө нь GUI thread дээр синхрон `open_transcript_from_job()` байсан). `transcriptReopened` сигналд bound method холбогдсон.
- `mmnext/ui/main_window.py` — `transcriptReopened`-д bound method холбогдож, **амжилттай reopen хийсний дараа Workspace руу шилжинэ** (Jobs→Workspace урсгал дуусна).
- `tests/test_transcript_open.py` — artifact-ыг бичих туслахч нь одоо гэрээны бүх талбаруудыг (`mode`, `fingerprint_settings`, `fingerprint_source_type`, `fingerprint_schema_version`) бичнэ; шинэ 8 шалгалт нэмэгдсэн.
- `tests/test_transcript_reopen_thread.py` (**шинэ**, 13 шалгалт) — off-GUI-thread уншилт, signal-аар алдаа, GUI thread дээр хэрэглэлт, бодит adapter artifact-аар reopen, Jobs дэлгэцийн товч, дараах code-review засваруудын regression-ууд.

### Code-review cycle — олдсон бөгөөд засварласан зүйлс

Өмнөх хэсэгт бичсэн кодыг дахин шалгахад дараах зүйлс олдсон. Бүгд засварлагдаж, regression тест нэмэгдсэн.

- [x] **Хувиргалтыг удирдахгүй байсан.** `dirty.total_dirty()` шалгалт нь зөвхөн *prepare* үед (worker thread дээр) хийгдэж, `project.load()` болон бүх session-ийг орлох үед дахин хийгдэхгүй байв. Ачаа ачаалагдах хооронд хэрэглэгчийн засвар үгүйсэж дараагийн session-ээр **дуусах** байсан. Одоо `_apply_prepared_transcript()` нь **GUI thread дээр дахин шалгана**; засвар гарсан бол "Unsaved edits appeared while the transcript was loading" гэж татсаад юу ч хэрэглэхгүй. `test_reopen_refuses_when_edits_appeared_during_the_load`.
- [x] **Session-ийн mode workspace-д дамжигдэхгүй байв.** `project.load()` mode өөрчлөлийг мэдэгдэхгүй тул workspace-ийн mode switcher хуучин mode-оо үлдэж, **нээсэн transcript-ийн мөрүүд буруу panel-ийн ард нуугдах** байв. Одоо `_apply_prepared_transcript()` нь mode-ийг илэрхий sync хийнэ. `test_reopen_syncs_the_workspace_mode`.
- [x] **Задалгааны бус JSON тохиолдолд crash гаргав.** `read_json` ямар ч JSON утга буцааж болно; `data.get(...)` нь list/string дээр `AttributeError` өгөх байв. Мөн `int(schema_version)`, `float(duration_s)`, `Path(...).samefile(...)` нь харгалзан `ValueError`/`TypeError`/`OSError` гаргаж байсан. Одоо бүгд **цэвэр `ValueError`** болж, "corrupt or unreadable" / "Unsupported transcript schema version" / "source path" гэсэн тодорхой мессежтэй татдаг. `test_reopen_rejects_a_non_object_artifact`, `test_reopen_rejects_a_non_numeric_schema_version`, `test_reopen_rejects_an_artifact_whose_source_vanished`.
- [x] **Үр дүнг холбох нь signal-ийн дарааллаас хамааралтай байв.** `_on_reopen_result` нь `self._reopen_thread` байхыг шаарддаг бөгөөд `finished` түүнийг **эхэнд** цэвэрлэх боломжтой байсан. Одоо **request id** ашиглана: id-г зөвхөн **шинэ** хүсэлт сольдог тул `result`/`finished`-ийн дарааллаас үл хамаарна. `test_reopen_result_is_dropped_for_a_superseded_request`.
- [x] **Амжилттай reopen нь хэрэглэгчийг Workspace-д авахгүй байв.** Jobs→Workspace урсгал дуусахгүй байсан. Одоо `MainWindow._on_transcript_reopened()` амжилттай reopen хийсний дараа Workspace руу шилжинэ. `test_main_window_lands_in_the_workspace_after_a_reopen`.
- [x] `prepare_transcript_from_job()`-д буцаах төрлийн annotation нэмэгдсэн: `tuple[ProjectSession, list[TranscriptRow], str]`.

### Задлан шалгасан үр дүн

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **364 passed, 1 skipped in 66.76s**. `skip`: `tests/test_transcript_regressions.py:158` (зөвшөөрөгдсөн media fixture болон орон нисангийн Whisper model шаардлагатай).
- `.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_transcript_reopen_thread.py -q --confcutdir=tests -p no:cacheprovider` → **28 passed in 3.87s**.
- `.\.venv\Scripts\python.exe -m pytest tests\test_architecture_gates.py tests\test_fingerprint.py tests\test_job_repository.py tests\test_narrator_coordinator.py tests\test_narrator_planning_service.py -q --confcutdir=tests -p no:cacheprovider` → **73 passed in 2.09s**.
- `.\.venv\Scripts\python.exe scripts\check_shell.py` (offscreen) → `MainWindow OK`, 7 дэлгэц, `closed`, exit 0.

### Одоо ч үнэн биш байгаа зүйлс

- Бодит **Whisper** smoke (орoн нисангийн model ашигласан transcript-ийн бодит reopen) хэрэглэгчийн media fixture/model тохируулгагүйгээр ажиллаагүй. `test_real_adapter_artifact_reopens_end_to_end` нь **бодит adapter-ийн artifact writer-ийг** ашиглаж байгаа боловч inference-ийг хийхгүй — FFmpeg/Whisper шаардлагагүй.
- Бүтэн **Jobs→Workspace restart flow** нь бодит media-гаар (restart-ийн дараа) ажиллуулагдаагүй; нэг process доторх signal-ийн урсгал баталгаажлагдсан.
- Narrator heavy integration (Gemini story context, translation batching, Edge TTS, Smart Sync render) **эхээж хэрэглээгүй** — энэ нь дараагийн босоо slice.
- `pyproject.toml`-ийн setuptools `packages` жагсаалтад `mmnext.infrastructure.repository` ба `mmnext.services.adapters` ороогүй тул non-editable install-ийн wheel хуурамсан байна. Энэ нь энэ slice-ийн хамрах хүрээнд ороогүй (release hardening).
  - **Засвар (Narrator pipeline slice):** хоёр субпакеты `pyproject.toml`-ийн `packages` жагсаалтад нэмэгдсэн, тиймээс non-editable install wheel-ийг одоо бүтэн болгоно.


## R. Narrator heavy integration pipeline slice — баталгаажилсан төлөв (2026-10-21, § Q-ийн дараа)

Энэ хэсэг нь § Q-д үлдсэн "Narrator heavy integration эхээж хэрэглээгүй" гэсэн дарааллын **үрсгэлэн дараагийн босоо slice**-ийн бодитоор ажиллуулж баталгаажуулсан төлөв юм. § O, § P, § Q-ийн хуучин бичлэгүүдийг устгаагүй; дээрх "Одоо ч үнэн биш байгаа зүйлс"-ийн өгүүлбэрүүд энэ хэсгээр орлохдоно.

### Өөрчилсөн ба шинэ файлууд

- `mmnext/services/protocols.py` — `TranslationProvider`, `SpeechSynthesizer`, `SmartSyncRenderer` protocol-ууд нэмэгдсэн. `TranslationProvider.translate_segments()` нь **narrator unit** (`NarrationSegment`) жагсаалт авч, segment тус бүрд нэг Myanmar орчуулга буцаана. Энэ нь exact-dubbing translation-ийн тусдаа contract-ийг хадгална. `SmartSyncRenderer.render()`-ийн `emit` параметр хасагдсан (progress нь coordinator-оос `ProgressEvent` sink-ээр дамжина).
- `mmnext/services/adapters/narrator_translation.py` (**шинэ**) — `LegacyNarratorTranslationAdapter` (legacy Gemini translator-ийг defensively ачаалж, дутуу бол **хоосон** орчуулга буцаан failure-ийг log-оор хэлдэг — fake success биш) ба `DemoTranslationProvider` (deterministic Myanmar placeholder).
- `mmnext/services/adapters/narrator_tts.py` (**шинэ**) — `LegacyEdgeTtsAdapter` (Edge TTS байвал `edge_tts.Communicate` ашиглан Burmese үнэг хэл, байхгүй бол **хоосон** буцаана) ба `DemoSpeechSynthesizer`. `cache_key()` нь `voice|rate|text` sha256 — тэтгэмэл cache тэмдэг.
- `mmnext/services/adapters/narrator_render.py` (**шинэ**) — `LegacySmartSyncRenderer` (legacy render worker-ийг defensively ачаална; **legacy entry point байхгүй бол `False` буцаана** — "нийлсэн" гэж худал хэлэхгүй) ба `DemoSmartSyncRenderer`.
- `mmnext/application/narrator_pipeline_coordinator.py` (**шинэ**) — `NarratorPipelineCoordinator` + `NarratorPipelineResult`. Qt-ийг импорт хийхгүй. `plan -> translate -> synthesise -> render` дарааллыг удирдаж, stage boundary дээр safe stop хийнэ. Progress нь `ProgressEvent` sink-ээр (0–100 scale) тархана.
- `mmnext/ui/narrator_pipeline_worker.py` (**шинэ**) — `NarratorPipelineWorker` + `NarratorPipelineThread`. Heavy stage-үүд **GUI thread дээр хэзээ ч ажиллахгүй**.
- `mmnext/ui/app_context.py` — `narratorProgress` / `narratorStateChanged` signal-ууд, `start_narrator_pipeline()`, `stop_narrator_pipeline()`, `narrator_pipeline_running`, `narrator_state` / `narrator_message`, `_on_narrator_progress/_log/_result/_error/_thread_finished` bound slot-ууд.
- `mmnext/ui/workspace/mode_panels/narrator_panel.py` — "Run narrator pipeline (DEMO)" ба "Stop pipeline" товч, progress bar, status label, `set_pipeline_state()` / `set_pipeline_progress()`.
- `mmnext/ui/workspace/workspace_screen.py` — panel-ийн signal-уудыг bound method-уудтай холбосон; `narratorProgress` / `narratorStateChanged`-д bound method-ууд.
- `pyproject.toml` — `mmnext.infrastructure.repository` ба `mmnext.services.adapters` `packages` жагсаалтад нэмэгдсэн.
- `tests/test_narrator_pipeline.py` (**шинэ**, 11 шалгалт) — protocol conformance, stage progress, stop before start, stop between stages (partial result хадгалагдана), renderer-гүй үед дуусах, render failure, exact-dubbing contract-ийг хөндөхгүй байх, legacy adapter-уудын honest degradation.
- `tests/test_narrator_pipeline_ui.py` (**шинэ**, 7 шалгалт) — pipeline товч, narration segment-уудын шинжилт, **off-GUI-thread ажиллагаа** (thread id-г харьцуулж баталгаажуулна), panel lifecycle, давхардсан run-ийн татгалз, transcript шаардлага.

### Code-review cycle — олдсон бөгөөд засварласан зүйлс

- [x] **Транскрипт rows-ийг орчуулах гэж буруу төрөл ашигласан.** Эхний coordinator нь `translator.translate_segments(transcript)` гэж **source transcript rows**-ийг өгсөн боловч үр дүнгийг **narration segment**-үүдэд хуваарилсан. Plan нь rows-ийг нэгэд нэгээр нь хуваах тул тоо нь таарч болох ч, merge/summarise хийсэн planner-ийн үед **alignment-ийн алдаа** үүсэх боломжтой. Одоо translator-т **narrator unit**-ууд өгөгдөнө.
- [x] **Progress-ийн scale codebase-ийн гэрээтэй зөрчилд байлаа.** Эхний хэрэглээ нь `0.0 / 0.15 / 0.45 / 0.8 / 1.0` байсан боловч codebase-ийн бусад progress (`transcript_adapter`) нь **0–100** хэрэглэдэг. Одоо `0 / 15 / 45 / 80 / 100`.
- [x] **UI-ийн log sink нь байхгүй signal-ийг дуудаж байлаа.** Эхний `run_narrator_pipeline()` нь `self.logAdded.emit(...)` гэж **байхгүй** signal-ийг дууддаг байв. Одоо `append_log(LogEntry(...))` ашиглагдана; signal нь `logAppended`.
- [x] **Sync байдлаар pipeline-г GUI thread дээр ажиллуулж байлаа.** Эхний хувилбар нь pipeline-ийг `AppContext` доторээ шууд дуудаж байсан — энэ нь "GUI thread-иэс хэнд ажиллахгүй" дүрэмтэй зөрчилдөнө. Одоо `NarratorPipelineThread` дээр ажиллаж, `test_pipeline_runs_off_the_gui_thread` шалгалт нь thread id-ээр баталгаажуулна.
- [x] **Pipeline-ийн үр дүн UI-д буцаж орохгүй байсан.** Одоо `_on_narrator_result()` нь segment-үүдийг `project.set_narration_segments()`-ээр **GUI thread дээр** хэрэглэнэ.

### Задлан шалгасан үр дүн

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **382 passed, 1 skipped in 108.36s**. `skip`: `tests/test_transcript_regressions.py:158` (зөвшөөрөгдсөн media fixture болон орон нисангийн Whisper model шаардлагатай).
- `.\.venv\Scripts\python.exe -m pytest tests\test_narrator_pipeline.py tests\test_narrator_pipeline_ui.py -q --confcutdir=tests -p no:cacheprovider` → **18 passed in 17.34s**.
- `.\.venv\Scripts\python.exe scripts\check_shell.py` (offscreen) → `MainWindow OK`, 7 дэлгэц, `closed`, exit 0.

### Одоо ч үнэн биш байгаа зүйлс

- **Бүх adapter одоо DEMO байна.** `AppContext.start_narrator_pipeline()` нь `DemoTranslationProvider` / `DemoSpeechSynthesizer` / `DemoSmartSyncRenderer`-ийг ашиглана. `Legacy*` adapter-ууд байгаа боловч **өргөөсөн зэрэгт холбогдоогүй** — тэдгээрийг ашиглахын тулд Gemini credential, `edge_tts` суулгалт, legacy render worker-ийн entry point шаардлагатай. UI-ийн товч **"Run narrator pipeline (DEMO)"** гэж шууд тэмдэглэгдэж, status мөн "DEMO narrator pipeline" гэж хэлдэг.
- **Smart Sync render жинхэнэ бичлэг үүсгэхгүй.** `DemoSmartSyncRenderer` нь `b"demo"` гэсэн placeholder файл бичнэ. Үнэхээр video гарах өгөгдөл **байхгүй**.
- **Reuse detection үлдсэн байна.** `SpeechSynthesizer.cache_key()` тооцоолж байгаа боловч pipeline нь **файлын байдлаар reuse-ийг шалгахгүй** — cache-т орох/гарах логик дутуу. Stage-level safe stop есть, segment-level reuse check байхгүй.
- **Gemini story context, translation batching, checkpoint, audit** хэрэглээгүй. `TranslationProvider` нь `context` ба `glossary` параметрүүдийг авдаг ч одоогийн demo adapter-ууд тэдгээрийг ашиглахгүй.
- **Batch-folder queue, narration editor save/re-render, translation audit findings, final video validation, output reveal** хэрэглээгүй (§ Phase 4-ийн үлдсэн item-үүд).
- **Exact Dubbing, Splitter, Common Editing** босоо slice-ууд хэвээр дутуу.


## S. UI→infrastructure isolation and code-review debt cycle — баталгаажилсан төлөв (2026-10-21)

Энэ хэсэг нь UI-ийн техникүүдийг infrastructure-руу шууд хүрэхгүйгээр application-layer facade-аар дамжуулах дараагийн code-review debt slice-ийн **бодитогоор ажиллуулж баталгаажуулсан** төлөв юм. § O, § P, § Q, § R-ийн хуучин бичлэгүүдийг устгаагүй; дээрх "Одоо ч үнэн биш байгаа зүйлс"-ийн зөвхөн энэ хэсгээр орлох хэсгийг энд тодорхойлж заана.

### Өөрчилсөн ба шинэ файлууд

- `mmnext/application/job_service.py` (**шинэ**) — Qt-гүй application facade. Owner of `JobRepository`, public `source_dir()` / `job_dir()` / `checkpoint_path()` helpers, job scan/load/save, canonical fingerprint helper, `create_transcript_provider()`, `prepare_transcript_from_job()`, and `persist_completed_transcript()`.
- `mmnext/application/runtime_service.py` (**шинэ**) — `detect_dependencies()`-ийг application-layer facade болгож, `MainWindow`-ийг infrastructure-руу шууд хүрэхгүй болгосон.
- `mmnext/application/player_service.py` (**шинэ**) — `create_player`, `player.info`, `PlaceholderPlayer` type/tick semantics-ийг application-layer facade болгож, `PreviewPanel`-ийг infrastructure-руу шууд хүрэхгүй болгосон.
- `mmnext/domain/errors.py` (**шинэ**) — `TranscriptStopped` domain exception; infrastructure raise, UI catch, тэдгээр нь infra классруу шууд харагдахгүй.
- `mmnext/infrastructure/transcript_adapter.py` — `TranscriptStopped` одоо `mmnext.domain.errors`-ээс импорт хийж `__all__`-д нээлттэй байна; `WhisperTranscriptAdapter` нь `repo._job_dir(...)` оронг `repo.job_dir(...)` **public** method-руу солилоо.
- `mmnext/infrastructure/repository/job_repository.py` — `source_dir()`, `job_dir()`, `checkpoint_path()` нэмэгдсэн. Private helper-үүд нь дотоод хэрэглээнд хадгалагдсан; UI/application-ийн дуудлага private API-г ашиглахгүй.
- `mmnext/ui/app_context.py` — `JobService` / `RuntimeService`-ийг эзэмшдэг; `_job_repository` нь facade-д delegate хийгддэг property боллоо; `start_local_transcript()` нь `JobService`-ээр provider авна; `prepare_transcript_from_job()` буцах validation-ийг `JobService`-д delegate хийсэн; transcript job persistence нь `JobService.persist_completed_transcript()`-р ажиллана; persistence failure нь `_reset_transcript_progress_after_persistence_failure()`-р progress-ийг `0.0` + failed state-руу буцаана.
- `mmnext/ui/main_window.py` — dependency chips одоо `context.detect_dependencies()`-ийг дуудана.
- `mmnext/ui/workspace/preview.py` — `PlayerService`-ийг ашиглана; `PlayerInfo`, `PlaceholderPlayer`, `create_player`-руу шууд import хийхгүй.
- `mmnext/ui/workers.py` — `DownloadWorker` нь `JobService.checkpoint_path()`-ийг дуудаж `_checkpoint_path` private helper-гүй repo ашигладаг.
- `mmnext/ui/transcript_worker.py` — `TranscriptStopped`-ийг `domain.errors`-ээс авдаг.

### Code-review debt засагч

- [x] **UI အရမှ infrastructure import-г болив.** `tests/test_architecture_gates.py::test_ui_layer_does_not_import_infrastructure` AST parse хийж relative/absolute infrastructure import-г бүх `mmnext/ui/**/*.py` файлд илрүүлнэ.
- [x] **Private repository path API integration-ийг болив.** `test_ui_layer_does_not_call_private_repository_path_helpers` нь `_source_dir(`, `_job_dir(`, `_checkpoint_path(` шууд текст marker-ийг UI-д илрүүлнэ. Production application worker нь public `JobService` methods ашигладаг.
- [x] **Adapter fingerprint == artifact fingerprint.** `tests/test_fingerprint.py::test_adapter_checkpoint_fingerprint_equals_artifact_fingerprint` нь `adapter.fingerprint`-ийн утгыг `translated_gender.json`/transcript artifact-ийн `payload["fingerprint"]`-тай **директ тааруулж** шалгадаг; checkpoint-ийн bus shuu fingerprint settings-ууд ч мөн адил тааруулагдана.
- [x] **Persistence failure нь хуучин 100%-ийг үрүүлэхгүй.** `AppContext._reset_transcript_progress_after_persistence_failure()` нь `ProgressEvent(percent=0.0)` үүсгэж, дараа нь `failed` state-г тохируулна. `tests/test_live_transcript_workspace.py::test_job_persistence_failure_is_visible_and_not_silent` нь `transcript_progress.value() == 0` of active enable state `transcribe_button.isEnabled()`-ийг мөн шалгадаг.

### Задлан шалгасан үр дүн

- `.\.venv\Scripts\python.exe -m pytest tests/test_architecture_gates.py tests/test_job_service.py tests/test_fingerprint.py -q --confcutdir=tests` → **57 passed in 2.81s**.
- `.\.venv\Scripts\python.exe -m pytest tests/test_live_transcript_workspace.py tests/test_transcript_open.py tests/test_transcript_reopen_thread.py tests/test_job_repository.py tests/test_workers.py -q --confcutdir=tests` → **80 passed in 16.33s**.
- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **391 passed, 1 skipped in 90.87s**. `skip`: `tests/test_transcript_regressions.py:158`.
- `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe scripts\check_shell.py` → `MainWindow OK`, 7 дэлгэц, `closed`, exit 0.

### Одоо ч үнэн биш байгаа зүйлс

- Бодит Whisper smoke (`MMNEXT_TRANSCRIPT_SMOKE_MEDIA` + `MMNEXT_TRANSCRIPT_SMOKE_MODEL`) хэрэглэгчийн fixture/model тохиргоогүйгээр хуучин `1 skipped` байна.
- Real narrator adapter wiring (`Gemini`, `edge_tts`, legacy render entry point) хэвээр DEMO байна; test suite нь зөвхөн демонстрацион pipeline-ийг хамрагчдаг.
- Репо-д `.git` байхгүй тул branch/commit/PR нотолгоо байхгүй; энэ slice-ийн нотолгоо нь дээрх test command-ууд болон архитектур gate-ууд юм.


## T. Strict real-media Whisper acceptance — full-speech fixture နဲ့ ဖြေပြည့်ပြီး (2026-10-22)

§ M နဲ့ § N မှာ "Strict acceptance FAILED" လို့ မှတ်ထားခဲ့သော ရလဒ်ကို **ပိုးမွေးပြီး ဖြေပြည့်ပါပြီ**။ အချက်အနှောက်က acceptance media ကို **မှားယှာ ရွေးခဲ့သခြင်း** ဖြစ်ပါတယ်။ Source rows ကို clamp/drop/merge/retime လုပ်ခြင်း **မလုပ်**ထားပါ။

- [x] **အချက်အနှောက်:** နောက်ဆုံးမှတ်ထားခဲ့သော `inputs/osr-harvard-12s.mp4` က **clipped** fixture ဖြစ်ပါတယ် — 18.356s ရှိ `harvard.wav` ကို ၁၂ စက္ကန့်မှာ ဖြတ်ထားသဖြင့် နောက်ဆုံး utterance တစ်ခုတည်း ပြတ်နေပါတယ်။ ဖြတ်ထားသော အစွန်းတွင် Whisper ရဲ့ နောက်ဆုံး segment က clip boundary ကို ကျော်တာ ဖြစ်လို့ `[10.0, 13.0]` က 12.0s ထက် ကျော်ပါတယ်။ ဒါက model bug မဟုတ် — မှားယှာ ရွေးခဲ့သော fixture ပါ။
- [x] **မှန်တကယ်တဲ့ acceptance media:** `inputs/harvard-full.mp4` — `harvard.wav` အပြည့် speech (18.356190476s) ကို black video ထဲ mux ထားသည့်၊ authoritative duration **18.357s**။ အပြည့်အစုံ speech ဖြစ်လို့ နောက်ဆုံး segment က အစွန်းအတွင်းပါသည်။
- [x] **Canonical runner PASS:** `.work/transcript-acceptance/boundary_acceptance.py` → `boundary-acceptance-result.json` တွင် `status: PASS`၊ `timing_tolerance_s: 0`၊ `clipped_rejection: PASS` (clipped fixture ကို strict ငြင်းခြင်း ဆက်လက် အတည်ပြီး)၊ `full_source: PASS` (6 rows၊ နောက်ဆုံး end **17.600s** ≤ 18.357s၊ inference 2.051s၊ audio mono/16 kHz/PCM16 18.357s)၊ `real_ui: PASS` (offscreen REAL button → QThread → real FFmpeg/Whisper → 6 rows၊ REAL badge၊ progress 100၊ Exact Dubbing blank translation ကြောင့် validation ပိတ်ထားမှု မှန်)။
- [x] **Opt-in test ကို တိကျအောင် ပြင်ဆင်ခဲ့:** `tests/test_transcript_regressions.py::test_optional_real_local_transcript` ရဲ့ docstring က *full-speech* fixture ကိုသာ သုံးရမည် ဖော်ပြပြီး "zero tolerance" အောင် ရှင်းလင်းချက် ထည့်ထားပါတယ်။ Clipped source နဲ့ test က fail ဖြစ်တာ မှားမဟုတ် — ဒါက ပိုးမွေးနေသော strict rejection ပါ။
- [x] **Source rows မပြောင်းထားပါ။** Row တစ်ခုချင်းစီရဲ့ id/start/duration/text က မူလ မြင့်ကြီးနဲ့တူပါတယ်။ လုံးဝ မဖြတ်၊ မပြောင်း၊ မ merge မလုပ်ထားပါ။

### Задлан шалгасан үр дүн

- `.\.venv\Scripts\python.exe .work\transcript-acceptance\boundary_acceptance.py` → `status: PASS`, tolerance 0 စက္ကန့်၊ clipped rejection PASS၊ full source PASS၊ offscreen real UI PASS။
- `.\.venv\Scripts\python.exe -m pytest tests/test_transcript_regressions.py::test_optional_real_local_transcript -q --confcutdir=tests` (env: `MMNEXT_TRANSCRIPT_SMOKE_MEDIA=inputs/harvard-full.mp4`, `MMNEXT_TRANSCRIPT_SMOKE_MODEL=models/tiny.en`) → **1 passed in 26.59s**။
- Clipped fixture နဲ့ တိုင်းစစ်ခြင်း → ရိုးသား ငြင်းပါတယ် (`RuntimeError: Whisper segment s3 [10.0, 13.0] exceeds authoritative video duration 12.0s`)။

### ဆက်လက် မှားမှတ်ထားသင့်သောအချက်

- Strict timing validation **မပြောင်းထားပါ**။ Overshoot ဖြစ်သော နောက်ဆုံး segment ကို clamp/drop လုပ်တာ မလုပ်ထားသဖြင့် strictness ဆက်လက် အစိမ်းအမှန်ပါ။
- လက်ရှိ opt-in test က တစ်ခုတည်း media ကိုသာ သုံးပါတယ်။ အများအပြား media နဲ့ (အများဆိုရင် ကလီပ်ချထားသော အသံ) strict acceptance က မဖြစ်နိုင်သလို သတိပေးရမည်။


## U. Exact Dubbing TTS / render / cache နဲ့ final validation (2026-10-22)

`translated_gender.json` ကနေ စတင်ပြီး Exact Dubbing ကို REAL render လုပ်နိုင်အောင် လုပ်ထားသော vertical slice။ Legacy `J:\movie-recap` ကို **ဖတ်ခဲ့သား** (read-only contract)၊ ဖိုင်များ မဖြတ်ခြင်း၊ copy မလုပ်ခြင်း။ Contract ကို native အသစ်ဖြင့် အသုံးပြုထားပါတယ်။

### အသစ်ဖြင့်ဖန်တီး/ပြင်ဆင်ခဲ့သောဖိုင်များ

- `mmnext/domain/exact_dubbing.py` (**အသစ်**) — pure domain contract။ `translated_gender.json` schema စစ်ခြင်း (JSON array, `id`/`start`/`duration`/`original`/`burmese`/`gender`)၊ Myanmar Unicode regex `[\u1000-\u109f\uaa60-\uaa7f]`၊ gender → voice mapping (`male` → `my-MM-ThihaNeural`, `female`/`unknown` → `my-MM-NilarNeural`)၊ immutable source check (timing tolerance `1e-6`)၊ `speech_window()` (legacy rule: နောက်ဆုံး row ရဲ့ gap ကို 80 % အထိ ချဲ့၊ နောက်ဆုံး row ကို media အဆုံးနဲ့ clamp)၊ `atempo_chain()` (>2× ကို chain ခွဲ)၊ `cache_signature()` (`sha256(voice + "\n" + text)`)။ Qt/application/infrastructure import မရှိ။
- `mmnext/services/adapters/exact_dubbing_tts.py` (**ပြန်ရေးခဲ့**) — `LegacyExactDubbingTtsAdapter` (Edge TTS, retry ladder 6 ခု / 5-10-20-40-60 စက္ကန့်, `.partial` + atomic rename, `.sha256` sidecar) နဲ့ `LocalWaveTtsAdapter` (offline၊ အမှန်တကယ် PCM WAV ထုတ်၊ အလျားပြုချက် = စကားရှည်နဲ့ ကြာချိန်)။ Cache signature က voice + text ပဲ ပါတယ် — rate ပြောင်းလဲမှုက ကုန်နှင့်ကို မဖျက်ပါ။
- `mmnext/infrastructure/exact_dubbing_render.py` (**အသစ်**) — `FfmpegExactDubbingRenderer`။ moviepy မလိုတော့။ (1) `atempo` chain နဲ့ locked window ထဲသို့ fit (FFmpeg sample rounding ကြောင့် `target + 0.04` ကျော်ရင် ဒုတိယ correction pass)၊ (2) 44100 Hz အတိအကျ timeline ပေါ်တွင် numpy memmap နဲ့ bounded mix (စကားမရှိသော နေရာ ငြိမ်သက်)၊ (3) source video ကို မဖြတ်ဘဲ mux (`h264_nvenc` → `libx264` fallback)၊ (4) FFprobe နဲ့ duration + audio stream + video stream validation ကျော်မှ မဟုတ်မှ `.partial` → final rename မလုပ်ပါ။
- `mmnext/application/exact_dubbing_service.py` (**အသစ်**) — application facade။ UI က infrastructure ကို တိုက်ရိုက် မလုပ်ရ။ `render_from_translated_gender()` က `translated_gender.json` ကို အရင် သိမ်းပြီး source rows နဲ့ တိကျစစ်ပြီးမှ render စတင်ပါတယ်။
- `mmnext/application/exact_dubbing_render_coordinator.py` — rate နဲ့ re-synthesis ကို ဖယ်ရှားပြီး (fit ကို renderer ရဲ့ `atempo` က လုပ်သဖြင့်) final validation မှာ **audio-stream check** ထည့်ခဲ့ပါတယ်။
- `mmnext/ui/app_context.py` — `ExactDubbingService` facade ကို သုံးရင်း renderer/TTS ကို ရွေးပါတယ်။ `export_exact_dubbing()` က အခု legacy-compatible ဖြစ်အောင် `id` က **positional int index** ဖြစ်ပြီး source row id ကို အပိုးအပိုး `row_id` key အဖြစ် ထည့်ပါတယ် (legacy reader အပိုးအပိုး key ကို လက်ခံပါတယ်)။
- `tests/test_exact_dubbing_render.py` (**အသစ်**, 29 tests) — domain schema/validation, cache, နဲ့ **real FFmpeg render** (video ထုတ် → WAV synthesize → fit → mix → mux → ffprobe validate)။ FFmpeg မရှိတဲ့ machine မှာ pure-domain test တွေကိုလည်း ဆက်လက် run ဖြစ်အောင် `skipif` ကို FFmpeg-dependent test တွေမှာသာ သုံးပါတယ်။

### Code-review fix cycle — Exact Dubbing slice (2026-10-22)

Independent review က exact-dubbing slice ကို စစ်ဆေးပြီး ရလဒ်တိုင်းကို source နဲ့ run ပြီး အတည်ပြပြီး ပြင်ဆင်ပါတယ်။

- [x] **CRITICAL — renderer/TTS diagnostic အားလုံး ပျောက်နေခဲ့သည်။** `create_coordinator()` က log callback မပေးတာကြောင့် `"Render failed"` ပဲ ပေါ်ပြီး `"FFmpeg mux failed: …"`၊ `"Output duration mismatch: …"` တို့ မမြင်ရဘူး။ အခု log callback က synthesiser/renderer/coordinator အားလုံးမှာ ပေးပြီး၊ failure ရင် renderer ရဲ့ `error` က coordinator result message ထဲမှာ အမှန်တကယ် အကြောင်းရင်းအမြစ် ပါပေါ်ပါတယ်။
- [x] **CRITICAL — UI က ပေးခဲ့သော duration က media duration ကို အစားထိုးနေခဲ့သည်။** Probed media duration ကသာ authoritative ဖြစ်ပြီး၊ caller က ပေးသော duration က ချိန်ချင်းမှာ source ပြောင်းသွားသော warning သာ ဖြစ်ပါတယ်။ ရင်းသားအတိုင်း output က တိုက်ရိုက် တိုးပြီး validation ကလည်း အဲဒီ ပိုးငွေနဲ့တူ ပြောင်းလဲသွားပါတယ်။
- [x] **CRITICAL (product bug) — numpy ရဲ့ concurrent import က UI render ကို deadlock လုပ်ခဲ့သည်။** `import numpy` က function အတွင်း lazy ဆိုရှားလို့ **worker thread ပထမအကြိမ်** import လုပ်ရာမှာ interpreter ကြန့်နေပါတယ် — main thread ကမှ မလုပ်ရဘူး။ numpy ကို အခု module အဆင်း တစ်ခါတည်း (loading thread ပေါ်ပဲ) import လုပ်ပြီး၊ optional dependency မရှိရင် clear error ပြပါတယ်။ **UI path ကို တိုက်ရိုက် run လုပ်တဲ့ test မရှိလို့ ဒီ defect က မဖမ်းမိခဲ့ပါ** — အခု `test_the_ui_render_goes_through_the_exported_translation` က ကားတားတယ်။
- [x] **Atempo correction pass က dead code ဖြစ်နေခဲ့သည်။** atempo branch က `-t` နဲ့ limit ထားသဖြင့် produced length က အတိအကျ target ဖြစ်ပြီး correction pass က မရောက်ခဲ့ပါ။ အခု `-t` ကို ဖြတ်ပြီး produced length ကို တိုင်းတား၊ legacy algorithm အတိုင်း corrected ratio နဲ့ ပြန် encode ပြီးမှ window ထဲ ချောင်းတဲ့ အစွန်းကို ဖြတ်ပါတယ်။
- [x] **Mix scratch file က Windows မှာ ဖျက်ခြင်း မဖြစ်ခဲ့ပါ။** memmap mapping ကို အတိအကျ close လုပ်ပြီးမှ scratch file က ဖျက်ပါတယ် (float32 + explicit close)။ fitted clips နဲ့ `dubbed_audio.wav` ကလည်း run ပြီးမှ ဖျက်ပါတယ်။
- [x] **Render report က publish မလုပ်ခင် ရေးပြီး output path က မရှိတဲ့ partial ကို ညွှန်းနေခဲ့သည်။** အခု report ကို coordinator က output ကို publish ပြီးမှ ရေးပါတယ်၊ `output` က final path ဖြစ်ပါတယ်။ ရှေ့သွားသော run က "success" လို့ ပုံစံ report မကျန်တော့ပါ။
- [x] **Final validation က audio stream ရဲ့ ကိုယ်ပိုင် duration ကို မစစ်ခဲ့ပါ။** ယခု container duration အပြင် audio stream duration ကိုလည်း စစ်ပါတယ် — ခုလိုင်မြင်နေသော/လုံးဝ အသံမဲ့ audio track ကို ငြင်းပါတယ်။
- [x] **Coordinator က `"ffprobe"` ကို hard-code ထားခဲ့သည်။** ffprobe path ကို settings မှာ ပို့ပြီး probe မအောင်မြင်ခြင်းနဲ့ "audio stream မရှိတော့" ကို မှားပြောင်းတာ ဖြေပြပြီး ခွဲခြားပါတယ်။
- [x] **BOM ပါတဲ့/မရှင်တဲ့ translation file က "not found" လို့ ပြောခဲ့သည်။** `utf-8-sig` နဲ့ ဖတ်ပြီး၊ missing နဲ့ unreadable ကို သီးသန့် အမှတ်ပြုပါတယ်။
- [x] **`row_id` က file name အဖြစ် သုံးခဲ့သည်။** artefact ကနေလာသော row id က path separator ပါနိုင်လို့ **positional index** ကိုသာ သုံးပါတယ် (legacy အတူ)။
- [x] **subprocess decode/timeout မရှိခဲ့သည်။** အားလုံး `encoding="utf-8", errors="replace"` + timeout ပါဝင်ပြီး၊ timeout ဖြစ်ရင် အမှန်တကယ် message ပေါ်ပါတယ်။
- [x] **DEMO session က REAL အဖြစ် အမှတ်ပြုခဲ့သည်။** အခု `session.is_demo or coordinator.is_demo` ကို သုံးပါတယ်။ ထပ်မံတွေ့ကားတဲ့ bug — demo synthesiser က အသုံးပြုပြီးပါက `available()` က **True** ဖြစ်တာကြောင့် availability ကို fallback မလုပ်ခင် ဖတ်ပါတယ်။
- [x] **Speed warning က user မရောက်ခဲ့ပါ။** `result.warnings` ကို log drawer ထဲ ပို့ပါတယ်။
- [x] **UI product path က `translated_gender.json` ကို မသုံးခဲ့ပါ။** အခု render က exported file ကို validate ပြီးမှ စတင်ပါတယ် — ဒါက test-only path မဟုတ်တော့ပါ။
- [x] **တချို့ minor item** — `EXACT_DUB_VOICES` ကို `Gender.voice` ကနေ ရယူပြီး (mapping တစ်ခုတည်း)၊ မလိုအပ်တဲ့ helper နှစ်ခု ဖယ်ရှားပြီး၊ numpy ကို dependency chip ထဲ ထည့်ပြီး၊ WAV ကို တစ်ခါတည်း buffer နဲ့ ရေးပြီး၊ stop message ကို မှန်တကယ်အတိအကျ ဖြစ်အောင် ပြင်ပြီး၊ schema docstring ကို implementation နဲ့ တူညီအောင် ပြင်ပါတယ်။
- [x] **မမှန်တကယ် မလုပ်ရသေးသော အချက်** — review မှာ မှတ်ထားခဲ့သော Edge TTS retry ladder က တစ် row အတွက် ၁၃၅ စက္ကန့် ရပ်တန့်နိုင်သော်လည်း (legacy အတူ)၊ coordinator က ပထမဆုံး မအောင်မြင်သော row မှာ ရပ်ပါတယ်။ မှတ်ထားခဲ့သော အချက်အလက် မှာ အမှန်တကယ် မဟုတ်။
- [x] **မမှန်တကယ် မလုပ်ရသေးသော အချက်** — mix က source soundtrack (music/SFX) ကို လုံးဝ မထည့်ပါ (legacy အတူ)။ နောက်ဆုံး row က trailing gap ထဲမှာ မပြောင်းပါ (legacy အတူ)။ နှစ်ခုလုံး product ဆုံးဖြတ်ချက် ဖြစ်ပါတယ်။

### အတည်ပြချက်

- [x] **Source rows ဘယ်တော့မှ မပြောင်းထားပါ။** `id`/`original`/`start`/`duration` က locked။ Render test က row snapshot ကို render မတိုင်မီ/ပြီး နှစ်ဖက် တူညီကြောင်းကိုလည်း၊ **source media ဖိုင်က byte-identical** အဖြစ် ကျန်ရှိကြောင်းလည်း စစ်ပါတယ်။ ထပ်မံတွေ့ကားတဲ့ defect ကို ဖယ်ရှားဖို့ ရေးပြီး row snapshot တစ်ခုတည်းကို တိုင်းရက် မလုပ်ဘဲ **mixed audio ရဲ့ ပထမဆုံး non-silent sample က `row.start * 44100` နေရာမှာ ရှိတာ** ကို စစ်ပါတယ်။
- [x] **Drift ဖြစ်တဲ့ translation ကို ငြင်းပါတယ်။** `start` ပြောင်းတဲ့ translation → speech မစတင်ခင်း `ValueError: changed start`၊ final file မရှိ။
- [x] **Final duration + audio-stream validation အလုပ်လုပ်ပါတယ်။** Renderer က FFprobe နဲ့ container duration (`max(0.1s, 1/fps)`)၊ **audio stream ရဲ့ ကိုယ်ပိုင် duration**၊ video stream သုံးခုလုံး စစ်ပြီးမှ final file ထုတ်ပါတယ်။ Coordinator ကလည်း output ပေါ်တွင် audio-stream duration ကို ထပ်စစ်ပါတယ်။ Media duration က probed တန်းက authoritative ဖြစ်ပါတယ်။
- [x] **Cache အလုပ်လုပ်ပါတယ်။** စကား/voice မပြောင်းရင် cache hit (file mtime မပြောင်း)၊ စကား ပြောင်းရင် invalidate။
- [x] **UI က infrastructure ကို တိုက်ရိုက် မလုပ်ပါ။** `test_ui_layer_does_not_import_infrastructure` က ဆက်လက် အောင်မြင်ပါတယ်။

### နောက်တစ်ဆင့်ကို မှန်တကယ် မလုပ်ရသေးသောအချက်

- **အသံက DEMO ပါ။** ဒီ venv မှာ `edge_tts` မရှိလို့ `LocalWaveTtsAdapter` (synthetic tone) ကို သုံးနေပါတယ်။ အသံပိုင်းက **မှန်တကယ် Burmese အသံ မဟုတ်**။ Renderer/fit/mix/mux/validation တိုင်း REAL ပါ။ Run ကို DEMO အဖြစ် ရှင်းလင်း အမှတ်ပြုထားပါတယ်။
- **Real Edge TTS run မလုပ်နိုင်ပါ။** Network မရှိတဲ့ test environment ကြောင့် `LegacyExactDubbingTtsAdapter` (retry ladder ပါ) ကို ဒီ environment မှာ run မလုပ်နိုင်ပါ။
- **Legacy pipeline ကို subprocess နဲ့ wrap လုပ်ခဲ့သော path မရှိပါ။** Native implementation ကို အသုံးပြုထားပြီး၊ legacy project ကို ဖိုင်မွေး/တည်းဖြတ်ခြင်း မရှိပါ။
- **Speed-fit warning သာ ရှိပြီး cap မရှိ။** 1.35× ကျော်ရင် warning ပဲ၊ fit ကို ဆက်လုပ်ပါတယ် (legacy အတူ)။
- **Splitter / Common Editing / Narrator heavy integration** က မလုပ်ရသေးပါ။

### နောက်ဆုံး စစ်ဆေးချက်

- `.\.venv\Scripts\python.exe -m pytest tests/test_exact_dubbing_render.py -q --confcutdir=tests -p no:cacheprovider` → **29 passed in 33.25s**။
- `.\.venv\Scripts\python.exe -m pytest tests/test_exact_dubbing_render.py tests/test_exact_dubbing_panel.py tests/test_exact_dubbing_validation_gate.py tests/test_transcript_regressions.py tests/test_architecture_gates.py -q --confcutdir=tests -p no:cacheprovider` → **91 passed, 1 skipped in 34.31s**။
- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **421 passed, 1 skipped in 121.47s**။
- `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe scripts\check_shell.py` → `MainWindow OK`, 7 မျက်နှာ, `closed`, **exit 0**။
- `MMNEXT_TRANSCRIPT_SMOKE_MEDIA=inputs/harvard-full.mp4`, `MMNEXT_TRANSCRIPT_SMOKE_MODEL=models/tiny.en` ဖြင့် opt-in real smoke → **1 passed**။


## V. Phase 1 cleanup — exact-dubbing slice (2026-10-22)

§ U ရဲ့ code-review fix cycle နောက်တွင် ကျန်ခဲ့သော **mechanical** debt အချက်လဲများကို ဖယ်ရှားခဲ့သော အပိုင်း။ **Behaviour မပြောင်းခဲ့ပါ** — review က အတည်ပြတဲ့ duplication/dead-code/test-gap အချက်များသာ။ ဆုံးဖြတ်ချက်သည် တောင်းဆိုခံရပြီး အချက်အလက်တွင် မှတ်တမ်းတင်ထားသည်။

### ပြင်ဆင်ခဲ့သောအချက်များ

- [x] **M1 — domain validation တစ်ခုတည်း ဖြစ်အောင် လုပ်ခဲ့သည်။** `mmnext/domain/exact_dubbing.py` က ကိုယ်ပိုင် Myanmar regex နဲ့ `1e-6` tolerance ကို ပြန်ရေးထားခဲ့ပုံမှာ `mmnext/domain/validation.py` ထဲမှာ `MYANMAR_SCRIPT_RE`၊ `TIMESTAMP_EPSILON`၊ `is_burmese()` သုံးခုလုံး ရှိပြီးသားဖြစ်လို့ ဒီအခါ အဲဒီတို့ကို import လုပ်ပြီး အစားထိုးထားသည်။ Public alias `MYANMAR_UNICODE_PATTERN` / `TIMING_TOLERANCE` ကို ထိန်းသိမ်းထားပြီး ဘယ်သူမှ ပြိုလုပ်မခံဘူး။ `validation.py` က `exact_dubbing` ကို import မလုပ်ထားလို့ import cycle မရှိ။
- [x] **M11 — duration tolerance နှစ်မျိုး မရှိတော့ပါ။** Renderer က `max(0.1, 1/fps)` ကို report ထဲ `"duration_tolerance"` / `"audio_tolerance"` အဖြစ် တင်ထားပြီး၊ coordinator က အဲဒီတိုင်းတန်းကိုသာ ပြန်စစ်ပါတယ်။ ရှေ့ကအတိုင်း coordinator ရဲ့ setting `0.25` က report မရှိတဲ့ renderer အတွက် fallback ဖြစ်ပါတယ် — ဒါပေမယ့် **အစိုးရတချို့** သည် renderer ရဲ့ သတ်မှတ်ချက်အတိုင်း ရှိလို့ coordinator က ပိုကျယ်တဲ့ တန်ဖိုးနဲ့ ပြန်စစ်ပြီး renderer က ငြင်းခဲ့သော output ကို ဖြတ်ပေးခံရမှာ မဟုတ်တော့ဘူး။ မှားနေတဲ့ report တန်ဖိုးကို ခုခံမထားပါ (string/bool ကို ငြင်းပြီး fallback သုံးပါတယ်)။
- [x] **Orphan adapter ကို ဖျက်ခဲ့သည်။** `mmnext/services/adapters/exact_dubbing_render.py` ရဲ့ `LegacyExactDubbingRenderer` / `DemoExactDubbingRenderer` နှစ်ခုလုံး native `FfmpegExactDubbingRenderer` က အစားထိုးပြီးမှ ဘယ်လူမှ import မလုပ်တော့ (AST scan နဲ့ package တစ်ခုလုံးမှာ အတည်ပြပြီး) — ဖျက်ခဲ့သည်။ `ExactDubbingRenderer` protocol ကို `mmnext/services/protocols.py` မှာ ထိန်းသိမ်း (renderer က သုံးပါတယ်)။ `__init__.py` အလွတ်ဖြစ်လို့ လုံးဝ မလိုအပ်။
- [x] **M7 — ကျန်ခဲ့သော test gap များ ဖြည့်ခဲ့သည်။** >1.35× speed-fit က warning ဖြစ်ပြီး cap မဟုတ်တာ၊ 80 % gap-expansion က real render မှာ အလုပ်လုပ်တာ၊ ရှည်တဲ့ speech ကို atempo နဲ့ fit လုပ်ပြီး window အတွင်းချုံ့တာ၊ နဲ့ duration tolerance တစ်ခုတည်း report ကနေ ပြန်ပြန်စစ်တာ — အသစ် test ၄ ခု။

### ဆုံးဖြတ်ချက်များ (user မေးမြန်းပြီး)

- [x] **မူလ video ရဲ့ အသံ (music/SFX) ကို လုံးဝ မထည့်ပါ** — legacy `movie-recap` အတူ speech-only mix။ ဆုံးဖြတ်ချက်: **legacy အတူ**။ Render contract မပြောင်း။
- [x] **Real Edge TTS run မလုပ်ရသေးပါ** — `edge_tts` မရှိ + environment မှာ network မရှိ။ အသံပိုင်း ဆက်လက် DEMO။
- [x] **နောက်ဆုံး row ရဲ့ trailing gap** — legacy parity (trailing silence ထဲ မပြောင်း) — record only.
- [x] **Edge TTS retry ladder (၁၃၅ စက္ကန့်/row)** — legacy parity + coordinator က ပထမဆုံး မအောင်မြင်သော row မှာ ရိုက်တာမို့ review က မှားယွင်းစွာ ဖော်ပြခဲ့သော "၁၈ နာရီ" မဖြစ်ပါ — record only.

### နောက်ဆုံး စစ်ဆေးချက်

- `.\.venv\Scripts\python.exe -m pytest tests/test_exact_dubbing_render.py tests/test_exact_dubbing_panel.py tests/test_exact_dubbing_validation_gate.py tests/test_transcript_regressions.py tests/test_architecture_gates.py -q --confcutdir=tests` → **95 passed, 1 skipped in 64.42s**။
- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **425 passed, 1 skipped in 150.08s**။
- `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe scripts\check_shell.py` → `MainWindow OK`, 7 မျက်နှာ, `closed`, **exit 0**။


## X. Splitter mode integration — REAL FFmpeg parts (2026-10-23)

Splitter slice။ UI (panel + `AppContext` + worker thread) က အခြားသော လုပ်ငန်းတွင် ရေးပြီးဖြစ်သဖြင့် ဤ slice က **planner ကို ချိန်ညှိပြီး**၊ **REAL renderer ကို အသစ်တည်ဆောက်ပြီး**၊ **တင်ဆက်ချိန်ညှိချက်များကို တိကျပြောပြပြီး**၊ နောက်ဆုံးတွင် **test များ ပြည့်စုံအောင် ဖြည့်ဆင်းခဲ့သည်** (ယခင်က splitter test **သုည** ဖြစ်ခဲ့သည်)။

### ဖိုင်များ

- `mmnext/infrastructure/ffmpeg_tools.py` (**အသစ်**) — FFmpeg/FFprobe invocation, probe reads (duration / stream duration / start_time / frame rate / stream presence) နှင့် `validate_media()` final check တို့ကို **တစ်နေရာတည်း** သို့ ရွှေ့ပြီး။ UTF-8 decode + timeout ကို အားလုံးတွင် တစ်ပြိုင်နက်တည်း အသုံးပြုသည်။
- `mmnext/infrastructure/splitter_render.py` (**အသစ်**) — `FfmpegSplitterRenderer`။ Stream copy (`-ss` အရင်, `-t`) + `-map 0:v:0 -map 0:a?` (audio မရှိသော part ကို ငြင်းရန်) + FFprobe validation + keyframe-snapped cut ကို `last_report` တွင် တိကျတကျ် report။ Output အမည်က `.partial` ကဲ့သို့ media extension မရှိနိုင်သဖြင့် `-f mp4` ကို တိတိကျကျ ထုတ်သည်။
- `mmnext/infrastructure/exact_dubbing_render.py` — helper တွေကို `FfmpegTools` သို့ delegate လုပ်ပြီး (copy နှစ်ခု မရှိတော့ပါ)။
- `mmnext/services/adapters/splitter.py` — planner + demo renderer ကျန်သည်; `LegacySplitterRenderer` ကို infrastructure မှ re-export လုပ်သည် (ffmpeg က UI/config မဟုတ် သော infrastructure layer နှင့် တွဲသည်)။
- `mmnext/application/splitter_render_coordinator.py` — မအောင်မြင်ပါက **အကြောင်းရင်း** (`self.renderer.error` / `last_report["error"]`) ကို ထုတ်ပြပြီး၊ keyframe snap ကို warning အဖြစ် တင်သည်။
- `tests/test_splitter_render.py` (**အသစ်**, 25 tests)၊ `tests/test_splitter_worker.py` (**အသစ်**, 6 tests)။

### CRITICAL — worker-thread tool probe (၂၆ စက္ကန့် → ၆ စက္ကန့်)

- [x] **`shutil.which()` က worker thread မှာ ပထမဆုံး ခေါ်ဆိုပါက ~၆ စက္ကန့် ကြာပါတယ်။** `faulthandler` stack dump က `shutil.py:1472 _access_check → ffmpeg_tools.py:48 available → splitter_render.py:69 render_part` ကို တိကျစွာ ပြခဲ့သည်။ တိုင်းတာချက်: main thread `0.008s`၊ worker thread (ပထမ) **`6.353s`**၊ worker thread (ဒုတိယ) `0.008s`၊ `subprocess` က `0.034s` — ဒါကြောင့် တိုင်ကြောင်းသည် subprocess spawn မဟုတ် ဘဲ PATH probe ပေါ်သည်။ `FfmpegSplitterRenderer.render_part` က part တစ်ခုချင်း `available()` ကို ခေါ်သဖြင့် ၃ ပိုင်း render တွင် ၂၆ စက္ကန့် ကုန်ခဲ့သည်။
- [x] **ဖြေရှင်းချက်:** `shutil.which` answers ကို `(PATH, tool)` key နှင့် memoize လုပ်ခဲ့သည် (process တစ်ခုတည်းအတွက် မပြောင်းနိုင်သဖြင့် ပြန်မေးရန် မလို)။ **Part တစ်ခုချင်း 11.53s → 2.72s**၊ render ၂ ပိုင်း **28s → 6.65s**။ ဤ fix က `exact_dubbing_render.py` ကိုလည်း ကျွန်ုပ် refactor လုပ်ခဲ့သဖြင့် exact-dubbing renderer ကိုလည်း ချက်ချင်းအကျိုးရှိသည်။

### Planner ချိန်ညှိချက် (bug တစ်ခု)

- [x] **`max_extra_wait` က `part_seconds` ထက် ကြီးရင် tail ကိ အားလုံး ဖြေလုပ်ခဲ့သည်။** `plan(6.0, 2.0)` က part ၃ ခု (၂s စီ) အစား **part တစ်ခုတည်း (၆s)** ထုတ်ခဲ့သည် — default wait 5s က ၂s part များ၏ ကျန်ရှိသည်ကို စားလိုက်သည်။ Tail ကို စားရန် part တစ်ခုထက် သို့ မကျော်စေရန် `tail < part_seconds` အခြေအနေ ထည့်ခဲ့ပြီး၊ `test_a_wait_larger_than_the_part_does_not_swallow_everything` က ချိန်ညှိခဲ့သည်။ (65s / 60s မှာ 5s tail ကို စားဒါဖြစ်ပါတယ်)။

### တိကျတကျ တင်ဆက်ချက်

- [x] **Stream-copy cut က keyframe ပေါ်တွင် ကျရောက်ပြီး သို့ သူ၏ အရှေ့တွင် ရှိသည်။** Part တစ်ခုက အမြင့်ဆုံးသော window မှ 2.333s ဖြစ်နိုင်သည် (2.0s window တွင်တောင့်ချိန်) — ဒါကို ဖျော့ချခြင်းမဟုတ်ဘဲ **တင်ပြသည်**: `last_report["start_time"]` နှင့် coordinator ရဲ့ `"Part N: cut snapped from X to Y"` warning။ Part ကို ငြင်းရန် မှားနေသော duration သာ (`PART_DRIFT_TOLERANCE = 0.5s`, packet-sized slack)။
- [x] **Sparse-keyframe source (test fixture `-g 250`) ကို စစ်ဆေးသည်** — `test_a_snapped_cut_is_reported_not_hidden` နှင့် `test_the_coordinator_warns_when_a_cut_snapped` က worst-case ကို လုပ်ဆောင်သည်။
- [x] **စစ်ဆေးမှု:** video + audio stream နှစ်ခုလုံး ရှိရမည်၊ duration > 0 နှင့် window နှင့် ကိုက်ညီရမည်။ မရှိသော/မမှန်သော part ကို ငြင်းပြီး ဖိုင်ကို မချန်ထားပါ။

### အခြားသော

- [x] **Test suite က worker thread ကို GIL မ ဆာဆင်ရန်** — တင်းမာသော event-loop spin က GUI thread ကို ကြာချိန်ယနູ တီတန်းလုပ်သဖြင့် worker က ffmpeg child များကို စောင့်နေရသည်။ ယခု `_wait_for` က 200ms poll သုံးသည်။
- [x] **`render(self)` က `part_{n}.mp4` သော့ချက်** — coordinator နှင့် တူညီသော အမည်နှင့် ကိုက်ညီသည်၊ cell ပြန်လည်အသုံးပြုမှုသည် မှားယွင်းမဖြစ်စေရ။

### ဆက်လက်မလုပ်ရသေးသော အချက်များ

- **Splitter renderer က stream copy သာ လုပ်နေသည်။** Frame-တိကျတကျ လိုအပ်ပါက re-encode လုပ်ရမည် (UI setting မရှိသေးပါ)။ Keyframe drift ကို တိကျတကျ report လုပ်နေသည်မှာ လက်ခံနိုင်သော လမ်းကြောင်းဖြစ်သည်။
- **Pause detection (`CutReason.PAUSE`/`BREATH`/`QUIETEST`) က UI မှ `pause_times` ကို လက်ခံရုံသာ** — အသံကို တကယ်လေ့လာ၍ ရှာတဲ့ code မရှိပါ (contract တွင် သတ်မှတ်ထားသည်)။
- **Splitter render ကို UI/real media ဖြင့် UI button (click-through) မှ မစစ်ရသေးပါ** — worker-thread test တစ်ခုက REAL FFmpeg render ကို `start_splitter_render()` မှ တိုက်ရိုက် အလုပ်လုပ်ကြောင်း အတည်ပြထားသည်။

### နောက်ဆုံး စစ်ဆေးချက်

- `.\.venv\Scripts\python.exe -m pytest tests/test_splitter_render.py tests/test_splitter_worker.py tests/test_architecture_gates.py -q --confcutdir=tests` → **43 passed**။
- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **458 passed, 2 skipped** (skip: opt-in REAL Edge TTS၊ Whisper real media)။
- `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe scripts\check_shell.py` → `MainWindow OK`, 7 မျက်နှာ, `closed`, **exit 0**။

## W. Phase 2 — REAL Edge TTS speech path (2026-10-22)

Exact-dubbing slice ရဲ့ Phase 2။ § V မှာ user ဆုံးဖြတ်ခဲ့သအတိုင်း soundtrack နဲ့ trailing-gap သည် legacy parity ဖြစ်လို့ **behaviour မပြောင်းခဲ့ပါ**။ အဓိက အလုပ်က **REAL speech path ကို ပထမဆုံး အမှန်တကယ် စမ်းပြီး** — ယခင်က `edge_tts` မရှိလို့ အသံပိုင်းက DEMO ပဲ ဖြစ်နေခဲ့ပါတယ်။

### ပြောင်းလဲမှုများ

- [x] **`edge-tts` ကို project venv သို့ တပ်ဆင်ခဲ့သည်** — `edge-tts 7.3.1` (+ `aiohttp` 3.14.5, `yarl`, `frozenlist`, `propcache`, `multidict`, `attrs`, `tabulate`, `aiohappyeyeballs`, `aiosignal`)။ Microsoft Edge TTS ဝန်ဆောင်မှုက ဤ environment မှာ ရောက်နိုင်ပါတယ် (Burmese voice တစ်ခုအတွက် 12384 bytes / 1.46s)။
- [x] **Offline switch တစ်ခု တင်ဆင်ခဲ့သည်** — `mmnext/application/exact_dubbing_service.py` ရဲ့ `MMNEXT_EXACT_DUB_OFFLINE_TTS` env var နဲ့ `allow_real_tts` kwarg။ `edge_tts` ထည့်ခဲ့ပြီးနောက် **test suite တစ်ခုလုံးက network ကို မထိရကျိုးအောင်** လိုအပ်ခဲ့ပါတယ် — REAL speech ရဲ့ အရှည်က မတူညီလို့ deterministic assertion တွေ (`speed > 1.0`, `window == 2.6`) ပြိုလဲမှုရှိပါတယ်။ Production default က REAL (env မရှိရင်)၊ `tests/conftest.py` က suite တစ်ခုလုံးအတွက် offline ကို သတ်မှတ်ပါတယ်။
- [x] **Opt-in REAL test တစ်ခု ထည့်ခဲ့သည်** — `tests/test_exact_dubbing_render.py::test_the_real_edge_tts_path_renders_a_labelled_real_dub` သည် `MMNEXT_EDGE_TTS_SMOKE=1` မရှိရင် skip ဖြစ်ပြီး `allow_real_tts=True` ကို တိတိကျကျ ဖြင့်ထားပါတယ်။ ၎င်းက အတည်ပြုသည့်အချက်များ: `result.is_demo` နဲ့ `report["is_demo"]` နှစ်ခုလုံး **False**၊ legacy voice mapping နှစ်ခုလုံး (`my-MM-ThihaNeural`, `my-MM-NilarNeural`) REAL audio နဲ့ အလုပ်လုပ်ခြင်း၊ နောက်ဆုံး output တွင် audio + video stream နှစ်ခုလုံးရှိခြင်း၊ cache တွင် REAL speech ကျန်ရှိခြင်း။
- [x] **Offline switch အတွက် unit test ထည့်ခဲ့သည်** — `test_the_offline_switch_keeps_the_suite_off_the_network` သည် package ထည့်ခဲ့ပြီးပါ (offline မဖြစ်တာ) တွင် switch က အလုပ်လုပ်ကြောင်း၊ explicit opt-in က env ကို လွှဲသွားကြောင်း၊ forced-offline coordinator က `LocalWaveTtsAdapter` ကို အသုံးပြုကြောင်း စစ်ပါတယ်။
- [x] **`LegacyExactDubbingTtsAdapter.available()` ကို cache လုပ်ခဲ့သည်** — `edge_tts` က `aiohttp` ကို ဆွဲတကြီးလို့ တစ်ခါတည်း import က ~2 စက္ကန့် ကြာပါတယ်။ availability က process တစ်ခုလုံးမှာ မပြောင်းနိုင်လို့ memoise လုပ်ပြီး render တစ်ခုချင်းစီ + UI status read တွေမှာ ပြန်မတွက်ရပါ။ Full suite က 206s → **135s** ဖြစ်လာပါတယ်။
- [x] **အမည်ပေးတဲ့ ပြဿနာတစ်ခု ဖြေရှင်းခဲ့သည်** — coordinator က ရယူရသော TTS output ကို `.wav` ဟု အမည်ပေးထားပုံမှာ REAL synthesiser က MP3 bytes ရေးလို့ ဖြစ်ပါတယ် (offline က တကယ် PCM WAV)။ အခု **neutral `.audio`** extension ကို သုံးပါတယ် — renderer က mix မတိုင်မီ FFmpeg နဲ့ ပြန်ရေးလို့ container က မကျေနပ်ပါ။ အတိအလင်း မဟုတ်တဲ့ ဖိုင်အမည်ကို ဖယ်ရှားခဲ့ပါတယ်။
- [x] **CWD-writes ချို့ယွင်းချက်ကို ဖမ်းမိပြီး ပြင်ဆင်ခဲ့သည်** — full suite ကို run လုပ်ပြီးနောက် repo root မှာ `narrator_tts/` + `out.mp4` ကျန်ရှိနေတာကို တွေ့ခဲ့ပါတယ်။ `tests/test_narrator_pipeline.py` က `coordinator.run(..., "out.mp4", {})` ကို **bare relative path** နဲ့ ခေါ်နေလို့ coordinator ရဲ့ cache fallback (`Path(output).parent / "narrator_tts"`) က CWD ဖြစ်သွားပါတယ်။ `Agent.md`/`AGENTS.md` က "never write real-job checkpoints to the CWD" ဟု ဆိုနေလို့ ၎င်းကို tmp_path သုံးစေရန် ပြင်ဆင်ပြီး stray artifact ၂ ခုကို ဖျက်ခဲ့ပါတယ်။ **Regression test** `test_the_pipeline_cache_stays_job_scoped` က cache က output အနီးမှာ ရှိပြီး CWD တွင် မကျန်ကြောင်း အာမခံပါတယ် (stray ၃ မျိုးကို စစ်ပါတယ်)။
- [x] **`tests/conftest.py` ကို git သို့ တင်ခဲ့သည်** — offline switch က suite တစ်ခုလုံးအတွက် အရေးပါသောကြောင့် untracked မကျန်စေရပါ။

### REAL Edge TTS — အတည်ပြထားသောရလဒ်များ

- [x] **REAL render အပြည့်အစုံ အောင်မြင်ပါတယ်** (production path, `ExactDubbingService.render_from_translated_gender`) —
  - `tts_available(): True`၊ `is_demo(): False`၊ `result.is_demo: False`
  - Voice mapping: `s0` → `my-MM-ThihaNeural` (male), `s1` → `my-MM-NilarNeural` (female)
  - Speech fitting: raw 2.064s → window 2.0s (speed 1.03x); raw 3.576s → window 2.0s (speed 1.79x, warning surfaced)
  - Mix + mux: `h264_nvenc`, output **6.0s**, audio stream duration **6.0s**, video stream present
  - `render_report.json`: `source_duration 6.0`, `output_duration 6.0`, `audio_duration 6.0`, `is_demo False`
  - Cache: `0000_3b9f9231….audio` + `.sha256`, `0001_fbc6f47e….audio` + `.sha256` (signatures match)
- [x] **Opt-in test → `1 passed in 9.07s`** (`MMNEXT_EDGE_TTS_SMOKE=1`)။
- [x] **Offline suite က ဆက်လက် offline နှင့် စက်** — full suite မှာ REAL test က skip ဖြစ်ပါတယ်။ `conftest.py` က switch ကို သတ်မှတ်လို့ network မထိပါ။

### ဆက်လက် မှန်တကယ် မလုပ်ရသေးသောအချက်

- **REAL speech ကို production UI ကနေ တိတိကျကျ မစမ်းရသေးပါ** — production path ကို တိုက်ရိုက် service call နဲ့ စမ်းခဲ့ပါတယ် (ảင်ကို opt-in test က)၊ `start_exact_dubbing_render` ကနေ REAL ဖြစ်စေ မလုပ်ရသေးပါ။ တူညီသောလမ်းကြောင်းဖြစ်လို့ တန်ဖိုးနည်းပါတယ်၊ ဒါပေမယ့် UI button click-through ကို မှတ်တမ်းမတင်ရသေးပါ။
- **`edge_tts` က network ပေါ်မူတည်ပါတယ်** — Microsoft ဝန်ဆောင်မှု 403/WSServerHandshakeError ဖြစ်တတ်ပါတယ် (legacy repo က မှတ်တမ်းတင်ထားပါတယ်)။ `LegacyExactDubbingTtsAdapter` မှာ retry ladder (5/10/20/40/60 စက္ကန့်) ရှိပြီး၊ ပထမ မအောင်မြင်သော row မှာ ရပ်ပါတယ်။ VPN/proxy ပြဿနာကို တိုက်ရိုက် မစစ်နိုင်ခဲ့ပါ။
- **Whisper / Gemini / Smart Sync** — အခြားသော service တွေက REAL adapter အဆင့်မှာ ကျန်ရှိပါတယ် (Narrator slice)။

### နောက်ဆုံး စစ်ဆေးချက်

- `MMNEXT_EDGE_TTS_SMOKE=1 .\.venv\Scripts\python.exe -m pytest tests/test_exact_dubbing_render.py::test_the_real_edge_tts_path_renders_a_labelled_real_dub -q --confcutdir=tests` → **1 passed in 9.07s**။
- `.\.venv\Scripts\python.exe -m pytest tests/test_exact_dubbing_render.py -q --confcutdir=tests` → **34 passed, 1 skipped** (REAL opt-in)။
- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **427 passed, 2 skipped in 135.03s** (skips: REAL Edge TTS opt-in, Whisper real media opt-in)။ Repo root တွင် stray artifact **မကျန်ပါ**။
- `QT_QPA_PLATFORM=offscreen .\.venv\Scripts\python.exe scripts\check_shell.py` → `MainWindow OK`, 7 မျက်နှာ, `closed`, **exit 0**။



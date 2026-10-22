# MMNext Movie Recap Pro — Todo Plan

## Product strategy

Build the product in vertical milestones. The first milestone is UI-first and must be usable with demo data. Real media services are connected only after the UI contract, domain models, and job state model are stable.

## Current verified status — 2026-10-21

The project is **not complete**. The PySide6 shell, separate mode/domain contracts, job/checkpoint repository components, and local Whisper transcript slice exist. Strict real-media and live-UI transcript acceptance is documented in `checklist.md` § N.

> **Latest superseding cycle — UI→infrastructure isolation / code-review debt
> (2026-10-21, same day).** The paragraph below is dated history. The current
> source-verified state for this cleanup is recorded in:
> `checklist.md` § S. The UI no longer imports `infrastructure` directly, and
> the previous private repository path calls were replaced by public
> `JobService`/`JobRepository` methods. Focused/full smoke verification:
> `checklist.md` § S runs a clean full suite of **391 passed, 1 skipped**.
>
> **Superseded again by the Exact Dubbing slice (2026-10-22).**
> `checklist.md` § T resolves the strict real-media Whisper acceptance;
> § U records the Exact Dubbing TTS/render/cache and final validation;
> § V records the Phase 1 cleanup of the remaining review debt (domain
> validation dedup, one duration tolerance, the orphan adapter removal and
> the added coverage); § W proves the **REAL Edge TTS speech path**
> (`edge-tts` installed, real Burmese audio through both legacy voices,
> REAL labelling, and an offline switch that keeps the test suite
> network-free). The current full suite is
> **426 passed, 2 skipped** (the two skips are opt-in network tests).
> A follow-up fix removed a CWD-writes violation in the narrator pipeline
> tests (a bare relative output path put the speech cache in the repository
> root) and added a regression guard for it; the current suite is
> **427 passed, 2 skipped**.

Fresh verification for this documentation update: `pytest tests -q --confcutdir=tests -p no:cacheprovider` with the approved local media/model fixture and project-local FFmpeg tools enabled: **291 passed in 63.32s**. Focused saved-transcript tests: `pytest tests/test_transcript_open.py -q --confcutdir=tests -p no:cacheprovider` → **6 passed in 0.27s**. This does not establish full product or clean-machine readiness.

> **Superseding audit — later the same day, after the transcript reopen / canonical
> fingerprint fix cycle.** The paragraph above is kept as dated history. The
> current, source-verified state is recorded in
> **§ Current verified status — canonical fingerprint fix cycle** below, and
> the counts below supersede "291 passed" wherever they disagree.
>
> **Superseded again by § Current verified status — reopen hardening cycle**
> (further down this file), which fixes every reopen defect listed in the
> canonical fingerprint fix cycle, records the latest counts
> (**364 passed, 1 skipped**), and lists the defects found by the follow-up
> code-review cycle. Read that section first.
>
> What changed: the repository/adapter fingerprint divergence is fixed by a
> single canonical algorithm in `mmnext/domain/fingerprint.py`; the jobs root
> **is** configured in normal startup; completed REAL transcript jobs **are**
> now discoverable; and the reopen path **does** compare the saved fingerprint.
> What did **not** change: the reopen path is still not end-to-end complete —
> the artifact JSON is still read on the GUI thread, the reopen fingerprint
> comparison is still computed without the artifact's settings (so a real
> artifact is currently rejected), artifact mode is still not compared, and
> legacy artifacts are still not rejected explicitly. See
> `checklist.md` § P for the per-item truth table.

The Jobs screen and `AppContext.open_transcript_from_job()` contain an explicit open path, but it is **not yet a complete restart-to-Workspace flow**: normal `MainWindow` construction does not pass a persistent jobs directory, the transcript adapter writes transcript/checkpoint artifacts but does not create completed Job metadata, and the saved transcript fingerprint is not checked when reopening. Artifact JSON is also read synchronously from the UI action. Treat this as partially implemented, not end-to-end complete.

> **Correction to the paragraph above (canonical fingerprint fix cycle).**
> Three of its four claims are now stale and are superseded by
> **§ Current verified status — canonical fingerprint fix cycle**:
> the jobs root **is** configured in normal startup (`AppContext` resolves it
> itself), a COMPLETE REAL Job record **is** persisted after a successful
> transcript, and the reopen path **does** compare the saved fingerprint.
> The claims that still hold: the restart-to-Workspace flow is not complete,
> and the artifact JSON is still read synchronously on the GUI thread.

### Highest-priority next work: make persisted transcript reopening/recovery real end to end

- [x] First obtain an independent, read-only NVIDIA Nemotron review of the current Step-5 transcript-reopen code using `outputs/nemotron-review-prompt-step5-transcript-reopen.md`; treat reported claims as unverified until checked against source/tests.
  - Done. Verdict: **REJECT** — 16 findings, 7 critical. Every finding was
  re-verified against source and by running the code, and the fix cycle that
  followed is recorded below.
- [x] Configure and document one persistent, user-writable jobs root in normal application startup; keep demo mode explicit.
  - Done. `AppContext` resolves `$MMNEXT_JOBS_DIR`, else `~/.mmnext/jobs`, and
  always constructs the `JobRepository`. Demo and REAL stay separated by
  `Job.is_demo`.
- [ ] Persist a versioned REAL transcript Job record, including COMPLETE state and the committed artifact location, only after transcript validation and atomic artifact commit succeed.
  - Largely done in the UI layer; `Job.fingerprint` and `Job.artifact_path`
    now round-trip through the metadata.
- [ ] Make repository-backed Jobs listing include eligible completed REAL transcript jobs as well as recoverable incomplete jobs; opening remains explicit and must never auto-resume.
  - **Done.** Discovery (`scan()["completed_real"]`, `list_completed_real()`) plus
    the Jobs screen wiring: the **Open transcript** action is offered for a
    completed REAL job only and routes through `start_reopen_transcript()`.
    No auto-resume.
- [ ] Harden reopen validation: source identity and fingerprint, mode, job/artifact schema, completion state, row uniqueness, and timing bounds. Reject failures without demo fallback or source-row mutation.
  - **Done.** Source identity (+ a clear "media is gone" message), fingerprint
    re-derived from the artefact's own settings, artefact `mode` compared
    against the job mode, legacy artefacts refused explicitly, artefact path
    containment checked, job/artifact schema, completion state, row
    uniqueness and timing bounds all enforced. No demo fallback, no source-row
    mutation.
- [ ] Move artifact reading/validation off the GUI thread and bind results only if the selected job/source is still current.
  - **Done.** The artefact is read and validated on a worker thread
    (`prepare_transcript_from_job` touches no project state) and applied in a
    GUI-thread slot. A `_reopen_token` guard drops a result whose request is
    no longer current.
- [ ] Add UI/integration tests for normal startup, completed-job discovery, explicit open, corrupt/missing/incompatible artifacts, source/fingerprint/mode mismatch, no demo fallback, off-GUI-thread loading, and Exact Dubbing invariants.
  - **Done.** `tests/test_transcript_open.py` (14) and the new
    `tests/test_transcript_reopen_thread.py` (6) cover every listed case,
    including a reopen driven by a real adapter-written artefact.
- [ ] Mark this slice complete only after a fresh full suite, the strict transcript acceptance, and a real Jobs→Workspace restart integration check all succeed.
  - **Now done** (2026-10-22). Fresh full suite **392 passed, 1 skipped** and the
    offscreen shell smoke is clean. A follow-up code-review cycle fixed five
    defects the first implementation introduced (edit loss during a load, an
    unsynced mode, crashes on malformed artefacts, an order-dependent result
    binding, and a missing Jobs→Workspace navigation) — see
    "Code-review cycle — findings and fixes" below. The latest regression
    coverage also verifies that a successful REAL run writes completed Job
    metadata, registers the job live, and is rediscovered by a fresh
    `AppContext`.
  - **Strict real-media Whisper acceptance: PASS.** The earlier failure came from
    pointing the acceptance at the *clipped* fixture
    `.work/transcript-acceptance/inputs/osr-harvard-12s.mp4` — an artificial
    12-second cut of an 18.356s recording, which truncates the last utterance
    so Whisper's final segment legitimately ends past the clip boundary. The
    canonical runner `.work/transcript-acceptance/boundary_acceptance.py` now
    passes with **zero tolerance**: `status: PASS`, `clipped_rejection: PASS`
    (the strict rejection of the clipped source is still enforced),
    `full_source: PASS` (6 rows, last end 17.600s ≤ 18.357s, inference 2.051s)
    and `real_ui: PASS` (offscreen REAL button → QThread → real FFmpeg/Whisper →
    6 rows, REAL badge, progress 100). No source row was clamped, dropped,
    merged or retimed; see `checklist.md` § T.
  - **Real Jobs→Workspace restart: PASS (automated).** A successful REAL run
    writes a versioned COMPLETE Job record with the committed artefact path and
    fingerprint, a fresh `AppContext` rediscovers it from
    `scan()["completed_real"]`, and the explicit open path reopens the artefact
    on a worker thread with strict validation.

The persistence/recovery slice now has a truthful end-to-end acceptance path
(fresh full suite, strict real-media Whisper acceptance with zero tolerance,
and an automated Jobs→Workspace restart), so the gate on starting translation,
TTS and rendering is **open**. The Exact Dubbing TTS/render/cache slice and
its final duration/audio-stream validation are implemented on top of
`translated_gender.json` — see `checklist.md` § U. Next priority: the real
Edge TTS speech run (the audio is still DEMO because `edge_tts` is not
installed and the environment has no network), then the Narrator vertical
slice, then Splitter, Common Editing, and release hardening.

## Current verified status — narrator pipeline slice

This section supersedes the "Narrator heavy integration is not started" claim in
§ Current verified status — reopen hardening cycle. It records what was
**verified by running the code**.

### Fresh verification

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **382 passed, 1 skipped in 108.36s**. The one skip is `tests/test_transcript_regressions.py:158`, which needs an approved media fixture and a locally cached Whisper model.
- `.\.venv\Scripts\python.exe -m pytest tests\test_narrator_pipeline.py tests\test_narrator_pipeline_ui.py -q --confcutdir=tests -p no:cacheprovider` → **18 passed in 17.34s**.
- `.\.venv\Scripts\python.exe scripts\check_shell.py` (offscreen) → `MainWindow OK`, 7 screens, `closed`, exit 0.

### What the narrator pipeline slice changed

- **Three service protocols.** `TranslationProvider`, `SpeechSynthesizer` and
  `SmartSyncRenderer` in `mmnext/services/protocols.py`. Translation operates on
  **narrator units** (`NarrationSegment`), not on transcript rows, so the
  narrator contract stays separate from the exact-dubbing contract.
- **Three adapters with honest degradation.**
  `mmnext/services/adapters/narrator_translation.py`,
  `narrator_tts.py`, `narrator_render.py`. Each has a `Legacy*` variant that
  loads the read-only legacy project defensively and a `Demo*` variant for the
  offline suite. A missing legacy entry point yields empty translations / no
  audio / a `False` render — never a fake success.
- **A Qt-free pipeline coordinator.**
  `mmnext/application/narrator_pipeline_coordinator.py` runs
  plan → translate → synthesise → render, reports `ProgressEvent` progress on
  the codebase's 0–100 scale, and stops safely at a stage boundary.
- **The heavy stages never touch the GUI thread.**
  `mmnext/ui/narrator_pipeline_worker.py` runs the coordinator on a
  `QThread`; `test_pipeline_runs_off_the_gui_thread` proves it by comparing
  thread ids.
- **The UI is wired.** `AppContext.start_narrator_pipeline()` /
  `stop_narrator_pipeline()`, `narratorProgress` / `narratorStateChanged`
  signals, and a "Run narrator pipeline (DEMO)" button plus progress bar and
  status line in the narrator panel.
- **Packaging is fixed.** `pyproject.toml` now lists
  `mmnext.infrastructure.repository` and `mmnext.services.adapters`, so a
  non-editable install no longer produces a broken wheel.

### What is still NOT true

- **Every adapter is still DEMO.** The `Legacy*` adapters are implemented but
  not wired into the run, because that needs a Gemini credential, an
  `edge_tts` install, and a real legacy render entry point. The button and the
  status line are labelled DEMO so simulated work is never presented as real.
- **No real video is produced.** `DemoSmartSyncRenderer` writes a placeholder
  file.
- **Reuse detection is incomplete.** `SpeechSynthesizer.cache_key()` is
  computed, but the pipeline does not yet check the cache on disk.
- **Gemini story context, translation batching/checkpointing/audit** are
  unused. `TranslationProvider` accepts `context` and `glossary`, but the
  current adapters ignore them.
- The strict **real-media Whisper acceptance** and a real
  **restart-to-Workspace** check still need an approved media fixture and a
  locally cached Whisper model.

### Next slice (priority order)

1. Narrator heavy integration, part 2: wire the **real** adapters (Gemini
   story context, translation batching with deterministic batch ids and
   checkpoints, Edge TTS with a real cache, the Smart Sync renderer) and add
   segment-level reuse detection and a final output validation step.
2. Exact Dubbing prepare/export, TTS cache, speech fitting, final duration
   and audio-stream validation.
3. Splitter planner, smart-cut/short-tail rules, per-part resume.
4. Common Editing non-destructive timeline, overlays, export validation.
5. Windows packaging, diagnostics, clean-machine and non-ASCII path testing.

Do not claim any narrated feature as production-complete until it has been
exercised with real media, real credentials and real output validation.

## Current verified status — canonical fingerprint fix cycle

This section supersedes the dated "291 passed" figures and the stale
`jobs_dir` claims in the section above wherever the two disagree. It records
what was **actually verified by running the code**, not what is intended.

### Fresh verification

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **342 passed, 1 skipped in 70.89s**. The one skip is `tests/test_transcript_regressions.py:158`, which needs an approved media fixture and a locally cached Whisper model.
- `.\.venv\Scripts\python.exe -m pytest tests\test_fingerprint.py -q --confcutdir=tests -p no:cacheprovider` → **40 passed in 1.61s** (new canonical-fingerprint suite).
- `.\.venv\Scripts\python.exe -m pytest tests\test_job_repository.py tests\test_transcript_regressions.py tests\test_transcript_integration.py tests\test_real_transcript.py -q --confcutdir=tests -p no:cacheprovider` → **70 passed, 1 skipped in 2.73s**.
- `.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider` → **32 passed in 11.17s**.

### What the fix cycle actually changed

- **One canonical fingerprint algorithm.** `mmnext/domain/fingerprint.py` (new) owns
  `canonical_fingerprint(source_path, source_type, mode, settings=None, schema_version=...)`
  and returns `fp2:<sha1hex>`. `JobRepository.compute_fingerprint()` keeps its
  public name and keyword signature and now delegates to it, and
  `WhisperTranscriptAdapter._fingerprint()` delegates to it as well. The two
  algorithms that previously disagreed now produce identical values.
- **Local file identity is real.** The old code only stat'ed the file when
  `source_type == "local"`, but the enum value is `"local_file"`, so size and
  mtime were always `(0, 0.0)`. Source types are now normalised
  (`local`/`local_file`/`file` → `local_file`, `youtube`/`url` → `youtube`),
  and an absent source is hashed with an explicit "absent" marker so it can
  never match a present one.
- **The artifact carries its own fingerprint inputs.** The transcript artifact
  now stores `mode`, `fingerprint`, `fingerprint_settings`
  (`language`/`auto_detect`/`model`/`schema`), `fingerprint_schema_version`, and
  `fingerprint_source_type`, so a re-open can re-derive the same value instead
  of guessing which settings produced it.
- **Completed REAL transcript jobs are discoverable.**
  `JobRepository.scan()` returns `recoverable`, `completed`, `completed_real`,
  and `corrupt`; `list_completed_real(source_path=None)` returns the matching
  `Job` objects. `Job.fingerprint` round-trips through the metadata
  serialisation, and legacy metadata without the key loads as `""`.
- **The jobs root is configured in normal startup.** `AppContext` resolves a
  default jobs directory itself (`$MMNEXT_JOBS_DIR`, else `~/.mmnext/jobs`) and
  always constructs the `JobRepository`, so `MainWindow` constructing
  `AppContext()` with no argument is no longer a blocker. Verified by running
  `AppContext()` with no argument: the repository is present and the scan
  returns all four keys.
- **No-Git review evidence exists.** `.work/review-baselines/transcript-reopen-fixcycle-01/`
  holds the pre-edit byte copies, `manifest.sha256`, `changes.diff`, and
  `changed-files.sha256`.

### What is still NOT true

> **Superseded by § Current verified status — reopen hardening cycle below.**
> Every item in this list was fixed in the reopen hardening cycle. The list is
> kept as dated history.

- **The reopen path currently rejects every real artifact.** The reopen check
  still recomputes the fingerprint without the artifact's settings, so a
  REAL adapter-produced artifact fails with
  `ValueError: Fingerprint mismatch between artifact and current source`
  (verified by running the full save → reopen path against a real adapter
  artifact). The fix is to recompute from `fingerprint_settings` /
  `fingerprint_source_type` / `fingerprint_schema_version`.
- **Artifact mode is not compared.** The artifact now carries `mode`, but the
  reopen path does not check it against the persisted Job mode or the
  workspace mode.
- **Legacy artifacts are not rejected explicitly.** An artifact without the new
  keys, or with a non-`fp2:` fingerprint, is unverifiable and must be
  refused with a clear "legacy artifact — re-transcribe required" message
  instead of being silently accepted.
- **Artifact reading is still synchronous on the GUI thread**, and there is
  still no stale-result guard on the open path.
- **No artifact path containment check** is performed.
- **The narration planning path and the `MMNEXT_JOBS_DIR` override landed in
  the same window** as the sibling's reopen-path rewrite; the narration
  planning work is out of scope for this slice and is not claimed here.

Do not begin translation, TTS, or final video rendering until this
persistence/recovery slice has a truthful end-to-end acceptance path. After
it, prioritize a real Narrator vertical slice, then Exact Dubbing, Splitter,
Common Editing, and release hardening.

## Current verified status — reopen hardening cycle

This section supersedes the "What is still NOT true" list above and the
"Highest-priority next work" checkboxes in the sections above. It records what
was **verified by running the code**.

### Fresh verification

- `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → **364 passed, 1 skipped in 66.76s**. The one skip is `tests/test_transcript_regressions.py:158`, which needs an approved media fixture and a locally cached Whisper model.
- `.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_transcript_reopen_thread.py -q --confcutdir=tests -p no:cacheprovider` → **28 passed in 3.87s**.
- `.\.venv\Scripts\python.exe -m pytest tests\test_architecture_gates.py tests\test_fingerprint.py tests\test_job_repository.py tests\test_narrator_coordinator.py tests\test_narrator_planning_service.py -q --confcutdir=tests -p no:cacheprovider` → **73 passed in 2.09s**.
- `.\.venv\Scripts\python.exe scripts\check_shell.py` (offscreen) → `MainWindow OK`, 7 screens, `closed`, exit 0.

### What the reopen hardening cycle changed

- **The fingerprint is re-derived from the artifact's own inputs.**
  `AppContext.prepare_transcript_from_job()` recomputes
  `canonical_fingerprint(source_path, fingerprint_source_type, mode,
  settings=fingerprint_settings, schema_version=fingerprint_schema_version)`
  and compares it with the artifact's stored value. Recomputing *without*
  the settings hashed a different payload, so every REAL reopen was rejected;
  that defect is gone.
- **Artifact mode is compared.** The artifact's `mode` must equal the
  persisted Job mode, so a narrator artifact can never be opened as exact
  dubbing.
- **Legacy artifacts are refused explicitly.** An artifact without a
  canonical `fp2:` fingerprint, or without `fingerprint_settings` /
  `fingerprint_source_type` / `fingerprint_schema_version`, is rejected with
  "Legacy transcript artifact - re-transcribe required" instead of being
  silently accepted.
- **Artifact path containment is checked.** The resolved artifact path must
  stay inside the repository's source directory for that job, so a job id
  containing path separators cannot place it outside the jobs root.
- **A vanished media file gives a clear message.** The reopen checks
  `is_source_available()` before comparing file identity, so the user sees
  "Source media is unavailable" rather than an OS error.
- **Reading and validation are off the GUI thread; application is on it.**
  `prepare_transcript_from_job()` is pure — it touches no project state — and
  the prepared result is applied by `_apply_prepared_transcript()` in a
  GUI-thread slot. `ReopenTranscriptWorker` now only prepares.
- **A stale result is never bound.** `AppContext._reopen_token` records the
  in-flight `(job_id, source_path)`; a result whose token no longer matches is
  dropped with "Stale reopen result" and nothing is applied.
- **The Jobs screen uses the threaded path.** The **Open transcript** action
  is enabled for a completed REAL job only and calls
  `start_reopen_transcript()` instead of the synchronous
  `open_transcript_from_job()`. The result is reported through the
  `transcriptReopened` signal.
- **Signal connections use bound methods.** The reopen path no longer
  connects a self-capturing `def` closure to a signal.
- **The Jobs→Workspace flow completes.** A successful reopen navigates the
  main window to the Workspace, and the reopened session's mode is synced so
  the matching mode panel is the one that is shown.

### Code-review cycle — findings and fixes

A review pass over the cycle above found five defects in the new code. All
are fixed and each has a regression test.

- **Unsaved edits could be silently discarded.** The dirty check ran only at
  *prepare* time, on the worker thread, but `project.load()` replaces the
  whole session at *apply* time. An edit made while the load was in flight
  was lost without a prompt. The check is now repeated on the GUI thread,
  where the apply happens, and the reopen is refused if edits appeared.
- **The reopened session's mode never reached the workspace.**
  `project.load()` does not notify a mode change, so the workspace kept
  showing the previous mode and the reopened rows were hidden behind the
  wrong panel. The mode is now synced explicitly.
- **Malformed artefacts crashed instead of being refused.** `read_json`
  returns any JSON value, so a non-object document raised `AttributeError`;
  a non-numeric `schema_version`/`duration_s` raised `ValueError`/`TypeError`;
  and `Path.samefile()` raised `OSError` when the recorded source path had
  vanished. All of these are now clean `ValueError` rejections with a
  specific message.
- **The result binding depended on signal delivery order.** The slot
  required `self._reopen_thread` to still be set, but the thread-finished
  slot clears it. A monotonic request id — replaced only by a *new* request —
  now identifies the request, so the binding is order-independent.
- **A successful reopen left the user on the Jobs screen.** The main window
  now navigates to the Workspace, which is what makes the restart-to-workspace
  flow usable.

### What is still NOT true

- The strict **real-media Whisper acceptance** and a real
  **restart-to-Workspace** check still need an approved media fixture and a
  locally cached Whisper model. The reopen is proven against a real
  *adapter-written* artifact, without inference.
- **Narrator heavy integration** (Gemini story context, translation
  batching, Edge TTS, Smart Sync render) is not started. It is the next slice
  in the priority order below.
- `pyproject.toml`'s setuptools `packages` list still omits
  `mmnext.infrastructure.repository` and `mmnext.services.adapters`, so a
  non-editable install produces a broken wheel. Out of scope here; belongs to
  release hardening.

### Next slice (priority order)

1. Narrator heavy integration: Gemini story context, translation batching with
   deterministic batch ids and checkpoints, Edge TTS behind a
   `SpeechSynthesizer` boundary with voice discovery and cache signatures,
   and the Smart Sync renderer — wired as a source → Whisper → plan →
   translation → TTS → Smart Sync chain with stage progress, safe stop at
   stage/segment boundaries and reuse detection.
2. Exact Dubbing prepare/export, TTS cache, speech fitting, final duration
   and audio-stream validation.
   - **Done** (2026-10-22). `translated_gender.json` drives the render:
     `mmnext/domain/exact_dubbing.py` owns the schema and the fitting maths,
     `mmnext/services/adapters/exact_dubbing_tts.py` owns the content-addressed
     TTS cache, `mmnext/infrastructure/exact_dubbing_render.py` fits, mixes,
     muxes and validates with FFmpeg/FFprobe, and
     `mmnext/application/exact_dubbing_service.py` is the UI-facing facade.
     The renderer, the fit, the mix, the mux and the final validation are
     REAL and exercised by `tests/test_exact_dubbing_render.py`; only the
     *speech* is still DEMO because `edge_tts` is not installed. A follow-up
     code-review cycle fixed seven defects in this slice, including a
     **deadlock in the product path** (the first `import numpy` happened on
     the worker thread and could hang the interpreter) and a **truncated
     output that passed validation** (a caller-supplied duration overrode the
     probed media duration). The UI path is now covered by a real end-to-end
     test. See `checklist.md` § U.
3. Splitter planner, smart-cut/short-tail rules, per-part resume.
4. Common Editing non-destructive timeline, overlays, export validation.
5. Windows packaging, diagnostics, clean-machine and non-ASCII path testing.

Do not claim any narrated feature as production-complete until it has been
exercised with real media, real credentials and real output validation.

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
> result is **342 passed, 1 skipped** in the current status section above.
> Evidence is cited in `checklist.md` §§ B, K, N, O, and P.

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
  **342 passed, 1 skipped**, recorded in `checklist.md` §§ O and P.
  - `python scripts\check_shell.py` → exit 0.

## Phase 2 — Domain models and job state

> **Status: partially implemented.** `JobRepository` provides versioned
> metadata/checkpoints, atomic writes, fingerprints, recovery scanning, and
> resume-eligibility checks. **Corrected:** `AppContext` now always resolves a
> jobs directory itself (`$MMNEXT_JOBS_DIR`, else `~/.mmnext/jobs`) and always
> constructs the `JobRepository`, so the old claim that "it creates/scans it
> only when `jobs_dir` is supplied" is no longer true — `MainWindow`
> constructing `AppContext()` with no argument is fine today. The transcript
> adapter still saves its artifact and checkpoint but does not itself persist
> completed Job metadata; that is done by the UI layer after a successful
> transcript.

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
  disk-backed metadata/checkpoint persistence. The repository is now
  constructed on every normal startup (see the corrected status note above).
  Completed REAL transcript Job creation happens in the UI layer after a
  successful transcript, and completed jobs are listed by
  `list_completed_real()` / `scan()["completed_real"]`; the restart-to-open
  path is still not end-to-end complete.

- [x] Implement schema versioning for current records.
  - Job metadata uses schema v1, checkpoints use the domain checkpoint schema,
  and transcript artifacts use schema v1. Migration hooks between versions
  are **not** implemented.

- [x] Implement atomic JSON/checkpoint writes.
  - `mmnext/domain/paths.py::atomic_write_text`;
  `test_workers.py::test_checkpoint_write_is_atomic`.

- [x] Implement source/settings/mode/schema fingerprint helpers.
  - `mmnext/domain/fingerprint.py::canonical_fingerprint()` is now the single
  algorithm for source identity, local file size/mtime, mode, schema version,
  and settings. `JobRepository.compute_fingerprint()` and
  `WhisperTranscriptAdapter._fingerprint()` both delegate to it, so the two
  previously divergent values now agree. The transcript artifact stores the
  exact `fingerprint_settings` that were hashed, so a re-open can re-derive
  the value. The reopen comparison is implemented but currently recomputes
  without those settings and therefore rejects real artifacts — see the
  "What is still NOT true" list. General artifact reuse and invalidation are
  still incomplete.

- [x] Implement repository scan for recoverable and corrupt job records.
  - `JobRepository.scan()` discovers incomplete records, completed records,
  completed REAL records (`scan()["completed_real"]`), and corrupt metadata.
  `AppContext` invokes it on every startup, because `AppContext` always
  resolves a jobs directory for itself. **Corrected:** the previous claim that
  "standard `MainWindow` startup does not currently supply that configuration"
  was stale — verified by running `AppContext()` with no argument.

- [ ] Wire repository-discovered jobs into the normal Jobs screen, including
  completed REAL transcript records.
  - **Partly done.** `AppContext._load_recoverable_jobs_from_repo()` now adds
  completed non-demo jobs from `scan()["completed"]` to the `JobManager`, and
  the repository exposes `list_completed_real()` / `scan()["completed_real"]`.
  The Jobs screen still renders only what `JobManager` holds, and the
  restart-to-open path is still not end-to-end complete (see the priority
  slice above).

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

- [x] Wrap existing narrator planner as an application service.
  - `mmnext/services/adapters/narrator.py::NarratorPlanningService` (defensive
    legacy load) + `mmnext/application/narrator_coordinator.py::NarratorPlanCoordinator`.

- [ ] Preserve glossary/story context, batching, audit, retries, and fallback behavior.
  - The `TranslationProvider` protocol accepts `context` and `glossary`, but the
    current adapters ignore them; batching, audit and retries are not written.

- [x] Keep exact-dubbing translation as a separate contract.
  - `TranslationProvider` operates on `NarrationSegment`, never on
    `ExactDubbingRow`.

- [x] Do not route exact-dubbing through narrator summarization.
  - The pipeline only ever reads `project.transcript()` and writes
    `project.set_narration_segments()`; it never touches the exact-dubbing
    working set (`test_pipeline_never_touches_exact_dubbing_rows`).

- [x] Ensure external model credentials are optional in demo/offline mode.
  - No network SDK is imported anywhere in `mmnext/`; the demo adapters are
    fully offline (`test_architecture_gates.py::test_no_external_api_clients_in_milestone_one`).

### TTS/render

- [x] Wrap Edge TTS behind `SpeechSynthesizer`.
  - `mmnext/services/adapters/narrator_tts.py::LegacyEdgeTtsAdapter` calls
    `edge_tts.Communicate` when the package is installed and returns no audio
    (with a log line) when it is not.

- [x] Add voice discovery/configuration.
  - `voice_discovery()` returns the Burmese voices; the pipeline reads
    `settings["voice"]` and `settings["rate"]`.

- [x] Preserve text/voice cache signatures.
  - `cache_key(text, voice, rate)` is a stable sha256 over `voice|rate|text`.
    *Reuse on disk is not yet implemented — the pipeline computes the key but
    does not consult a cache.*

- [x] Wrap Smart Sync renderer.
  - `mmnext/services/adapters/narrator_render.py::LegacySmartSyncRenderer`.

- [ ] Wrap exact-duration renderer.

- [ ] Wrap splitter renderer.

- [ ] Use partial outputs and final validation before rename.

## Phase 4 — Narrator mode integration

- [x] Connect source → Whisper → plan → translation → TTS → Smart Sync stages.
  - `mmnext/application/narrator_pipeline_coordinator.py` runs
    plan → translate → synthesise → render; the Whisper stage feeds it through
    the persisted transcript. **The run currently uses the DEMO adapters only** —
    the `Legacy*` adapters are implemented but not yet wired into the run.

- [x] Add stage progress and structured logs.
  - `ProgressEvent` per stage on the codebase's 0–100 scale, plus
    `AppContext.append_log()` entries; the panel shows a progress bar and a
    status line.

- [ ] Add safe stop at stage and segment boundaries.
  - **Stage boundaries are done**: `request_stop()` stops the run at the next
    stage boundary and keeps the partial result. **Segment boundaries are not**:
    the translation and synthesis stages do not check the stop flag per
    segment.

- [ ] Add resume/reuse detection.
  - Not implemented. `cache_key()` exists, but the pipeline does not consult
    the cache and there is no checkpointed resume.

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

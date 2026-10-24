# MMNext — GitHub Copilot prompts for the remaining roadmap

This document turns the remaining `todo plan.md` work into separate Copilot prompts, excluding the first task for restart discovery and fingerprint validation. That first task has its own prompt at `outputs/copilot-task-restart-discovery-fingerprint.md`.

Do not give all of these prompts to Copilot at once. After Nemotron reviews the current code, tests, and review results and selects the next task, use **only one prompt**. If the code already implements a task, do not duplicate it; report the evidence instead.

## Shared instructions

To use a work order, copy this shared preamble first, then copy **exactly one** numbered task prompt below it. Do not paste the entire collection into Copilot.

```text
You are implementing one approved MMNext Movie Recap Pro work order. Use the model selected and available in the current GitHub Copilot environment; do not claim to be using Nemotron or another model unless it is actually selected. Nemotron is the separate planner/reviewer and decides the next task.

Before editing, read the current Agent.md, instructions.md, todo plan.md, checklist.md, README.md, and every applicable AGENTS.md from the repository root to the files you will change. Inspect the relevant current source, tests, and Git diff. Confirm whether the requested behavior is already implemented. If a required decision is unapproved or the work order conflicts with a project invariant, stop and report the exact blocker instead of guessing.

Implement only the single selected task. Preserve the existing UI/application/domain/services/infrastructure boundaries. Keep FFmpeg, yt-dlp, Whisper, TTS, model calls, large file operations, and artifact validation off the PySide6 GUI thread. Keep REAL and DEMO flows separate; never silently fall back to demo behavior. Use job-scoped paths and atomic persistence for real jobs. Never overwrite source media or expose secrets. Do not alter legacy output conventions without an approved migration.

Preserve Exact Dubbing invariants: id, original, start, and duration are immutable; only burmese and gender are editable. Never summarize, omit, reorder, merge, retime, or invent Exact Dubbing dialogue. Keep Exact Dubbing independent from Narrator Mode.

Add or update focused tests, run the relevant full test suite when practical, and report exact commands and pass/skip/failure counts. Do not claim unrun tests passed. Do not commit, push, create a pull request, or select the next project task unless explicitly requested.

Write the user-facing completion report in clear, natural, grammatically correct Myanmar Unicode Burmese. Do not use Zawgyi or accidentally mix unrelated scripts or languages into Burmese sentences.
```

The task-specific prompts below are in English for use with Copilot. The required user-facing completion report is in Myanmar Unicode Burmese.

## Phase 0 — Baseline decisions and documentation

Do not let Copilot make the Phase 0 decisions on its own. Nemotron must first compare the current implementation with the user's approved requirements and produce a decision record. The active project already uses the `mmnext` package, so do not reopen the decision to base the new application on the legacy Tkinter project. Use the prompt below only after the outstanding decisions have been approved.

### Prompt 0 — Document approved baseline decisions

```text
You are updating MMNext project documentation only. Nemotron has supplied the following approved baseline decisions: [PASTE THE APPROVED DECISION RECORD HERE].

Read Agent.md, instructions.md, todo plan.md, checklist.md, README.md, and relevant current source/tests. Compare each Phase 0 checkbox with the real repository state. Do not invent a decision where the approval record is silent. Do not change source code. Update only the documentation needed to record the approved decisions, compatibility/migration boundary, supported Windows/Python/PySide6 targets, media-tool strategy, job/artifact conventions, and legacy-reference status. Keep all statements evidence-based, preserve historical test evidence, and do not mark a capability complete unless code/tests prove it. If a decision is not approved or conflicts with the current implementation, stop and report the exact question to Nemotron instead of guessing.

Run documentation/link checks if the repository has them. Return the exact files changed, decisions documented, unresolved questions, and checks run. Respond to the user in correct Myanmar Unicode Burmese. Do not commit or push.
```

## Phase 3 — Runtime adapters and source/download

### Prompt 1 — Media tools, source intake, metadata, and Analyze

```text
Implement one bounded shared-runtime/source-intake slice for MMNext. First inspect the current PySide6 app, services, settings, adapters, tests, and the Phase 3 roadmap. Do not duplicate features already present.

Implement configurable FFmpeg/FFprobe discovery using the project's existing conventions, with clear errors and a safe preference order for an explicitly configured path, an approved bundled path, and PATH. Keep mpv optional and preserve the placeholder player. Verify Windows child-process cleanup for any process this slice starts; do not add unbounded process launches.

Wire real local-file metadata and metadata-only YouTube Analyze through the existing service protocols and normal AppContext. Map yt-dlp formats/qualities into the existing domain model without starting a download during Analyze. Show available source size when known. Add local video drag-and-drop only if it fits the current Import screen contract. The output directory already has a Settings location; do not add a duplicate picker or relocate it without an approved UX decision.

Preserve demo mode and offline startup. Add focused adapter, mapping, UI, and Windows-safe process tests. Do not implement the downloader in this task. Report exact changed files, tests, limitations, and whether Analyze remained separate from Download. No commits or pushes.
```

### Prompt 2 — Real YouTube download queue

```text
Implement only the real YouTube download adapter and its persisted queue behavior. Inspect the current DownloadService/yt-dlp boundaries, domain states/events, JobRepository, download UI, and tests before editing.

Add yt-dlp format/quality selection and structured progress events for bytes, total size when known, speed, ETA, filename, destination, and task state. Persist enough job/checkpoint data to safely identify partial output and recover after restart. Use job-scoped paths, atomic metadata updates, and partial media names. Implement pause/resume only if the actual backend can safely support it; otherwise expose an honest capability label and do not simulate byte-range resume. Redact sensitive YouTube URL query parameters from logs and user-visible errors.

Keep Analyze and Download as separate user actions. Do not make network-dependent tests; use fake subprocess/provider fixtures. Test failure, retry, stop, partial-file state, redaction, and truthful pause/resume availability. Preserve demo behavior. Do not implement translation or rendering. Return exact test results and limitations in Burmese Unicode. Do not commit or push.
```

## Phase 4 — Narrator Mode

### Prompt 3 — Narrator planner and translation services

```text
Implement the Narrator planning/translation adapter slice only. Inspect the legacy narrator planner and its worker, current MMNext domain/service protocols, coordinators, settings, tests, and the project rules before changing code. Preserve legacy behavior through adapters; do not import Tkinter into MMNext or place planner logic in widgets.

Wrap sentence-aware recap planning and translation behind application/service interfaces. Preserve source-language behavior, story context, glossary consistency, contextual overlap/lookahead, batching, audit, bounded retries, and documented fallback behavior. Keep API credentials optional for DEMO/offline mode and load any real credentials only through the approved configuration boundary. Never log credentials or raw authorization material.

Keep Narrator recap semantics separate from Exact Dubbing. This task must not summarize or alter Exact Dubbing source rows. Add deterministic fake-provider tests for plan boundaries, context/glossary propagation, batches, audit/retry/fallback, missing credentials, and cancellation. Do not add TTS or final rendering here. Report exact test results, files, and limitations in Burmese Unicode. No commits or pushes.
```

### Prompt 4 — Narrator Edge TTS and Smart Sync adapters

```text
Implement the Narrator speech/render adapter slice only. Inspect the existing SpeechSynthesizer/VideoRenderer protocols, legacy Edge TTS and Smart Sync behavior, current models, path/checkpoint helpers, and tests before editing.

Wrap Edge TTS behind the existing speech service boundary. Add voice discovery/configuration for the supported Myanmar voices and rate controls using typed settings. Preserve a stable cache signature that includes the generated text, voice, rate, and every other synthesis option that changes audio. Reuse only validated cache artifacts. Wrap Smart Sync rendering behind the renderer protocol and preserve its configured retiming limits and existing visual timing behavior.

Write audio/video to job-scoped partial paths, validate outputs, and atomically finalize them. Keep long-running work off the GUI thread. Do not implement Exact Dubbing speech fitting in this task, and do not change the Exact Dubbing contract. Add fake-provider/cache/signature, failure, cancellation, and output-validation tests. Do not require live TTS credentials in ordinary tests. Return exact results and remaining limitations in Burmese Unicode; do not commit or push.
```

### Prompt 5 — Narrator end-to-end coordinator and production controls

```text
Connect the approved Narrator services into one resumable application workflow: source → transcript → plan → translation/audit → TTS → Smart Sync render → final validation. Inspect the current AppContext/coordinator, workers, state machine, job persistence, workspace panels, and relevant legacy behavior first. Implement only Narrator Mode.

Show truthful stage progress and structured logs. Support safe stop at stage/segment boundaries and resume/reuse only when source, settings, glossary/context, model, text, voice, and schema fingerprints match. Add batch-folder processing with completed-job skipping only after validation. Connect narration editor save and selected-segment re-render without rewriting unrelated segments. Surface translation-audit findings and unresolved issues. Block success until the final artifact exists and duration/stream validation passes; provide an output reveal action only for a validated artifact.

Never block the Qt GUI thread. Never silently fall back to demo or stale artifacts. Keep Exact Dubbing independent. Add integration tests with fake transcript/translation/TTS/render adapters for safe stop, reuse invalidation, batch skipping, single-segment edit/re-render, audit visibility, and failure recovery. Do not require external API access in tests. Report exact pass/skip/failure counts in Burmese Unicode. No commits or pushes.
```

## Phase 5 — Exact Dubbing Mode

### Prompt 6 — Exact Dubbing preparation, translation export, and UI warnings

```text
Implement the Exact Dubbing preparation/export slice without adding TTS or final video rendering. Inspect the current Exact Dubbing models, validation gate, local Whisper path, YouTube metadata/caption adapters, JobRepository, panel, legacy Mode 2 preparation/export behavior, and tests.

Support preparation from an available YouTube caption track, Whisper fallback, or supplied local transcript, with source metadata and versioned job artifacts. Preserve a strict one-to-one row contract. Export schema-compatible translation files, including translated_gender.json, using the existing naming/migration conventions where available. Revalidate the complete row set immediately before export.

Immutable fields are `id`, `original`, `start`, and `duration`; only `burmese` and `gender` may change. Never summarize, omit, reorder, merge, retime, or invent dialogue. Show an explicit warning in the Exact Dubbing UI that it does not summarize or omit source dialogue. Keep rendering disabled until validation succeeds. Add tests for each preparation source, schema/export round-trip, missing/reordered/changed rows, source immutability, Burmese validation, gender validation, and warning visibility. Do not route through Narrator planning or translation. Report exact evidence in Burmese Unicode; no commits or pushes.
```

### Prompt 7 — Exact Dubbing TTS, speed fitting, and final validation

```text
Implement the Exact Dubbing speech/render slice only after the preparation/export contract and validation gate are verified. Inspect the legacy Mode 2 pipeline and current MMNext services, job paths, state machine, and tests before editing.

Connect gender-to-voice mapping, TTS cache keyed by voice plus translated text and relevant synthesis options, speech-window fitting with pitch-preserving FFmpeg processing, and the exact-duration renderer. Preserve every source segment and the original video timeline. Prefer NVENC when available and fall back to CPU with a visible status; do not report NVENC if it was not used. Write partial outputs, validate the final duration within the configured tolerance and confirm the expected audio/video streams before atomic finalization.

Persist status.json/render_report.json-compatible information and display validated job status/report details in the UI. Rendering must remain blocked until all source rows validate. Test cache hit/miss, voice mapping, speed warnings/limits, unavailable encoder fallback, duration/stream mismatch, stop/failure recovery, and Exact Dubbing immutability. Use fake adapters for ordinary tests; do not require GPU or live TTS. Report actual optional hardware tests separately. Burmese Unicode report only; do not commit or push.
```

## Phase 6 — Splitter Mode

### Prompt 8 — Split planning, pause detection, and part preview

```text
Implement the Splitter planning/preview slice only. Inspect the current Splitter domain models, legacy splitter algorithm and short-tail rule, workspace/panel, media analysis services, and tests before editing.

Connect exact-duration and smart-pause planning with the configured maximum wait. Detect and record cut reasons using the supported values: exact, pause, breath, quietest, or end. Apply the verified short-tail merge rule. Show the proposed parts before render, including start/end, duration, cut reason, and warnings. Add preview of ratio, fill, text, and part number without rendering media. Record source/settings fingerprints with the plan.

Keep source media unchanged and do not use narrator summaries. Add unit/property tests for boundaries, maximum pause wait, exact cuts, short-tail merge, cut-reason display, stable fingerprints, and invalid source duration. Do not implement part rendering in this task. Return exact test counts and limitations in Burmese Unicode. No commits or pushes.
```

### Prompt 9 — Split rendering, resume, fingerprint reuse, and batch queue

```text
Implement Splitter per-part rendering and recovery using the approved split plan. Inspect the current renderer/process adapter, JobRepository, partial-file rules, legacy splitter output conventions, and Splitter UI/tests before editing.

Render each planned part to a job-scoped partial output and validate it before atomic rename. Persist per-part state and progress so safe stop/restart can resume only compatible unfinished parts. Reuse completed parts only when the source, cut plan, ratio/fill/text/part-number settings, renderer schema, and artifact fingerprints match; otherwise rebuild only the invalid part. Show per-part queued/running/paused/stopped/failed/complete state and expose truthful recovery actions. Add a batch splitter queue that does not duplicate active jobs.

Keep all media work off the GUI thread. Do not alter the source or legacy output names without an approved migration. Test per-part success/failure, stop/resume, fingerprint skip/rebuild, duplicate queue prevention, partial cleanup safety, and UI state. No network-dependent tests. Report exact results in Burmese Unicode; do not commit or push.
```

## Phase 7 — Common Video Editing

### Prompt 10 — Non-destructive timeline, ranges, overlays, and preview controls

```text
Implement the Common Video Editing project/timeline model and editing UI slice only; do not build a full nonlinear editor. Inspect existing render settings, workspace preview/timeline/inspector, mode panels, unsaved-edit handling, and tests first.

Add a non-destructive edit model for source range/trim and overlays, preserving the original media. Support title, logo, extra text, and blur-box overlays with editable placement and preview positioning. Complete the common preview controls that are currently missing, including volume, fit/zoom, ratio/fill, and flip, using typed settings and stable UI state. Ensure switching modes or refreshing panels does not lose selection or unsaved edits. Keep mode-specific state separate.

Add model serialization, selection/undo-safe editing where existing architecture supports it, preview/UI tests, and Myanmar Unicode round-trip tests for overlay text. Do not connect final export in this task. Report exact behavior and tests in Burmese Unicode. Do not commit or push.
```

### Prompt 11 — Common Editing export presets and validation

```text
Implement Common Video Editing export configuration and validation only after its non-destructive timeline model is approved. Inspect current renderer boundaries, job persistence, output conventions, and tests before editing.

Add typed export presets and map supported aspect ratio/fill/zoom/flip, source range, and overlay settings into the renderer. Never overwrite the source. Render to a job-scoped partial file, report progress through typed events, and finalize only after validating output existence, duration/range, expected streams, and requested settings. Record the settings fingerprint and a machine-readable render report. Show clear validation issues and expose Open Output only for a validated artifact.

Keep FFmpeg off the GUI thread. Add tests for range boundaries, preset mappings, overlay serialization, render failure, invalid/missing streams, incorrect duration, atomic finalization, and stale artifact invalidation. Use fake rendering in the normal suite. Do not expand into a Premiere-like editor or another mode’s renderer. Report exact test results in Burmese Unicode; no commits or pushes.
```

## Phase 8 — Reliability, packaging, and release

### Prompt 12 — Diagnostics, crash recovery, partial cleanup, and log export

```text
Implement the first release-reliability slice. Inspect current startup status probes, JobRepository recovery, logging, worker shutdown, and tests before editing.

Add a user-facing diagnostics report for Python/runtime, FFmpeg/FFprobe, mpv, GPU/NVENC, TTS connectivity, and optional translation credentials. Never display or log secret values; report only configured/missing/usable states. Add crash-safe job recovery and a conservative orphan partial-file cleanup flow that identifies candidates, protects active/recoverable jobs, and requires explicit user action before destructive deletion. Add structured log export with secret/URL redaction and useful stage/job identifiers.

Do not auto-resume jobs or delete artifacts automatically. Keep diagnostics usable offline and in DEMO mode. Add tests for missing tools, stale/corrupt jobs, active-job protection, user-confirmed cleanup, redaction, and structured log export. Report exact evidence in Burmese Unicode. Do not commit or push.
```

### Prompt 13 — Windows packaging and beta acceptance

```text
Prepare an evidence-based Windows beta packaging and acceptance slice. First inspect the approved Phase 0 decision record, package/build configuration, supported Python/PySide6 versions, tool discovery, current full test suite, and release checklist. Do not invent target versions, install methods, signing credentials, or hardware availability; ask Nemotron/user when an approval is missing.

Implement only the approved packaging strategy. Add a reproducible build configuration and package smoke test, include only approved runtime dependencies, and keep user media, secrets, generated media, and caches out of the package/source control. Complete a small-fixture end-to-end test path. Add or run acceptance checks for CPU-only and NVIDIA systems when available, non-ASCII/Myanmar file paths and Myanmar text round-trip/rendering, safe pause/stop/resume across each implemented major mode, and the complete release checklist. Clearly mark hardware or clean-machine tests as not run when unavailable; never claim them passed.

Update the user guide and legacy migration notes from verified behavior only. Do not beta-tag, commit, or publish a release. Return build/test commands, pass/skip/failure counts, machine details actually tested, unresolved release blockers, and a Burmese Unicode handoff for Nemotron.
```

## Recommended execution order and review gates

Use one Copilot prompt per task. The numbers below are the prompt numbers in this file; the transcript-recovery task has a separate prompt. Do not start a later task while the current task has unresolved blocking test failures or independent-review findings.

1. **Phase 0 decisions:** Nemotron checks whether any baseline decisions are truly unresolved. Use Prompt 0 only after Nemotron or the user has approved a decision record. Skip it if the decisions and documents are already accurate.
2. **First implementation task:** use `outputs/copilot-task-restart-discovery-fingerprint.md`. Wait for the Copilot handoff, then have Nemotron create a separate read-only review prompt. Fix any blocking findings and verify the restart/open and fingerprint acceptance criteria before continuing.
3. **Shared media foundation:** use Prompt 1 if Nemotron verifies that tool discovery, source intake, or metadata/Analyze wiring blocks the selected production slice. Prompt 2 covers the real downloader. Complete Prompt 2 before starting YouTube-dependent production work, especially Exact Dubbing from a remote video. If the Narrator local-file slice does not depend on downloading, Nemotron may defer Prompt 2 until it becomes a prerequisite; record the reason.
4. **Narrator:** follow Prompt 3 (planning/translation services), then Prompt 4 (TTS/Smart Sync adapters), then Prompt 5 (end-to-end workflow and controls). Do not start the coordinator until its required adapters and job persistence are accepted.
5. **Exact Dubbing:** follow Prompt 6 (preparation/export) before Prompt 7 (TTS, fitting, rendering, and validation). Do not start production rendering until validation and export are proven.
6. **Splitter:** follow Prompt 8 (planning/preview) before Prompt 9 (per-part rendering, resume, and batch processing).
7. **Common Video Editing:** follow Prompt 10 (non-destructive model and editing UI) before Prompt 11 (export and validation).
8. **Release hardening:** follow Prompt 12 (diagnostics/recovery/log export) before Prompt 13 (Windows packaging and beta acceptance). Do not tag or publish a release as part of these tasks.

After **every** Copilot task, return the complete handoff, changed-file list, Git diff or pull-request link if available, and full test output to Nemotron. Nemotron then creates a separate read-only review prompt. The reviewer checks the actual diff, tests, and acceptance criteria. Only after blocking findings are fixed and the slice is accepted should Nemotron select the next prompt. Update `todo plan.md` and `checklist.md` only for behavior that is implemented and verified. Never treat a passing full test suite alone as proof that the whole product is ready.

The latest checklist says the major mode order after transcript recovery is Narrator → Exact Dubbing → Splitter → Common Editing → release hardening. Prompt 1 and Prompt 2 are shared infrastructure, so Nemotron may place them earlier or defer them only when current code and verified dependencies justify that choice. Some Phase 0 items require Planner/user decisions rather than code; Copilot must never guess unapproved choices.

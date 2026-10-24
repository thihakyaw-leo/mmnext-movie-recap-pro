# MMNext Movie Recap Pro — Agent Handoff

## 1. Handoff instruction

You are now the primary implementation agent for **MMNext Movie Recap Pro**. Own the project end-to-end from this point forward. Continue from the current repository state; do not restart the project or redesign completed foundations without evidence.

The authoritative MMNext implementation workspace is:

```text
J:\mmnext-movie-recap-pro
```

A legacy/reference recap project is:

```text
J:\recap-en-to-mm-main\recap-en-to-mm-main
```

A second legacy exact-dubbing reference project is:

```text
J:\movie-recap
```

The goal is a professional Windows desktop application built with PySide6, with mpv playback, a Subtitle Edit-like production workspace, and four distinct production modes:

1. Common Video Editing
2. Splitter Mode
3. Narrator Mode
4. Exact Dubbing Mode

The new application must preserve the valuable behavior of both legacy projects while keeping the new UI, domain, application, and infrastructure layers separate.

## 2. Mandatory reading order

Read these files before editing:

```text
Agent.md
instructions.md
todo plan.md
checklist.md
README.md
```

Then inspect the relevant source and tests:

```text
J:\mmnext-movie-recap-pro\mmnext\domain\models.py
mmnext/domain/enums.py
mmnext/domain/paths.py
mmnext/domain/validation.py
mmnext/services/protocols.py
mmnext/services/adapters/metadata.py
J:\mmnext-movie-recap-pro\mmnext\infrastructure\repository\job_repository.py
J:\mmnext-movie-recap-pro\mmnext\infrastructure\transcript_adapter.py
J:\mmnext-movie-recap-pro\mmnext\ui\workers.py
J:\mmnext-movie-recap-pro\mmnext\ui\transcript_worker.py
J:\mmnext-movie-recap-pro\mmnext\ui\app_context.py
J:\mmnext-movie-recap-pro\mmnext\ui\main_window.py
J:\mmnext-movie-recap-pro\mmnext\ui\screens\jobs_screen.py
J:\mmnext-movie-recap-pro\mmnext\ui\workspace\
J:\mmnext-movie-recap-pro\mmnext\ui\widgets\
J:\mmnext-movie-recap-pro\tests\
```

Also inspect the legacy implementations before wrapping or changing behavior:

```text
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\controller.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\core.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\recap_planner.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\planner_worker.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\render_worker.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\splitter.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\splitter_tab.py
J:\recap-en-to-mm-main\recap-en-to-mm-main\app\narration_editor.py
J:\movie-recap\AGENTS.md
J:\movie-recap\SKILL.md
J:\movie-recap\README_MM.md
J:\movie-recap\pipeline_master_local.py
J:\movie-recap\run.bat
```

## 3. Current verified project state

### Completed and verified

- PySide6 UI shell exists and launches in demo/offscreen mode.
- Navigation and seven screens are registered and smoke-tested.
- Production workspace has the intended editor-style structure: segment area, preview area, timeline/selection, inspector, and logs/progress.
- Mode separation exists for Common Editing, Splitter, Narrator, and Exact Dubbing.
- Narrator and Exact Dubbing use separate domain models/coordinators.
- Unsaved-edit protection exists for destructive actions such as reset and close.
- Worker infrastructure uses dedicated `QThread` instances outside the Qt GUI thread.
- Worker signal contract exists for started, progress, log, paused, resumed, pause_requested, stop_requested, stopped, failed, and completed.
- Atomic checkpoint writes use temporary files and `os.replace` through the domain path helpers.
- Corrupt checkpoint loading is handled safely.
- JobRepository exists with versioned metadata/checkpoint schemas.
- Job-scoped paths are used for real jobs.
- Real jobs require job context; demo fallback is explicit.
- Fingerprints include source identity, source size/mtime where available, mode, settings/schema information.
- Resume eligibility checks state, support, schema, mode, fingerprint, artifacts, and completion state.
- Persistent `.stop_requested` handling exists for real jobs.
- Startup recovery scans for recoverable/corrupt jobs without auto-resuming.
- Local metadata and YouTube Analyze flows exist.
- Analyze is separate from Download.
- Download requires successful Analyze.
- Quality selection and output-folder persistence exist.
- Demo/real source and download separation exists.
- Exact Dubbing validation gate exists.
- Exact Dubbing immutable fields are enforced: `id`, `original`, `start`, `duration`.
- Exact Dubbing editable fields are `burmese` and `gender`.
- Exact Dubbing Render/Save are blocked before successful validation or when errors exist.
- Transcript domain model and `TranscriptProvider` protocol exist.
- Transcript worker runs outside the GUI thread.
- Stable transcript IDs and timestamps are preserved.
- Transcript checkpoints use JobRepository and atomic writes.
- Demo transcript flow and language/auto-detection contract exist.
- Legacy pipeline behavior has not been changed.

### Latest reported test evidence

The latest reported full suite result is:

```text
238 tests passed
```

Earlier verified milestones included:

```text
Worker focused tests:       24 passed
JobRepository tests:        18 passed
Phase 2 integration tests:   5 passed
Exact Dubbing tests:        18 passed
Source/download tests:      11 passed
UI shell/offscreen tests:   passed
```

Always run the actual current test suite before relying on these numbers:

```powershell
pytest tests -q --confcutdir=tests
```

## 4. Important current limitations

The current transcript milestone is still a foundation/simulation layer. It is not yet a complete real Whisper production flow.

Known limitations:

- Real Whisper binary/model invocation is not yet wired.
- FFmpeg audio extraction is still a placeholder in the transcript adapter.
- FFprobe fallback may return `0.0` when the binary is unavailable; real jobs must not treat that as valid analysis.
- Transcript rows are not yet written to a dedicated versioned `transcript.json` artifact for real jobs.
- Production Workspace live transcript binding is incomplete; demo data is still used in places.
- Real adapter progress for Whisper/download is not fully wired; placeholder progress remains in some paths.
- QThread and polling are retained by milestone decision; do not migrate to QRunnable unless a real correctness/performance need is demonstrated.
- Jobs screen actions are basic in some areas and should be connected to persisted repository records.
- Real TTS, translation, Gemini, Edge TTS, and final FFmpeg rendering are not connected.
- No automatic resume should be implemented; recoverable jobs must be presented for explicit user action.

Do not hide these limitations. Do not report a simulated transcript, download, render, or TTS operation as real production completion.

## 5. Critical invariants

### General

- Never block the PySide6 GUI thread with FFmpeg, yt-dlp, Whisper, TTS, model calls, or large file operations.
- Never write real-job checkpoints to the current working directory.
- Never silently fall back from real mode to demo behavior.
- Never expose API keys in source, logs, tests, or screenshots.
- Never overwrite original source media.
- Use atomic writes and partial media names.
- Do not change legacy output conventions without explicit migration work.

### Exact Dubbing

The following fields are immutable after preparation:

```text
id
original
start
duration
```

Only these are editable:

```text
burmese
gender
```

Exact Dubbing must never summarize, omit, reorder, merge, or invent source dialogue. Render must remain blocked until validation succeeds.

### Narrator Mode

Narrator Mode may use sentence-aware recap segmentation, story context, glossary, translation batching, audit, Smart Sync, and narrator editing. It must not be used as a substitute for Exact Dubbing.

### Download

Analyze and Download are separate actions. Analyze must not start Download. Real Download must not start before successful Analyze and must use a real job context.

### Transcript

Transcript rows must preserve stable IDs and source timing. Transcript work must not translate, summarize, or call TTS in the transcript-only milestone.

## 6. Immediate next milestone: Real Local Transcript Execution

Implement the next milestone in this order:

1. Real FFprobe duration probing for real jobs.
2. Real FFmpeg audio extraction limited to authoritative video duration.
3. Real `faster-whisper` invocation behind the existing `TranscriptProvider` interface.
4. Versioned, dedicated `transcript.json` artifact with metadata.
5. Real progress mapping.
6. Truthful stop/resume behavior.
7. Live Production Workspace transcript binding.
8. Nemotron technical review.

Do not add Gemini, translation, Edge TTS, or final video render during this milestone.

### Real transcript requirements

- Real jobs require a valid FFprobe result.
- Missing FFprobe or zero/invalid duration must produce a structured unavailable/failed state, not a successful transcript.
- FFmpeg must create a valid mono 16 kHz PCM WAV limited to video duration.
- Audio output must be written to a partial file and atomically renamed after validation.
- Whisper must run in a worker thread.
- Explicit language and auto-detection must be supported.
- Transcript rows must preserve stable IDs, start, duration/end, and text.
- Real progress must not use simulated percentages.
- Checkpoints must identify the stage, artifact paths, source fingerprint, and whether resume is actually supported.
- If Whisper cannot resume mid-operation, state that clearly and resume from the last safe stage or restart the stage explicitly.
- Real/demo status must be visible in the UI.

### Required tests

Add or update tests for:

```text
real_ffprobe_required_for_real_job
zero_duration_rejected_for_real_job
demo_zero_duration_fallback_allowed
ffmpeg_audio_extraction_command
audio_output_validation
partial_audio_atomic_rename
real_whisper_adapter_invocation
explicit_language_forwarded
auto_detect_forwarded
real_transcript_artifact_written
transcript_artifact_atomic_write
real_progress_not_simulated
stop_checkpoint_after_completed_segment
resume_policy_is_truthful
live_workspace_transcript_binding
real_tool_failure_visible_in_ui
whisper_never_runs_on_gui_thread
no_translation_is_called_in_transcript_milestone
```

Use mocks/fakes for FFmpeg, FFprobe, and faster-whisper in unit tests. Add optional integration tests that skip cleanly if tools/models are unavailable.

## 7. Work protocol for CUE Agent

For every milestone:

1. Read the governing documents and relevant source.
2. Inspect current tests before changing behavior.
3. State the exact scope and files to change.
4. Implement the smallest vertical slice.
5. Add tests before declaring completion.
6. Run focused tests.
7. Run the full suite.
8. Run offscreen UI smoke tests.
9. Inspect the final diff for accidental contract changes.
10. Update the checklist with evidence.
11. Ask a separate review model for architecture/UX review when the milestone is material.

Do not perform broad refactors during a feature milestone. Do not change multiple mode contracts in one pass.

## 8. Review model routing

Use model roles as follows:

```text
Step 5 Preview
  Lead architecture, difficult implementation, repository-level reasoning,
  real media adapter design, and complex tests.

Minimax M3.1 Flash Free
  Small patches, test boilerplate, simple fixes, and routine refactoring.

Meta Muse Glimmer 30B
  UI/UX review, workflow review, screenshots, layout, readability, and usability.

NVIDIA Nemotron 3.5 Super VL 120B A12B
  Final architecture, safety, regression, multimodal, and production-readiness review.
```

Only one implementation agent should edit code for a given change. Review agents should report findings without editing. Apply only confirmed findings.

## 9. Router orchestration policy

CUE Agent is the primary orchestrator and final owner of the repository. Use the configured Router to delegate work to the model best suited to the task, then consolidate the result and remain responsible for the final implementation.

```text
Step 5 Preview
  Architecture decisions, difficult implementation, real media adapters,
  threading/state work, and complex tests.

Minimax M3.1 Flash Free
  Small isolated patches, test boilerplate, simple fixes, and routine refactoring.

Meta Muse Glimmer 30B
  UI/UX review, workflow usability, screenshots, layout, readability, and Myanmar text-entry review.

NVIDIA Nemotron 3.5 Super VL 120B A12B
  Final architecture, safety, regression, multimodal, and production-readiness review.
```

Router rules:

1. Give every delegated model the relevant files, exact milestone scope, and governing invariants.
2. Do not ask multiple models to edit the same files concurrently.
3. Review models must return findings only; they must not modify the repository.
4. Reconcile conflicting findings against the code, tests, and project documents.
5. Apply only confirmed findings through one implementation path.
6. After changes, run focused tests, the full suite, and the appropriate UI smoke test.
7. Never treat a model's textual approval as a substitute for local tests or real media smoke tests.
8. Include delegated model names, findings, and decisions in the milestone report.

## 10. Required completion report

At the end of every milestone, report exactly:

```text
1. What changed
2. Files changed
3. Contracts preserved
4. Tests run and results
5. UI smoke result
6. Persistence/checkpoint behavior
7. Known limitations
8. Checklist items completed
9. Review status
10. Next recommended milestone
```

Never report a real feature as complete when it is simulated, placeholder-only, or demo-only.

## 11. Completion target

The project is not beta-ready until a user can:

- choose a local video or analyze a YouTube URL;
- select quality and output folder;
- download with truthful progress and safe recovery;
- open a real transcript in the workspace;
- choose Narrator or Exact Dubbing without mixing contracts;
- edit and validate Exact Dubbing rows safely;
- generate Myanmar TTS through the correct service;
- render a final video with duration/output validation;
- stop and resume jobs without corrupting artifacts;
- inspect logs, reports, and job folders;
- use Myanmar Unicode text reliably on Windows.

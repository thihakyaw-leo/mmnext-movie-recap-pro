# Copilot Instructions — MMNext Movie Recap Pro

## Read first

Before writing code, read:

1. `Agent.md`

1. `todo plan.md`

1. `checklist.md`

1. The relevant legacy source files in both project roots:
  - `app/controller.py`
  - `app/core.py`
  - `app/recap_planner.py`
  - `app/planner_worker.py`
  - `app/render_worker.py`
  - `app/splitter.py`
  - `app/splitter_tab.py`
  - `app/narration_editor.py`
  - `pipeline_master_local.py`
  - `README.md` / `README_MM.md`
  - `AGENTS.md` / `SKILL.md` in `J:\movie-recap`

Do not infer behavior from filenames alone. Confirm contracts in code and tests.

## Primary execution rule: UI first

The first implementation phase is a functional PySide6 UI shell. Build the screens and navigation before connecting real network, AI, TTS, or rendering services.

The first UI milestone must run with no API key, no downloaded video, and no GPU. It should use demo project data and simulated task events. The app must demonstrate:

- Source selection.

- YouTube URL analysis placeholder.

- Download queue states.

- Production workspace layout.

- Mode switching.

- Segment selection.

- Timeline/playhead movement.

- Inspector editing.

- Logs and progress.

- Stop/resume state transitions.

Do not replace this milestone with a command-line prototype.

## Framework and UI rules

- Use **PySide6** for the new UI.

- Use **mpv** through a small playback adapter for video playback. Keep mpv optional during the first UI-only milestone and provide a placeholder player when it is unavailable.

- Use Qt signals/slots and worker threads or `QThreadPool`/`QRunnable` for long-running tasks.

- Never call FFmpeg, yt-dlp, Whisper, Edge TTS, Gemini, or file-heavy operations directly in a widget event handler.

- Keep all widgets responsive during work.

- Use a dark, professional editor theme, but do not sacrifice readability or keyboard access.

- Use layouts and size policies; do not hard-code a single screen resolution.

- Use model/view widgets (`QTableView`, `QListView`, custom models) for segment tables and job queues instead of rebuilding rows manually.

- Keep selection stable when data refreshes.

- Use a command/action layer for menu items and keyboard shortcuts.

## Domain and service rules

Create typed domain models before connecting external services. At minimum define models for:

- `SourceAsset`

- `VideoMetadata`

- `DownloadTask`

- `JobRecord`

- `TranscriptSegment`

- `NarrationSegment`

- `ExactDubbingRow`

- `SplitPart`

- `OverlayItem`

- `RenderSettings`

- `ProgressEvent`

- `ValidationIssue`

Use enums for source type, mode, task state, severity, and job stage. Avoid passing unstructured dictionaries between UI and service layers except at explicit serialization boundaries.

External integrations must be behind interfaces/adapters:

- `VideoMetadataProvider`

- `VideoDownloader`

- `MediaProbe`

- `TranscriptProvider`

- `TranslationProvider`

- `SpeechSynthesizer`

- `VideoRenderer`

- `VideoSplitter`

- `VideoPlayer`

- `JobRepository`

The legacy scripts can initially be wrapped by subprocess adapters. Do not copy their implementation into UI classes.

## Source behavior to preserve

### Narrator mode

Preserve the current recap project behavior: Whisper transcript, language selection/auto-detection, story context/glossary, batched translation, translation audit, sentence-aware segments, Edge TTS, Smart Sync, overlays, batch processing, safe stop, resume/reuse, and narration editing.

### Exact Dubbing mode

Preserve the movie-recap Mode 2 contract:

- Prepare a transcript from YouTube captions, Whisper fallback, or a supplied local transcript.

- Keep every segment.

- Do not change `id`, `original`, `start`, or `duration`.

- Edit only Burmese translation and speaker gender.

- Validate all rows before render.

- Use the gender-to-voice mapping.

- Cache TTS by voice plus text.

- Fit generated speech into the allowed speech window with pitch-preserving FFmpeg filters.

- Preserve the original video timeline and duration.

- Prefer NVENC and fall back to CPU encoding.

### Splitter mode

Preserve exact cuts, smart pause cuts, maximum extra wait, short-tail merge, ratio/fill, text overlays, part labels, per-part output names, fingerprints, progress, and resume behavior.

## UI state rules

- Every long-running task has a visible state: queued, running, paused, stopping, stopped, failed, complete.

- Buttons must be derived from state. Example: Pause is enabled only while a task is pausable; Resume is enabled only while paused/stopped and resumable.

- Disable destructive or conflicting actions while a job is in a non-interruptible commit step.

- Show a confirmation only for destructive actions such as deleting a job or discarding unsaved edits.

- Safe stop means request a checkpoint, not immediate process termination, unless the user explicitly chooses Force Stop.

- After a stop, show exactly what was completed and where to resume.

## Download UX rules

Analyze and Download are separate actions.

Analyze should populate metadata without downloading the full media. Download should allow quality/output selection first. The download card must show progress, speed, ETA, destination, and current state. If the backend does not support reliable byte-range resume, label Pause as “Pause requested” or omit it instead of faking resume.

## Editing UX rules

- Source text is read-only unless the mode explicitly allows source editing.

- Exact-dubbing timing/ID fields are visibly locked.

- Unsaved changes are tracked at project and segment level.

- Saving a segment must be atomic and must not rewrite unrelated rows.

- Provide next/previous segment, search, problem navigation, and keyboard-friendly editing.

- Preserve Myanmar Unicode and use a suitable font/text control.

### Myanmar language and Unicode requirements

- Write all newly authored Myanmar-language content—UI labels, instructions, prompts, documentation, logs, captions, and translations—in standard Burmese using Unicode code points and UTF-8 encoding. Do not use Zawgyi encoding, Zawgyi-only fonts, or Latin transliteration unless the user explicitly requests it.
- Review Myanmar text for correct meaning, spelling, grammar, punctuation, and natural phrasing; Unicode validity alone does not prove linguistic accuracy. Use consistent terminology and do not mix unrelated languages or scripts unintentionally.
- Preserve Myanmar combining marks, word spacing, and punctuation through storage, serialization, display, and copy/paste. Use Myanmar-capable fonts and controls. Tests must verify that representative Myanmar text round-trips unchanged and renders without replacement characters; ASCII-only tests are insufficient.
- Do not silently normalize, rewrite, translate, or re-encode source transcript text. In Exact Dubbing, preserve each original row and its ID, original text, start, and duration exactly; only the permitted translation and gender fields may change.
- Narrator translations may adapt wording only within the Narrator contract. Exact Dubbing translations must remain one-to-one with source dialogue and must not summarize, omit, merge, reorder, or invent content.

- Show validation issues near the edited row and in a global issue panel.

## Data and persistence rules

- Use a versioned JSON schema or SQLite repository for project/job state; choose one deliberately and document the decision.

- Use atomic writes.

- Never mutate source media.

- Use temporary `.partial` files for media output.

- Add a fingerprint to any reusable artifact.

- Resume only when source fingerprint, mode, settings, and schema are compatible.

- If incompatible, create a new revision or explicitly invalidate the artifact.

## Error handling and logging

Every error must include:

- User-facing summary.

- Stage and operation.

- Technical detail in the job log.

- Artifact or command involved.

- Suggested recovery action.

- Whether retry/resume is safe.

Use structured events for UI updates rather than parsing arbitrary human log text. Keep raw subprocess output in the job log, but emit typed progress/status events to the UI.

## Testing rules

At minimum, add tests for:

- Domain model serialization/deserialization.

- Job state transitions.

- Button availability for each task state.

- Source validation and metadata mapping.

- Download progress event handling.

- Exact-dubbing row invariants.

- Translation validation.

- Split plan calculations and short-tail merge.

- Fingerprint/reuse decisions.

- Atomic checkpoint writes.

- Safe stop/resume recovery.

- Final duration validation.

UI tests should cover navigation, mode switching, selection preservation, unsaved-edit prompts, and demo-mode operation. Integration tests should be optional and skip cleanly when FFmpeg/mpv/API credentials are unavailable.

## Security rules

- Never print, commit, or place API keys in UI state or logs.

- Read secrets from environment/configuration providers.

- Redact authorization headers and sensitive URLs from logs.

- Do not upload user media unless explicitly required by an approved service.

- Keep generated media and `.env` files out of version control.

## Change discipline

- Make small, reviewable changes.

- Do not rewrite the legacy pipeline while building the UI shell.

- Do not silently reintroduce the deprecated Mode 1/external-chat workflow into the exact-dubbing path.

- Do not add a new CLI flag when a behavior belongs in the UI or a project setting.

- Do not change output names/contracts without a migration note and compatibility tests.

- Run focused tests after each change and the full test suite before declaring a milestone complete.

## Completion response format for Copilot

When completing a task, report:

1. What changed.

1. Files changed.

1. Which source contract was preserved.

1. Tests run and results.

1. Known limitations or follow-up work.

1. Whether the relevant checklist items are complete.

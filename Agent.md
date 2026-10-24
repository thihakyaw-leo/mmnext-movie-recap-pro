# MMNext Movie Recap Pro — Agent Brief

## 1. Mission

Build **MMNext Movie Recap Pro**, a Windows desktop movie-recap and dubbing workstation that combines the strongest ideas found in:

- `J:\recap-en-to-mm-main\recap-en-to-mm-main`: the existing Tkinter narrator-recap application with Whisper transcription, Gemini planning/translation, Myanmar Edge TTS, Smart Sync, overlays, batch processing, safe stop/resume, narration editing, and a video splitter.
- `J:\movie-recap`: the existing Mode 2 exact-duration Burmese dubbing pipeline with YouTube/local-video input, timestamped transcript preparation, Cue-controlled translation, speaker-gender voice mapping, exact timeline preservation, TTS caching, speed fitting, validation, GPU export, and durable job artifacts.

The target product is not a disposable script. It is a reliable, inspectable, resumable production application with a professional editing workspace and a simple first-run experience.

## 2. Non-negotiable implementation order

**Build the UI shell first. Do not begin by wiring the complete AI/video pipeline.**

The first usable milestone must be a PySide6 application shell with real navigation and placeholder data:

1. Project/start screen.
2. Source intake screen supporting local video and YouTube URL.
3. YouTube metadata/analyze screen.
4. Download queue/progress panel with Pause, Resume, and Stop states.
5. Video Production Workspace with a Subtitle Edit-like layout.
6. Mode navigation for Common Video Editing, Splitter, Narrator, and Exact Dubbing.
7. Video preview area, timeline/segment table, inspector/settings panel, logs/status panel, and job state indicators.
8. Mock/demo data so the complete navigation can be tested without API keys or a real video.

Only after this UI contract is accepted should the implementation connect real services through adapters.

## 3. Product principles

- **Clarity before automation:** every long-running action must show its current stage, progress, recoverability, and next available action.
- **One workspace, multiple modes:** users should not need to learn separate launchers for recap, dubbing, and splitting.
- **Source truth is preserved:** never silently alter original media, transcript IDs, timestamps, or exact-dubbing constraints.
- **Every expensive operation is resumable:** transcript, plan, translation, TTS segment, download, split part, and final render should have checkpointed state.
- **Preview before production:** users can inspect source metadata, transcript segments, overlays, planned cuts, and selected output settings before committing to a long job.
- **UI state is separate from domain state:** PySide6 widgets must not contain business logic or invoke FFmpeg/Whisper/TTS directly.
- **Truthful status:** never display Complete unless the expected artifact exists and validation has passed.
- **Safe defaults:** do not overwrite source files; use job folders, partial files, atomic writes, and explicit output paths.
- **Myanmar text is a first-class requirement:** use a proper text editor/rendering path, test Unicode shaping, and never assume ASCII-only UI or filenames.

## 4. Source capabilities to preserve

### 4.1 From recap-en-to-mm-main

Preserve and eventually expose through a service layer:

- Any-language-to-Myanmar narrator recap workflow.
- Source language selection and Whisper auto-detection.
- English `small.en` path and multilingual model path for other languages.
- Gemini story context, glossary consistency, batched translation, audit/retry behavior, and model/key fallback logic where legally and operationally permitted.
- Segment planning with sentence-aware boundaries, contextual overlap/lookahead, and Smart Sync.
- Edge TTS Myanmar voices: `my-MM-ThihaNeural` and `my-MM-NilarNeural`.
- TTS speed/rate, short-pause handling, voice volume, mirror/zoom, aspect ratio, fill mode, title, logo, extra text, and blur boxes.
- Batch-folder processing with completed-job skipping.
- Safe stop through a stop marker and child-process lifecycle management.
- Resume/reuse of transcript and plan artifacts.
- Narration editor with source text, Myanmar text, problem detection, save/re-render behavior, and Myanmar-friendly Windows text input.
- Splitter with exact or smart-pause cuts, ratio/fill, text box, part labels, progress, and per-part checkpointing.

### 4.2 From movie-recap

Preserve and eventually expose through a service layer:

- Local video and YouTube URL as first-class source types.
- Prepare → translate/edit → validate → render stage separation.
- YouTube metadata and download before processing.
- `translation_request.json`, `translated_gender.template.json`, `translated_gender.json`, `status.json`, and `render_report.json` style artifacts.
- Exact Mode 2 contract: keep every segment, ID, original text, start time, and duration unchanged.
- Speaker gender mapping: `male` → `my-MM-ThihaNeural`; `female`/`unknown` → `my-MM-NilarNeural`.
- Burmese translation validation, including complete segment count, original/timing equality, Burmese-script presence, and allowed gender values.
- TTS segment cache keyed by voice and translated text.
- Speech-window expansion into available gaps, pitch-preserving FFmpeg speed fitting, and warnings when speed exceeds the normal threshold.
- Exact original video duration and frame preservation during final export.
- NVENC-first encoding with CPU fallback.
- Durable job output folder and status/report artifacts.
- Glossary-aware translation and evidence-based speaker classification.

## 5. Target technical architecture

Use a layered architecture:

```text
PySide6 UI
  ├── Navigation / screens / dialogs
  ├── View models and Qt signals
  ├── Preview and timeline widgets
  └── User notifications

Application layer
  ├── Project/session controller
  ├── Job manager and state machine
  ├── Download coordinator
  ├── Mode coordinators
  └── Checkpoint/resume policy

Domain layer
  ├── SourceAsset / VideoMetadata
  ├── Transcript / Segment / TranslationRow
  ├── RecapPlan / DubbingPlan / SplitPlan
  ├── Overlay / Timeline / RenderSettings
  └── JobStatus / ProgressEvent / ValidationReport

Infrastructure adapters
  ├── FFmpeg/FFprobe adapter
  ├── yt-dlp adapter
  ├── Whisper adapter
  ├── Gemini/LLM adapter (only for the approved narrator mode)
  ├── Edge TTS adapter
  ├── mpv playback adapter
  ├── JSON/checkpoint repository
  └── Logging/diagnostics adapter
```

Recommended package direction:

```text
mmnext/
  app.py
  ui/
    main_window.py
    screens/
    widgets/
    dialogs/
    theme/
  application/
    project_controller.py
    job_manager.py
    download_manager.py
    mode_coordinators.py
  domain/
    models.py
    enums.py
    validation.py
    events.py
  services/
    source_service.py
    metadata_service.py
    transcript_service.py
    translation_service.py
    tts_service.py
    render_service.py
    splitter_service.py
    playback_service.py
  infrastructure/
    ffmpeg_adapter.py
    yt_dlp_adapter.py
    whisper_adapter.py
    llm_adapter.py
    edge_tts_adapter.py
    mpv_adapter.py
    repositories.py
  tests/
```

Do not import Tkinter into the new UI. Do not put PySide6 widgets inside service modules. Existing modules may remain as compatibility/reference implementations while adapters are introduced.

## 6. UI contract

### 6.1 Global shell

The main window should contain:

- Left navigation rail: Home, Import, Download, Workspace, Jobs, Settings.
- Top bar: current project/job name, source status, GPU/FFmpeg status, language, save indicator, and global Cancel/Stop action when relevant.
- Central page stack.
- Optional bottom status/log drawer that can expand without blocking the main workspace.
- Consistent keyboard shortcuts and accessible focus order.

### 6.2 Source intake

Provide two obvious cards:

- **Local Video:** file picker, drag-and-drop, supported formats, source preview.
- **YouTube URL:** URL field, Load/Analyze button, validation message, metadata card.

The user must not be forced into a processing mode before the source has been inspected.

### 6.3 YouTube metadata/analyze

After Load/Analyze, show:

- Thumbnail where available.
- Title, channel/uploader, duration, upload date if available, source URL.
- Available qualities/formats.
- Audio-only or video+audio selection where supported.
- Output folder picker.
- Estimated file size when available.
- Clear Download button.

Download must not start merely because Analyze succeeded.

### 6.4 Download manager

Show a job card with:

- Queued/downloading/paused/completed/stopped/failed state.
- Current bytes, total bytes if known, percentage, speed, ETA.
- Current filename and output path.
- Pause, Resume, Stop, Retry, Open Folder actions as appropriate.
- A log drawer with the last meaningful message.

Stopping must leave a resumable partial/download state where the underlying downloader supports it. Do not claim resume support if the adapter cannot safely resume.

### 6.5 Production workspace

Use a Subtitle Edit-like editing arrangement:

- **Left:** segment list or project outline.
- **Center:** mpv video preview, playback controls, current time, zoom/fit control.
- **Bottom:** timeline with segment boundaries, selected range, playhead, and mode-specific markers.
- **Right:** inspector/settings for the selected item.
- **Bottom drawer:** logs, validation warnings, and task progress.

The workspace should preserve the selected segment while switching panels. Editing text must not unexpectedly reset playback or lose unsaved changes.

### 6.6 Mode menu

Expose these modes as navigation cards or a mode switcher:

1. **Common Video Editing** — source preview, trim/range selection, overlays, aspect ratio, fill, title/logo/text, export settings.
2. **Splitter Mode** — part duration, smart cut, maximum pause wait, cut plan table, per-part preview, labels, text, ratio/fill, output folder.
3. **Narrator Mode** — transcript, sentence-aware plan, Myanmar narration, glossary/context, translation audit, voice/rate, Smart Sync, narration editor, final render.
4. **Exact Dubbing Mode** — every source segment preserved, ID/start/duration locked, Burmese translation and speaker gender editable, validation gate, exact-duration render.

Mode-specific panels may share widgets, but they must not silently change the mode’s data contract.

## 7. Mode invariants

### Common editing

- Original source is read-only.
- Edits are represented as a project/timeline model.
- Export uses a partial output followed by validation and atomic rename.

### Splitter

- Smart cuts may wait up to the configured maximum for a speech pause.
- Exact mode cuts at the requested duration.
- A very short tail is merged according to the existing splitter rule.
- Each part records start, end, cut reason, settings fingerprint, and output status.

### Narrator

- This is a recap/narration workflow, not exact dialogue dubbing.
- Sentence-aware segmentation and story context are allowed.
- Translation may be batched and audited.
- Smart Sync retimes visual playback to the generated Myanmar narration according to configured limits.
- Existing transcript/plan/TTS artifacts should be reused when their fingerprints still match.

### Exact dubbing

- Never summarize, omit, reorder, or merge source dialogue segments.
- `id`, `original`, `start`, and `duration` are immutable after preparation.
- `burmese` and `gender` are the editable fields.
- Render is blocked until validation succeeds.
- Final duration must match the source within the configured tolerance.
- Unknown gender remains valid and maps to the configured fallback voice.

## 8. Job state machine

Use explicit states rather than ad-hoc booleans:

```text
NEW
  → SOURCE_ANALYZED
  → DOWNLOAD_QUEUED
  → DOWNLOADING
  → DOWNLOAD_PAUSED
  → DOWNLOAD_STOPPED / DOWNLOAD_FAILED / DOWNLOADED
  → PREPARING
  → AWAITING_TRANSLATION_OR_EDIT
  → VALIDATING
  → READY_TO_RENDER
  → RENDERING
  → COMPLETE
```

Any state may become `STOP_REQUESTED`, then transition to a safe checkpoint state. Persist state after every material checkpoint. The UI must derive button availability from the state machine, not from scattered widget checks.

## 9. File and artifact rules

- Keep source media untouched.
- Use a per-project/per-source job folder.
- Write JSON atomically through a temporary file and rename.
- Write media to `.partial` or temporary names and rename only after validation.
- Every job should have a machine-readable status and a human-readable log.
- Use fingerprints for source, settings, translation text, voice, and render configuration.
- Never place API keys in source code, committed docs, logs, or UI screenshots.
- Never commit `.env`, downloaded media, generated audio, generated video, GPU runtimes, or large cache folders.

## 10. Agent working rules

1. Read this file, `instructions.md`, `todo plan.md`, and `checklist.md` before changing code.
2. Inspect nearby source and tests before editing an existing module.
3. Follow the current repository’s local rules if they conflict with a proposed migration; document the conflict before proceeding.
4. Implement one vertical slice at a time and keep the application runnable after each slice.
5. Prefer small adapters over large rewrites of the legacy pipelines.
6. Add tests for state transitions, JSON schemas, validators, fingerprints, and checkpoint behavior before connecting real long-running work.
7. Never hide failures behind a generic “something went wrong”; show the stage, artifact, command, and recovery action.
8. Keep UI updates on the Qt GUI thread. Run downloads, FFmpeg, Whisper, TTS, and rendering in worker tasks.
9. Do not use blocking subprocess calls from the GUI thread.
10. Do not claim a feature is complete until the relevant checklist and acceptance tests pass.

## 11. Definition of success

MMNext is ready for a beta release when a user can:

1. Start the PySide6 app.
2. Choose a local video or analyze a YouTube URL.
3. Select quality and output folder.
4. Download with visible progress and safe pause/stop behavior.
5. Open the production workspace and choose a mode.
6. Inspect/edit transcript or dubbing rows without losing timing data.
7. Run a resumable production job.
8. Recover from a stop or failure without restarting from zero.
9. Validate the final artifact and open its job folder.
10. Understand every major state without reading a terminal window.

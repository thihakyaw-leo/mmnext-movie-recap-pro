# MMNext Movie Recap Pro

## Current transcript slice (supersedes the historical milestone-1 notes below)

Production Workspace now has **Transcribe local video… (REAL)**. It runs the
local FFprobe → validated FFmpeg PCM WAV → faster-whisper adapter on a finite
worker thread, binds verbatim read-only source rows, and prepares separate Exact
Dubbing rows without creating a narrator recap. REAL/DEMO, measured progress,
failure guidance and cooperative Stop are visible. A real job never substitutes
demo rows when dependencies fail. Stop is restart-only, not mid-model resume.

This code path has mocked integration/offscreen regression coverage, **not a
verified real-media/model acceptance run**. Install/configure FFmpeg/FFprobe and
the optional faster-whisper dependency before using real transcription. The
local model must be available; first model loading can take time. The opt-in
real test uses `MMNEXT_TRANSCRIPT_SMOKE_MEDIA` and a local model directory in
`MMNEXT_TRANSCRIPT_SMOKE_MODEL` and skips when they are absent.

Artifacts keep the transcript v1 schema/basename but now live under the
source- and mode-isolated repository job tree. Existing shared-path transcripts
are not automatically migrated/reopened. Startup transcript recovery and
loading a saved transcript into a fresh session are not connected yet. No
translation, Gemini, Edge TTS or final rendering is added by this slice.
See `checklist.md` section M for evidence, exact limitations and review status.

A Windows desktop application for producing movie recaps, dubbed versions,
split parts and edited video.

The application is built **UI-first**: the complete editor shell comes up on
deterministic demo data before any real AI, download, transcription, text-to-
speech or rendering service is connected.

## Milestone 1 - what works today

Milestone 1 is a **functional PySide6 shell**. It runs with:

* no API key,
* no internet access,
* no YouTube access,
* no FFmpeg,
* no Whisper,
* no mpv,
* no NVIDIA GPU.

Everything that would need one of those is simulated by a deterministic demo
service, and the simulation runs on a worker thread so the GUI never blocks.

| Area | What the shell demonstrates |
|---|---|
| Source selection | Local file import and YouTube URL input |
| Analyze | URL analysis placeholder that fills in metadata without downloading |
| Download queue | Queue states plus a progress card with progress, speed and ETA |
| Download controls | Pause, Resume, Stop and Retry derived from the task state |
| Production workspace | Subtitle-Edit-like layout: segment list, timeline, preview, inspector |
| Playback | An mpv adapter with a placeholder player fallback when mpv is missing |
| Mode switching | Common Video Editing, Splitter, Narrator and Exact Dubbing |
| Segment selection | A shared selection between the table, the timeline and the inspector |
| Inspector editing | Per-mode editing with Myanmar Unicode support |
| Logs and progress | A collapsible bottom log drawer with a Log and a Progress tab |
| Stop / resume | Queued, running, paused, stopping, stopped, failed and complete states |
| Unsaved edits | A confirmation before a destructive reset or close; mode switching never discards an edit |

No real backend is wired yet. The download *Pause* is a simulated pause, not a
byte-range resume.

## Running the demo

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m mmnext.main
```

or, using the console script after an editable install:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m mmnext.main
```

`scripts/run_app.py` is a thin launcher wrapper around the same entry point.

## Running the tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests
```

`--confcutdir=tests` matters on Windows: without it pytest walks up to the
drive root and the collection can fail with a permission error.

The suite runs fully offline. Integration tests that need FFmpeg, mpv or API
credentials skip cleanly when those are unavailable.

Current status: **145 tests passing** (`145 passed in 52.87s, exit code 0`).
A headless smoke check of the whole shell is available too:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe scripts\check_shell.py
```

## Architecture

The dependency direction is strictly one-way:

```
ui  ->  application  ->  services  ->  domain
```

* `mmnext/domain` - typed models, enums, validation and path helpers. Pure
  Python, no Qt.
* `mmnext/services` - the interfaces an external system has to satisfy
  (`VideoMetadataProvider`, `VideoDownloader`, `TranscriptProvider`,
  `TranslationProvider`, `SpeechSynthesizer`, `VideoRenderer`,
  `VideoSplitter`, `VideoPlayer`, `JobRepository`) and the demo
  implementations used in milestone 1.
* `mmnext/application` - the controllers that drive those services
  (`ProjectController`, `JobManager`, `DownloadController` and the per-mode
  coordinators). Still Qt-free.
* `mmnext/ui` - the PySide6 shell: screens, widgets, models and the theme.
  It only ever talks to the application layer through `AppContext` signals.
* `mmnext/infrastructure` - runtime probes and the mpv / placeholder player
  adapters.

`tests/test_architecture_gates.py` enforces the layering with ten gates,
including that the domain and application layers never import PySide6, that
Tkinter never appears, and that no network SDK is imported anywhere in
`mmnext/`.

### The four modes

Narrator Mode and Exact Dubbing Mode are deliberately kept apart. They do
not share a row type, a base class or a coordinator implementation - only a
small protocol. A narrator edit can never reach an exact-dubbing row.

* **Narrator Mode** works on summarised, re-orderable narration rows.
* **Exact Dubbing Mode** keeps one immutable row per source line: the id,
  the original text, the start time and the duration may not change, and only
  the Burmese translation and the speaker gender are editable.

## Known limitations

Milestone 1 is a **shell**. The following are deliberately not implemented yet
and must not be mistaken for working features.

* **No real backend.** FFmpeg, yt-dlp, Whisper, Edge TTS and Gemini are never
  invoked. Every action that would need one of them is a labelled simulation
  ("Simulated in milestone 1").
* **Download pause is simulated, not a byte-range resume.** The demo provider
  restarts from the last chunk index. When a real downloader lands, the
  control must be relabelled "Pause requested" or removed if the backend
  cannot resume, rather than faking resume.
* **Nothing is persisted to disk.** There is no project repository, no
  versioned JSON schema, no artifact fingerprints and no startup recovery
  scan. "Save narration" clears the dirty flag in memory; it does not write a
  file.
* **The global Stop button is disabled for demo jobs** by design, so the demo
  cannot destroy its own fixtures.
* **The demo exact-dubbing fixture ships with one intentional error** (row 12
  has no Burmese text), so `ExactDubbingCoordinator.can_leave()` is `False`
  until that row is filled. This is a fixture, not a bug.
* **"Save" in the unsaved-changes prompt clears the dirty flag only.** It does
  not persist, because there is no persistence layer yet.
* **Incomplete mode pages.** Volume and fit/zoom on the preview, trim/range in
  Common Editing, smart-cut and maximum-wait controls in Splitter, and
  voice/rate and Smart Sync in Narrator are not wired. See `todo plan.md` for
  the itemised list.
* **The Settings dependency rows are static labels.** Only the top-bar
  FFmpeg / GPU chips reflect the live runtime probe.
* **"Open job folder" is missing** from the Jobs screen, and the download
  card's "Open in workspace" navigates to the workspace rather than Explorer.

## Source projects

This application replaces two legacy pipelines, which are left untouched:

* `J:\recap-en-to-mm-main\recap-en-to-mm-main` - the narrator pipeline.
* `J:\movie-recap` - the exact-dubbing pipeline (Mode 2 contract).

They are wrapped by subprocess adapters in a later milestone; their logic is
never copied into a UI class.

## Documentation

* `Agent.md` - the governing contract for this project.
* `instructions.md` - the engineering rules the implementation follows.
* `todo plan.md` - the phased plan.
* `checklist.md` - the acceptance checklist, with evidence for every item.
#   m m n e x t - m o v i e - r e c a p - p r o  
 
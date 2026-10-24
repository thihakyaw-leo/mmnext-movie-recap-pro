# Next Plan — Exact Dubbing Prepare/Export Vertical Slice

## Context
- Project: MMNext Movie Recap Pro (Windows desktop, PySide6, UI-first).
- Current verified state: full suite `382 passed, 1 skipped`; offscreen shell smoke passes.
- Narrator pipeline exists with honest DEMO/REAL adapter selection and speech caching.
- Exact Dubbing UI locks source identity and validates rows, but no prepare/export/TTS/render chain is wired.
- Real media acceptance and restart-to-Workspace checks still need a cached Whisper model and approved fixture.

## Goal
Make Exact Dubbing a usable vertical slice:
- prepare source segments from a transcript
- preserve immutable source identity
- export a schema-compatible `translated_gender.json`
- connect TTS/render/cache with final validation

## Recommended next slice
Exact Dubbing prepare/export vertical slice.

### Task 1 — Prepare stage
- Add a prepare action that converts transcript rows into `ExactDubbingRow` objects.
- Preserve `id`, `original`, `start`, and `duration` exactly.
- Keep `burmese` blank until explicitly translated or edited.
- Never route exact rows through narrator summarization.
- Tests: immutable fields, blank Burmese, no row reordering.

### Task 2 — Translation boundary
- Keep exact-dubbing translation separate from narrator translation.
- Add a `TranslationService` adapter boundary for exact rows.
- Gate on optional credentials; label demo work.
- Tests: credential-missing demo fallback, row identity preservation.

### Task 3 — Schema export
- Export `translated_gender.json` with the legacy-compatible schema.
- Validate before writing.
- Use atomic write plus `.partial` rename.
- Tests: schema round trip, missing fields, atomic write.

### Task 4 — TTS and render
- Wrap exact-duration TTS behind `TtsService`.
- Add voice/gender mapping and cache signatures.
- Wrap the exact-duration renderer.
- Validate final duration and audio stream.
- Tests: missing adapter, render failure, output validation.

### Task 5 — UI and validation
- Add prepare/export buttons to the Exact Dubbing panel.
- Show validation summary and render status.
- Add "Open output folder".
- Tests: UI lifecycle, validation gate, output reveal.

## Architecture constraints
- `ui -> application -> services -> domain` only.
- No Qt in `domain` / `application`.
- No self-capturing lambda/partial connected to a signal.
- Never block the GUI thread with FFmpeg/Whisper/TTS/render/model calls.
- Never silently fall back from REAL to DEMO; label demo work and surface REAL failures.
- Never write real-job checkpoints to CWD; use job-scoped paths plus atomic `.partial` rename.
- Never overwrite source media or mutate exact-dubbing source rows.
- No auto-resume; present recovered jobs for explicit user action.
- Exact Dubbing rows: only `burmese` and `gender` are editable.

## Validation
- Focused: `pytest tests/test_exact_dubbing_validation_gate.py tests/test_exact_dubbing_panel.py tests/test_architecture_gates.py`
- Full: `pytest tests -q --confcutdir=tests -p no:cacheprovider`
- Offscreen smoke: `QT_QPA_PLATFORM=offscreen python scripts/check_shell.py`

## Risks
- Legacy exact-dubbing adapter loading can fail on a clean machine; degradation must be honest and logged.
- TTS and render must not report success without a real output file.
- Source identity must remain immutable across prepare/export.

## Out of scope for this slice
- Splitter planner and per-part resume.
- Common Editing timeline, overlays, and export validation.
- Windows packaging, diagnostics, and clean-machine testing.
- Real-media Whisper acceptance and restart-to-Workspace checks.
- Narrator real adapter wiring beyond the current honest fallback.

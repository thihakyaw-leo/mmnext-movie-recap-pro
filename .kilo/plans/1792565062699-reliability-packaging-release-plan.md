# Reliability, Packaging, and Release Plan

## Goal
Close Phase 8 by adding startup diagnostics, crash-safe recovery, structured log export, small-media end-to-end tests, Windows packaging, and release validation without changing mode contracts.

## Scope
- Startup diagnostics for Python/runtime, FFmpeg, mpv, GPU/NVENC, TTS connectivity, and optional translation credentials.
- User-facing diagnostics report.
- Crash-safe recovery and orphan partial-file cleanup.
- Structured log export.
- End-to-end tests using small fixture media.
- Windows packaging strategy.
- CPU-only, NVIDIA, non-ASCII path, and Myanmar text validation.
- Pause/stop/resume coverage across major modes.
- User guide and migration notes.

## Ordered Tasks
1. Add a diagnostics service that probes runtime dependencies and returns a structured report.
2. Wire diagnostics into Settings and startup status chips.
3. Add orphan partial-file cleanup on startup and after failed runs.
4. Add structured log export from the log drawer.
5. Add small fixture media and end-to-end tests for transcript, narrator, exact dubbing, splitter, and common editing.
6. Define Windows packaging approach and build scripts.
7. Validate on CPU-only and NVIDIA machines.
8. Validate non-ASCII paths and Myanmar text round-trips.
9. Validate pause/stop/resume across major modes.
10. Write user guide and migration notes.
11. Run full suite, smoke tests, and release checklist.

## Failure Modes
- Diagnostics must not block startup or require network.
- Cleanup must not delete committed artifacts or source media.
- Packaging must preserve jobs root and runtime tool discovery.
- Tests must remain offline and skip opt-in real media gracefully.

## Validation
- Focused diagnostics and recovery tests.
- Architecture gates.
- Full suite.
- Offscreen smoke.
- Manual packaging and clean-machine smoke.

## Open Questions
- Whether diagnostics should be a separate screen or part of Settings.
- Whether packaging uses PyInstaller, cx_Freeze, or an installer wrapper.
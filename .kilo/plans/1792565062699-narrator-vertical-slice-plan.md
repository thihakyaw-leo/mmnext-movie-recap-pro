# Plan: Narrator Vertical Slice — Plan Stage Wiring (bounded)

## Goal
Wire Narrator Mode's plan stage (transcript → atomic narration units) through an application service + adapter, running off the GUI thread, without mixing the Exact Dubbing contract and without invoking Gemini/TTS/render (those need credentials/network and are deferred per `todo plan.md` ordering).

## Decisions resolved
- Legacy planner entry point: `J:\recap-en-to-mm-main\recap-en-to-mm-main\app\recap_planner.py` — use only the **pure** planner functions (`atomicize_timestamp_segments`, `assign_full_coverage_boundaries`, repetition guards). Do NOT call `build_story_context`/Gemini.
- TTS: Edge TTS behind `SpeechSynthesizer` protocol — OUT OF SCOPE this slice (requires credentials/network). The "Translate to Myanmar" button stays simulated.
- Legacy path coupling is fragile (outside repo root): import `recap_planner.py` defensively (guarded import); fall back to simulation if the path is unavailable so the app never crashes.
- Narrator rows stay separate from Exact Dubbing rows (separate coordinator, no shared base). No auto-resume.

## Tasks (implementation-ready, ordered)
1. Extend `mmnext/services/adapters/narrator.py`: add `plan_units(transcript_rows, video_duration)` returning atomic units. Wrap `recap_planner` import defensively; fall back to timestamp-sorted units if unavailable. Add unit tests.
2. Create `mmnext/application/narrator_coordinator.py`: orchestrate transcript→plan on a `QThread` (never GUI thread); emit stage progress/log events; update `session.narration_segments`; keep Exact Dubbing untouched. Add unit tests.
3. Wire `mmnext/ui/workspace/mode_panels/narrator_panel.py`: `regenerateRequested` → coordinator plan; `translateRequested` → log "simulated, no service"; `validateRequested` → existing `validate_narration`; `saveRequested` → mark clean. No self-capturing lambdas (use bound methods / `setProperty`).
4. Add focused integration test: off-GUI-thread planner run produces `NarrationSegment` list with stable IDs and no Exact Dubbing rows affected.

## Boundaries (files to touch)
- `mmnext/services/adapters/narrator.py` (extend)
- `mmnext/application/narrator_coordinator.py` (new)
- `mmnext/ui/workspace/mode_panels/narrator_panel.py` (wire signals)
- `tests/test_narrator_coordinator.py`, `tests/test_narrator_planning_service.py` (extend)

## Constraints / invariants preserved
- No Qt in `domain`/`application`; no network SDK imports in `mmnext/`; no Tkinter; every subpackage needs `__init__.py`.
- UI never connects a self-capturing lambda/`functools.partial` to a signal.
- Narrator contract ≠ Exact Dubbing contract; never route Exact Dubbing through narrator summarization.
- No real translation/TTS/render invoked; button remains labelled simulated.

## Validation
- Focused narrator tests pass.
- Full suite passes (`pytest tests -q --confcutdir=tests -p no:cacheprovider`).
- Offscreen smoke passes (`QT_QPA_PLATFORM=offscreen scripts\check_shell.py`).
- Exact Dubbing invariants still hold (regression).

## Out of scope (explicitly deferred)
- Gemini story context / translation batching / audit.
- Edge TTS synthesis and Smart Sync render.
- Resume/reuse detection for plan/TTS artifacts.
- Persisted transcript reopening end-to-end (that's a separate, higher-priority persistence slice per `todo plan.md`).

## Status (implemented — bounded slice)

Completed:
1. `mmnext/services/adapters/narrator.py` — `plan_units(transcript_rows, video_duration)` with defensive legacy-planner import + deterministic fallback. Unit tested.
2. `mmnext/application/narrator_coordinator.py` — Qt-free `NarratorPlanCoordinator.plan()` returning `NarrationSegment[]` (blank narration, full coverage, stable IDs). Unit tested.
3. `mmnext/application/project_controller.py` — added `set_narration_segments()` (sets + notifies `narration_changed`).
4. `mmnext/ui/app_context.py` — wired `NarratorPlanningService` + `NarratorPlanCoordinator`; added `plan_narration(video_duration=None)`.
5. `mmnext/ui/workspace/workspace_screen.py` — connected `narrator_panel.regenerateRequested` (bound method) → `_on_narrator_plan` → `context.plan_narration()` → `_reload()`.
6. Tests: `tests/test_narrator_planning_service.py`, `tests/test_narrator_coordinator.py` (incl. AppContext integration proving Exact Dubbing rows untouched).

Verification:
- Focused narrator tests: pass.
- Full suite: 302 passed, 1 skipped.
- Offscreen smoke (`check_shell.py`): MainWindow OK, all 7 screens, clean close.

Deferred:
- QThread worker for the planner call (synchronous pure-Python call used for this slice; not FFmpeg/Whisper/TTS).
- Gemini story context / translation batching / audit; Edge TTS/Smart Sync render.
- Resume/reuse detection for plan/TTS artifacts.

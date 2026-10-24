# Narrator Priority Slice Plan

## Goal
Complete the highest-priority narrator gaps: segment-level stop in translate/synthesize, disk-cache reuse detection, batch-folder queue, selected-segment save/re-render, translation audit UI, and final video validation/output reveal. Keep changes within narrator boundaries and preserve REAL/DEMO separation, no GUI thread blocking, and Exact Dubbing immutability.

## Scope
- `mmnext/application/narrator_pipeline_coordinator.py` - per-segment stop checks, stronger cache lookup, audit/warnings
- `mmnext/services/adapters/narrator_tts.py` / cache handling
- `mmnext/application/narrator_coordinator.py` and job/queue plumbing
- `mmnext/ui/narrator_pipeline_worker.py`, `mmnext/ui/app_context.py`
- `mmnext/ui/workspace/mode_panels/narrator_panel.py`, `mmnext/ui/workspace/inspector.py`
- `mmnext/ui/workspace/workspace_screen.py`
- `tests/test_narrator_pipeline*.py`, new tests as needed

## Decisions
1. **Segment-level stop**: already partially present in coordinator; ensure translate loop checks stop after each unit (done in current code) and synthesize checks per segment (done). Add explicit checks before/after calls and in UI worker. 
2. **Disk-cache reuse**: coordinator already checks cache via `cache_key()` and `_cached_audio()`; ensure cache root is consistent and reused segments are reported. Add cache directory under job-scoped paths.
3. **Batch-folder queue**: add simple queue in AppContext/job manager for narrator batch runs (separate from download queue).
4. **Selected-segment save/re-render**: allow re-running pipeline for a single segment or update narration and re-synthesize/render that segment.
5. **Translation audit UI**: surface `warnings` from coordinator as audit findings in inspector/panel.
6. **Final validation & output reveal**: already validate REAL renders; add output reveal (open folder/file) action.

## Ordered Tasks
1. Inspect narrator panel/inspector and worker to see current UI wiring.
2. Harden coordinator stop checks and cache reuse reporting.
3. Add batch queue support in AppContext.
4. Add selected-segment re-render path.
5. Wire translation audit display in UI.
6. Add output reveal action.
7. Add/update tests.
8. Run focused narrator tests, full suite, smoke.

## Validation
- `tests/test_narrator_pipeline.py tests/test_narrator_pipeline_ui.py`
- Full suite
- Offscreen smoke

## Risks
- Must not touch Exact Dubbing working set
- Cache must be job-scoped
- Reuse must not hide failures
- Stop must be responsive at segment boundaries
# Common Editing Workspace Plan

## Goal
Implement the Phase 7 Common Editing vertical slice on top of the existing `AppContext`, `ProjectController`, and mode-switching UI, without changing the narrator or exact-dubbing contracts.

## Scope
- Non-destructive timeline/range model.
- Trim and range selection.
- Overlay model and preview positioning.
- Title/logo/extra text/blur-box support.
- Ratio/fill/zoom/flip controls.
- Export preset model.
- Export validation and final artifact inspection.
- UI wiring in `mode_panels/common_editing_panel.py` and workspace screens.
- Tests for model behavior, UI bindings, validation, and off-GUI-thread export.

## Affected Boundaries
- `domain`: add typed models for timeline range, overlay, and export preset; keep models pure.
- `application`: add `CommonEditingService`/coordinator for non-destructive operations and export orchestration.
- `services`: add adapter boundary for FFmpeg-based common-editing export, with demo and real variants.
- `ui`: wire controls through `AppContext`; no direct infrastructure import.
- `tests`: add common-editing model, service, worker, UI, and architecture-gate coverage.

## Ordered Tasks
1. Inspect existing common-editing panel and overlay models; identify reusable FFmpeg helpers.
2. Add domain models: `TimelineRange`, `Overlay`, `ExportPreset`, and validation helpers.
3. Add application service/coordinator for trim/range/overlay/export operations.
4. Add demo adapter and real FFmpeg export adapter behind a protocol.
5. Wire `AppContext` methods and signals.
6. Wire Common Editing panel controls and inspector.
7. Add export worker and progress/log handling.
8. Add validation for output duration, streams, and overlay bounds.
9. Add tests and run focused suite.
10. Run full suite and offscreen smoke.

## Failure Modes
- Export must not overwrite source media.
- Invalid ranges or overlays must be rejected before render.
- Demo and REAL work must be labelled honestly.
- No heavy export work on the GUI thread.
- No silent REAL→DEMO fallback.

## Validation
- Focused common-editing tests.
- `tests/test_architecture_gates.py`.
- Full suite.
- Offscreen smoke via `scripts/check_shell.py`.

## Open Questions
- Whether overlays should be persisted in `ProjectSession` or a separate sidecar file.
- Whether export presets should be user-editable or fixed for the first release.
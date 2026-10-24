# Splitter Mode Integration

## Recommendation
Implement the next roadmap slice as **Splitter mode integration**: legacy split planning, smart-cut/short-tail rules, part rendering, per-part status, and resume. Exact Dubbing and Narrator slices are already implemented; Splitter is the next incomplete mode in the priority order.

## Scope
- Wrap the legacy splitter planner behind a protocol and adapter.
- Plan output parts with cut reasons: exact, pause, breath, quietest, end.
- Apply short-tail merge and maximum-extra-wait rules.
- Render selected parts with ratio, fill, text, and part-number overlays.
- Track per-part status and resume from the correct part.
- Skip unchanged parts using source/settings fingerprints.
- Add worker-thread execution and UI wiring.

## Affected Boundaries
- `mmnext/services/protocols.py`
- `mmnext/services/adapters/splitter.py` or equivalent
- `mmnext/application/splitter_coordinator.py` or equivalent
- `mmnext/ui/app_context.py`
- `mmnext/ui/splitter_render_worker.py` or equivalent
- `mmnext/ui/workspace/mode_panels/splitter_panel.py`
- `mmnext/ui/workspace/workspace_screen.py`
- Tests under `tests/test_splitter*.py`

## Design Decisions
- Keep splitter planning separate from narrator and exact-dubbing contracts.
- Plan first, render only after the user sees planned parts.
- Preserve source media; write each part through a partial path.
- Resume only when the checkpoint and fingerprint match.
- Skip a part only when its fingerprint and settings match.
- CPU fallback is allowed when NVENC is unavailable.

## Data Flow
1. Analyze source duration and selected part duration.
2. Plan parts with cut reasons and short-tail handling.
3. Show planned parts before rendering.
4. Render selected parts with ratio, fill, text, and part number.
5. Persist per-part status and checkpoint progress.
6. Resume or skip parts based on fingerprint and settings.

## Failure Modes
- Invalid part duration: planning is rejected before rendering.
- Missing FFmpeg: render fails with a clear dependency error.
- NVENC unavailable: fall back to CPU encoding.
- Stop request: stop at the next part boundary and keep completed parts.
- Checkpoint mismatch: restart the affected part instead of reusing stale output.
- Short-tail merge: tested explicitly.

## Validation
- `.venv\Scripts\python.exe -m pytest tests\test_splitter*.py -q --confcutdir=tests`
- `.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider`
- `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe scripts\check_shell.py`

## Open Questions
- Should smart cut and maximum extra wait be user-editable in the first splitter slice?
- Should per-part resume reuse completed FFmpeg segments or restart each affected part?
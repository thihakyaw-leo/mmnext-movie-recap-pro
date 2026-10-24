# Exact Dubbing TTS, Render, Cache, and Validation

## Recommendation
Implement the next roadmap slice as **Exact Dubbing TTS/render/cache/speech fitting and final output validation**. Export already exists; the missing production work is generating Burmese speech per locked source row, fitting it to each source duration, rendering the final video, and validating duration/audio output without mutating source rows.

## Scope
- Add exact-dubbing TTS and render adapters behind protocols.
- Synthesize one Burmese audio segment per validated `ExactDubbingRow`.
- Fit each synthesized segment to its locked source duration and log speed-fit warnings.
- Render `final_exact_gender_dub.mp4` with source frames/timing preserved.
- Validate final output existence, non-empty size, audio stream, and duration tolerance.
- Add cache reuse keyed by Burmese text, voice, and rate.
- Add a worker-thread render flow and UI state/reporting.

## Affected Boundaries
- `mmnext/services/protocols.py`
- `mmnext/services/adapters/exact_dubbing_tts.py` or equivalent
- `mmnext/services/adapters/exact_dubbing_render.py` or equivalent
- `mmnext/application/exact_dubbing_render_coordinator.py` or equivalent
- `mmnext/ui/app_context.py`
- `mmnext/ui/exact_dubbing_render_worker.py` or equivalent
- `mmnext/ui/workspace/mode_panels/exact_dubbing_panel.py`
- `mmnext/ui/workspace/workspace_screen.py`
- Tests under `tests/test_exact_dubbing*.py`

## Design Decisions
- Exact rows remain immutable: only `burmese` and `gender` are editable.
- Render is blocked until `validate(AppMode.EXACT_DUBBING)` has no errors.
- TTS runs one row at a time; source timing is never changed to fit speech.
- Speech fitting may adjust TTS rate within a documented maximum and emits warnings.
- Final output is written through a `.partial` path and renamed only after validation.
- Demo adapters must remain fully offline and clearly labelled.
- Real adapters report failure honestly; no fake success.

## Data Flow
1. Validate exact rows.
2. For each row, synthesize Burmese audio using the gender-mapped voice.
3. Reuse cached audio when the cache key matches.
4. Fit speech to the locked source duration and record warnings.
5. Render source video with fitted audio to a partial output.
6. Validate output existence, size, audio stream, and duration.
7. Rename to `final_exact_gender_dub.mp4` only after validation.

## Failure Modes
- Missing TTS dependency: run fails or remains DEMO-labelled.
- Synthesis failure: row-level failure with no partial completion claim.
- Excessive speed fit: validation warning or failure according to configured tolerance.
- Missing audio stream: render fails.
- Duration mismatch beyond tolerance: render fails.
- Stop request: stop at the next row or render boundary and preserve partial output.

## Validation
- `.venv\Scripts\python.exe -m pytest tests\test_exact_dubbing_validation_gate.py -q --confcutdir=tests`
- `.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider`
- `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe scripts\check_shell.py`

## Open Questions
- What maximum TTS speed-fit ratio should be allowed before failing?
- Should speech fitting use per-row rate adjustment only, or also pause trimming?
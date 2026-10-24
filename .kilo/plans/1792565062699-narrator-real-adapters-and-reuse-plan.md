# Narrator Heavy Integration — Real Adapters and Validation

## Recommendation
Implement the next roadmap slice as **Narrator heavy integration part 2** before Exact Dubbing TTS/render. The narrator pipeline skeleton, protocols, demo adapters, coordinator, worker, and UI already exist; the remaining work is to make the real adapters honest, cached, resumable, and validated.

## Scope
- Wire real narrator adapters behind the existing `TranslationProvider`, `SpeechSynthesizer`, and `SmartSyncRenderer` protocols.
- Add story context and glossary handling to translation.
- Add deterministic translation batching and checkpointing.
- Add segment-level TTS cache reuse and voice discovery.
- Add Smart Sync output validation and output reveal.
- Preserve the Exact Dubbing contract and never route narrator rows through it.

## Affected Boundaries
- `mmnext/services/adapters/narrator_translation.py`
- `mmnext/services/adapters/narrator_tts.py`
- `mmnext/services/adapters/narrator_render.py`
- `mmnext/application/narrator_pipeline_coordinator.py`
- `mmnext/ui/app_context.py`
- `mmnext/ui/narrator_pipeline_worker.py`
- `mmnext/ui/workspace/mode_panels/narrator_panel.py`
- Tests under `tests/test_narrator_pipeline*.py`

## Design Decisions
- Keep adapters behind protocols; the UI and coordinator must not import legacy modules directly.
- Use real adapters only when `available()` is true and required credentials/tools exist; otherwise use clearly labelled demo adapters.
- Never report a failed or skipped render as successful.
- Keep translation on `NarrationSegment`, never `ExactDubbingRow`.
- Reuse TTS cache by `cache_key(text, voice, rate)`.
- Stop at stage and segment boundaries; preserve partial results.
- Write final output through partial-file handling and validate before completion.

## Data Flow
1. Load transcript rows and plan narrator segments.
2. Translate each batch with deterministic batch IDs and checkpoint partial results.
3. Synthesize each segment, reusing cache when the key matches.
4. Render Smart Sync output to a temporary path.
5. Validate output existence, audio stream, and duration tolerance.
6. Commit final output only after validation passes.

## Failure Modes
- Missing Gemini credentials: adapter reports unavailable; UI remains DEMO-labelled.
- Missing `edge_tts`: no audio is produced and the run fails honestly.
- Missing legacy render entry point: render returns `False`.
- Missing or invalid source media: fail before translation.
- Stop request: stop at the next stage or segment boundary and retain partial output.
- Cache corruption: regenerate and replace the affected cache entry.

## Validation
- `.venv\Scripts\python.exe -m pytest tests\test_narrator_pipeline.py tests\test_narrator_pipeline_ui.py -q --confcutdir=tests`
- `.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider`
- `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe scripts\check_shell.py`

## Open Questions
- Which Gemini credential source and model name should the real translation adapter require?
- Should translation checkpoints be stored under the narrator job directory or a dedicated cache root?
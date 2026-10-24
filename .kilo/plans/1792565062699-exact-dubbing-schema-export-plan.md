# Exact Dubbing schema export slice

## Goal
Add schema-compatible `translated_gender.json` export for Exact Dubbing rows, with validation gating, without connecting TTS/render.

## Scope
- Export each `ExactDubbingRow` as a JSON object with keys `id`, `start`, `duration`, `original`, `burmese`, `gender`.
- Preserve immutable fields verbatim from the prepared rows.
- Validate rows before export; refuse export when validation has errors.
- Write atomically to the job/output folder.

## Non-goals
- No translation service.
- No TTS/render/cache/speed fitting.
- No output video validation.

## Affected boundaries
- Domain: `ExactDubbingRow` serialization only; no model changes.
- Application: `ProjectController.export_exact_dubbing(path)` or `AppContext.export_exact_dubbing()`.
- UI: Exact Dubbing panel gets an `Export schema` action or reuse existing save button with export path.
- Infrastructure: `atomic_write_json`.

## Data flow
1. User prepares exact rows.
2. User edits burmese/gender.
3. Validation passes.
4. Export writes `translated_gender.json` to `session.output_folder` or job exact-dubbing directory.
5. UI shows output path / errors.

## Failure modes
- No project/session/rows: raise ValueError.
- Validation errors: refuse export and return report.
- Missing output folder: use jobs dir fallback or require explicit path.
- Atomic write failure: leave previous file intact.

## Validation
- Focused tests for export shape, immutable preservation, validation gating.
- Run full suite and offscreen smoke after implementation.
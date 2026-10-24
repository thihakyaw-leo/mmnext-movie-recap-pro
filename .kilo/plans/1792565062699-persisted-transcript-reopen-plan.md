# Plan: Persisted Transcript Reopening & Job Recovery (end-to-end)

## Goal
Make completed REAL transcript jobs discoverable and reopenable with truthful validation, off-GUI-thread loading, and Exact Dubbing invariants preserved. No translation/TTS/render.

## Constraints (from todo plan.md + AGENTS.md)
- No auto-resume; opening is explicit.
- No demo fallback on any failure path.
- Persisted transcript reopening must not mutate source rows.
- Source/config/tests authoritative over docs.

## Tasks (ordered)
1. Configure persistent user-writable jobs root at normal startup (currently `AppContext` defaults to `~/.mmnext/jobs` / `MMNEXT_JOBS_DIR`; verify `MainWindow` does not override). Keep demo mode explicit.
2. Persist a versioned REAL transcript `Job` record (COMPLETE + artifact location) only after transcript validation + atomic artifact commit succeed. (Already partially in `_on_transcript_result` — verify completion gate rejects invalid timestamps.)
3. Repository-backed Jobs listing includes eligible completed REAL transcript jobs + recoverable incomplete jobs. Opening remains explicit. (Already scanned in `_load_recoverable_jobs_from_repo` — verify completed non-demo filter.)
4. Harden reopen validation in `open_transcript_from_job`: source identity/fingerprint, mode, schema, completion state, row uniqueness, timing bounds; reject without demo fallback or source-row mutation. (Already implemented — add tests for corrupt/missing/incompatible.)
5. Move artifact reading/validation off the GUI thread (worker thread) and bind results only if selected job/source still current. (Currently synchronous — needs QThread worker + stale-result guard.)
6. Add UI/integration tests: normal startup, completed-job discovery, explicit open, corrupt/missing/incompatible artifacts, source/fingerprint/mode mismatch, no demo fallback, off-GUI-thread loading, Exact Dubbing invariants.

## Boundaries (files to touch)
- `mmnext/ui/app_context.py` (jobs root, scan, reopen)
- `mmnext/ui/main_window.py` (jobs_dir wiring if needed)
- `mmnext/infrastructure/repository/job_repository.py` (completed scan — already present)
- `mmnext/ui/transcript_worker.py` (new reopen worker)
- `tests/test_transcript_open.py` (extend)
- `tests/test_live_transcript_workspace.py` (extend)

## Validation
- Focused transcript + jobs tests pass.
- Full suite passes.
- Offscreen smoke passes.
- No demo fallback on any failure path.

## Out of scope
- Translation, TTS, final video rendering.
- Router/Nemotron review (separate authorized task).
- Clean-machine installation / GPU tests.
# MMNext Movie Recap Pro — Persisted Transcript Reopen Hardening

## Goal
Make persisted transcript reopening/recovery **real end to end** (Per `todo plan.md` "Highest-priority next work" §), BEFORE narrator heavy integration. Do not begin translation/TTS/render until this slice has a truthful end-to-end acceptance path.

## Ordering (per todo plan.md)
1. Persisted transcript reopen/recovery end-to-end ← this plan
2. Narrator heavy integration (Gemini story context, translation batching, Edge TTS, Smart Sync render) ← follow-up, out of scope here

## Current state (verified, source-checked)
- `JobRepository.scan()` returns `recoverable`, `completed`, `completed_real`, `corrupt`; `list_completed_real()` filters by source.
- `AppContext` always resolves jobs root (`$MMNEXT_JOBS_DIR` else `~/.mmnext/jobs`) and constructs `JobRepository` at startup; scans on every startup.
- Completed REAL Job records persist after a successful transcript (job_id, fingerprint, artifact_path, is_demo=False, state=COMPLETE).
- `ReopenTranscriptThread` + `open_transcript_from_job()` exist; reopen runs off the GUI thread.
- Canonical fingerprint `mmnext/domain/fingerprint.py::canonical_fingerprint` (fp2:) is single source of truth; artifact carries `mode`, `fingerprint_settings`, `fingerprint_source_type`, `fingerprint_schema_version`.
- Full suite: 342 passed, 1 skipped (media fixture dependent).

## What is still NOT true (blockers — must fix)
1. **Reopen rejects every REAL artifact.** `open_transcript_from_job` recomputes fingerprint via `compute_fingerprint(source_path, source_type, mode, schema_version=1)` WITHOUT settings, but the artifact was written WITH settings (`language`/`auto_detect`/`model`/`schema`). Real artifacts fail `ValueError: Fingerprint mismatch between artifact and current source` (verified).
2. **Artifact mode not compared.** Artifact carries `mode`; reopen does not check it vs persisted Job mode / workspace mode.
3. **Legacy artifacts not rejected explicitly.** An artifact without `fp2:` prefix / new keys is unverifiable and must be refused with "legacy artifact — re-transcribe required".
4. **No artifact path containment check.** Reopen does not verify the artifact lives inside the job's expected directory.
5. **No stale-result guard binding.** Reopen result must be bound only if the selected job/source is still current.
6. **Jobs screen wiring incomplete.** `completed_real` jobs are added to `JobManager` at startup, but the Jobs screen does not yet offer an explicit "open transcript" action for completed REAL jobs.

## Decisions (resolved)
- Follow `todo plan.md` ordering: persistence/recovery hardening BEFORE narrator heavy integration.
- Reuse the existing `canonical_fingerprint` + artifact `fingerprint_settings`/`fingerprint_source_type`/`fingerprint_schema_version` for re-derivation; do NOT invent a second algorithm.
- No demo fallback, no silent REAL→DEMO, no source-row mutation on rejection. Rejections surface clear messages.
- Reopen stays an explicit user action; never auto-resume.
- Keep `open_transcript_from_job()` as the synchronous validation core; `ReopenTranscriptThread` runs it off GUI thread.

## Implementation plan (ordered tasks)

### 1. Fix fingerprint re-derivation in open_transcript_from_job (`mmnext/ui/app_context.py`)
- When validating, read artifact's `fingerprint_settings`, `fingerprint_source_type`, `fingerprint_schema_version`.
- Recompute `canonical_fingerprint(source_path, fingerprint_source_type, mode, settings=fingerprint_settings, schema_version=fingerprint_schema_version)`.
- Compare to artifact's `fingerprint`. Reject mismatch without demo fallback.
- Keep backward compat: if artifact lacks settings fields, treat as legacy (see task 3).

### 2. Add artifact mode comparison (`mmnext/ui/app_context.py`)
- Read artifact `mode`; compare to persisted `job.mode` and the workspace/current mode.
- Reject on mismatch with a clear message ("artifact mode <X> does not match job mode <Y>").

### 3. Reject legacy artifacts explicitly (`mmnext/ui/app_context.py`)
- Before fingerprint compare, require `is_canonical_fingerprint(artifact_fp)` (fp2: prefix + 40 hex).
- If artifact lacks `mode`/`fingerprint_settings` keys or has non-fp2 fingerprint → raise `ValueError("Legacy transcript artifact — re-transcribe required")`.

### 4. Add artifact path containment check (`mmnext/ui/app_context.py`)
- Compute expected artifact directory from `JobRepository` layout (`<job_dir>/<mode.value>/transcripts/<stem>.transcript.json`).
- Verify `artifact_path` resolves inside that expected directory (use `os.path.commonpath` / `Path.relative_to` against expected parent). Reject escapes.

### 5. Add stale-result guard to reopen (`mmnext/ui/app_context.py` + `mmnext/ui/reopen_transcript_worker.py`)
- Track the "current reopen token" (job_id + source_path) on `AppContext`.
- Before applying the reopen result (emitting `transcriptReopened(session, "")`), verify the token still matches the job/source being opened; if source/session changed meanwhile, reject as stale.

### 6. Wire Jobs screen "open transcript" for completed REAL jobs
- `mmnext/ui/screens/jobs_screen.py`: add an explicit action (button/menu) on completed REAL job rows that calls `AppContext.start_reopen_transcript(job_id, source_path)`.
- Only enabled for `state == COMPLETE` and `not is_demo`. No auto-resume.

### 7. Tests (`tests/`)
Add/update integration tests covering:
- `test_reopen_real_artifact_uses_artifact_settings` — REAL adapter-produced artifact reopens successfully (fp match via fingerprint_settings).
- `test_reopen_rejects_mismatched_settings` — artifact fingerprint vs recomputed with wrong settings rejected.
- `test_reopen_rejects_mode_mismatch` — artifact mode vs job mode mismatch rejected.
- `test_reopen_rejects_legacy_artifact` — artifact without fp2:/new keys → "legacy artifact — re-transcribe required".
- `test_reopen_rejects_artifact_path_escape` — artifact outside expected job dir rejected.
- `test_reopen_stale_result_guard` — source/session changed between start and result → not applied.
- `test_reopen_off_gui_thread` — `start_reopen_transcript` emits result via signal, no GUI blocking.
- `test_jobs_screen_offers_open_for_completed_real` — completed REAL job row exposes open action; demo/cancelled do not.
- Keep `tests/test_transcript_open.py` passing (existing 6 tests).

## Validation plan
- Run `.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider` → expect 342+ passed, 1 skipped (unchanged skip).
- Run focused reopen tests: `pytest tests/test_transcript_open.py tests/test_job_repository.py -q --confcutdir=tests -p no:cacheprovider`.
- `QT_QPA_PLATFORM=offscreen .\.\venv\Scripts\python.exe scripts\check_shell.py` → MainWindow OK, clean close, exit 0.
- Confirm a REAL adapter-written artifact (from `WhisperTranscriptAdapter`) reopens via `start_reopen_transcript` end-to-end (off GUI thread).

## Risks / open questions
- `pyproject.toml` setuptools `packages` omits `mmnext.infrastructure.repository` and `mmnext.services.adapters` (non-editable install broken). Not part of this slice; noted for release hardening.
- No clean-machine installation test performed yet (Phase 8).
- Narrator heavy integration is explicitly deferred until this slice is end-to-end complete.

## Rollout / migration
- No data migration: legacy artifacts (pre-fp2) are refused with a clear message; users re-transcribe. Completed REAL jobs already on disk remain discoverable.
- No auto-resume: opening a discovered job remains an explicit user action.

---
Plan location: `.kilo/plans/1792565062699-persisted-transcript-reopen-hardening.md`

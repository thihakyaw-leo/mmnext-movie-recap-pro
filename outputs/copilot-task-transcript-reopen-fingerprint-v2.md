# GitHub Copilot coding task — REAL transcript restart discovery and canonical fingerprint (verified update)

Use this prompt in the MMNext Movie Recap Pro repository with the user-selected GitHub Copilot coding model. Nemotron is the separate Planner/reviewer. Do not claim Copilot is using Nemotron or another model unless that model is actually selected in Copilot.

## Task

Complete exactly one bounded vertical slice: make a completed REAL transcript discoverable after restart and safely reopenable only when the persisted Job, transcript artifact, mode, current source, and canonical fingerprint agree.

Do not replan the project, implement later modes, or review/approve your own work. Before editing, read the current `Agent.md`, `instructions.md`, `todo plan.md`, `checklist.md`, `README.md`, `AGENT_HANDOFF.md` if present, and all applicable `AGENTS.md` files. Inspect the current source and tests before trusting the audit notes below.

## Fresh evidence and corrected current state

A recent read-only inspection found the following in the current repository:

- The stable jobs root is already configured in `AppContext` as `Path.home() / ".mmnext" / "jobs"` when no test root is injected. `MainWindow` constructs `AppContext()`, and `AppContext` creates the repository and runs its startup scan. **Do not reimplement this or claim that `jobs_dir` is absent.**
- The startup scan is wired, but `JobRepository.scan()` returns only non-COMPLETE/non-CANCELLED records in its `recoverable` collection. Completed jobs therefore are not surfaced as completed transcript jobs in the normal Jobs screen. Add a distinct completed-REAL discovery path; do not mix completed jobs into resume eligibility.
- The current fingerprint implementations disagree. `SourceType.LOCAL_FILE.value` is `"local_file"`, but `JobRepository.compute_fingerprint()` stats a file only when the type is `"local"`. The transcript adapter instead hashes a resolved path, size, nanosecond mtime, mode, and transcription settings. `AppContext.open_transcript_from_job()` compares the repository calculation to the adapter artifact value. The result can reject a transcript produced by the real adapter.
- Existing `tests/test_transcript_open.py` helper writes artifacts using `JobRepository.compute_fingerprint()`. It does not exercise the fingerprint emitted by `WhisperTranscriptAdapter`; its passing tests are not proof that a real adapter-produced artifact can reopen.
- The `Job` dataclass currently has no fingerprint field. Serialization writes `getattr(job, "fingerprint", "")`, but deserialization does not restore one. Transcript completion computes a fingerprint but does not store it on the Job; persistence errors are swallowed.
- The app-context open path reads and validates artifact JSON synchronously, has a no-op state check that consults the in-memory JobManager even for a disk-only record, and the transcript artifact currently lacks a mode field. Row validation at reopen does not check unique IDs, finite values, or authoritative duration bounds.
- The Nemotron report supplied earlier recorded `2 failed, 288 passed, 1 skipped`. A newer independent run in the current workspace on 2026-10-21 instead reported `290 passed, 1 skipped in 59.86s`. Treat both as dated evidence, not a future expected count. Re-run tests before and after your changes. A green suite does not prove this task is complete until tests exercise a REAL adapter-produced artifact through restart and reopen.
- The workspace currently has no `.git` directory. Do not assume `git status` or `git diff` is available, do not initialize a repository, and do not change branches.

These notes are leads from a read-only audit, not substitutes for tracing the current implementation yourself. If the live code has changed, report the evidence and adapt the work order without reintroducing already-fixed defects.

## Required implementation

### 1. One canonical fingerprint contract

- Establish one canonical fingerprint function and use it from the transcript adapter, JobRepository, transcript completion, transcript reopen, and checkpoint/resume validation. Do not keep parallel algorithms copied into separate classes.
- Correctly recognize the actual `local_file` source type. Include a safely normalized/canonical source identity and real source file metadata (at least size and a sufficiently precise modification timestamp) for local media; handle unavailable files by rejecting reopen/resume instead of treating zero metadata as a valid match.
- Include the mode, artifact/checkpoint schema, and relevant transcript settings consistently. Store or otherwise make available the settings needed to recompute a fingerprint. Ensure all callers use the same input values and canonical serialization.
- Add deterministic tests that use an actual artifact emitted by the REAL transcript adapter (with fake/local providers as needed), then verify that the same source opens and a changed or missing source is rejected. Do not construct every test artifact from the same repository helper being tested.
- Confirm that checkpoint `can_resume_job` uses the same canonical contract and does not introduce regressions. Safely handle legacy checkpoints whose previous fingerprint scheme cannot be verified; never bless a mismatch by disabling validation.

### 2. Persist Job fingerprint and completion truthfully

- Add a backward-compatible `fingerprint` field to the Job domain model and round-trip it through JobRepository serialization/deserialization. Existing versioned metadata without the new field must load safely with an explicit empty/legacy value.
- Persist the matching fingerprint and source/mode/schema/artifact identity for a REAL transcript Job only after the transcript artifact has been validated and atomically committed. Preserve failure/stopped semantics; never create a misleading COMPLETE record.
- Remove `except Exception: pass` around persistence. Log a useful, secret-free error and show it to the user. If metadata persistence fails, keep the current transcript display behavior safe, but clearly tell the user that restart recovery was not saved; do not represent the job as durably complete.
- Add tests for Job fingerprint round-trip, old metadata loading, write failure visibility, and correct artifact-before-COMPLETE ordering.

### 3. Discover completed jobs without auto-resuming

- Add a repository/startup API that exposes completed REAL transcript jobs separately from incomplete/recoverable and corrupt records. Keep the existing no-auto-resume rule.
- Populate the Jobs screen from persisted records after restart and avoid duplicate IDs when demo jobs are present. Clearly distinguish persisted REAL from DEMO records.
- Permit explicit open of a valid disk-only job. Do not require the completed job to already exist in the in-memory JobManager. Remove the current ineffective `if state differs: pass` logic; validate the authoritative persisted state and any legitimate in-memory consistency requirement explicitly.
- Add fresh-AppContext restart and repeat-refresh/idempotency tests. Opening must remain a user action; never auto-open or auto-resume.

### 4. Validate mode, schema, fingerprint, and rows before binding

- Add the mode to the transcript artifact and verify that artifact mode, persisted Job mode, current workspace mode, and the canonical fingerprint inputs agree.
- Version the artifact format explicitly if the schema changes. Keep old artifacts intact. For legacy artifacts missing mode or using an unverifiable old fingerprint, either implement a safe, tested compatibility path or reject them with a clear recovery/retranscription message. Never silently accept an unverifiable artifact or delete user data.
- Verify COMPLETE state, REAL marker, supported job/artifact schemas, source identity, artifact path containment within the expected job directory, and successful JSON parsing before session mutation.
- Validate every row before binding: nonempty unique IDs, finite timestamps, nonnegative start, positive duration, and end within authoritative media duration when available. Failure must preserve the current project/session and Exact Dubbing source rows exactly.
- Preserve the Exact Dubbing immutable fields `id`, `original`, `start`, and `duration`; only `burmese` and `gender` are editable. Never summarize, omit, reorder, merge, retime, auto-translate, or invent source dialogue.

### 5. Keep artifact I/O off the GUI thread

- Move large artifact loading and validation to a worker using the project's existing QThread pattern. Keep widgets free of business logic.
- Apply the result only if the selected job/source is still current when the worker completes. On any failure or stale result, do not mutate the active session.
- Add a deterministic UI/integration test proving the read/validation path is not executed on the GUI thread and stale results cannot replace a newer selection.

## Scope and invariants

- Implement only the saved REAL transcript persistence/discovery/reopen slice.
- Do not add translation, Gemini, TTS, YouTube downloads, Splitter planning/rendering, Common Editing rendering, new dependencies, theme changes, or broad refactors.
- Preserve UI → application → services → domain layering and the existing architecture gates.
- Never block the PySide6 GUI thread with FFmpeg, yt-dlp, Whisper, TTS, model calls, or large I/O.
- Never silently fall back from REAL to DEMO. Never write real-job data to the working directory. Use job-scoped paths and atomic writes. Never alter source media or delete user artifacts.
- Do not change legacy output conventions without an approved migration. Protect all secrets. Do not commit, push, create a pull request, initialize Git, or edit files under `outputs/` as part of the implementation.

## No-Git review evidence requirement

Because this workspace has no `.git` directory, do not claim to provide a Git diff. Before editing, preserve byte-for-byte baseline copies of every existing file you intend to change under a unique `.work/review-baselines/transcript-reopen-<unique-id>/` directory, maintaining relative paths. Record SHA-256 hashes. After editing, produce a unified diff against those baselines and a changed-file/hash manifest under the same task-specific `.work` directory. Keep these review materials available; do not overwrite an existing baseline directory or remove it. Include their paths in your handoff. Do not copy secrets or user media into the baseline.

## Documentation discipline

Update `todo plan.md` and `checklist.md` only after behavior is actually implemented and verified. Correct the stale statements that normal startup lacks a persistent jobs root and that the latest test run is `291 passed`; preserve dated historical evidence and add a superseding current audit instead of erasing history. Record the exact fresh run from this task. Do not edit prompt files under `outputs/`.

## Tests and acceptance

Run focused tests first and then the full suite. The current workspace baseline observed on 2026-10-21 was `290 passed, 1 skipped in 59.86s`; test collection may change when you add tests, so do not target an obsolete exact total. The optional real-media Whisper smoke may remain skipped if its approved local fixture/model is unavailable; state that honestly.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

Acceptance requires all of the following to be demonstrated: canonical fingerprints match between the REAL adapter and reopen path; changed/missing source and mode/schema mismatch are rejected; completed REAL jobs appear after a fresh application restart; explicit open succeeds for a valid disk-only job; no auto-resume occurs; persistence failures are visible; row/session/Exact Dubbing invariants hold; artifact validation is off the GUI thread; architecture tests pass; and no relevant test failures remain. Passing the full suite alone is not sufficient.

## Required handoff

Return a factual handoff in clear, natural Myanmar Unicode Burmese. Include the acceptance criteria addressed, each changed file and reason, exact test commands/counts, direct evidence for a real adapter-produced artifact surviving a fresh-context restart and explicit open, the `.work` baseline/diff/hash-manifest paths, every unmet criterion, and untested limitations. Do not claim completion unless all acceptance conditions are demonstrated. Do not choose the next task; Nemotron Planner will decide after independent review.

# OpenCode implementation prompt — transcript fingerprint validation and restart discovery

Use **OpenCode CLI** with the exact implementation model **`nvidia/stepfun-ai/step-5-preview`**. Work in the existing authoritative repository at `J:\mmnext-movie-recap-pro`. Do not start a new project or redesign completed foundations.

You are the implementation agent for one narrowly scoped vertical slice: fix saved REAL transcript fingerprint validation and make completed transcript jobs discoverable after application restart, so a user can explicitly reopen a valid transcript from the Jobs screen.

A separate NVIDIA Nemotron review reported these issues: transcript artifacts/checkpoints are persisted, but restart discovery and UI binding are incomplete; reopen does not enforce saved-fingerprint validation; the persisted Jobs state is not reflected by the UI; and restart/error-path test coverage is insufficient. Treat these as findings to verify against the current working tree before editing. Inspect the current source and tests; do not assume the report or roadmap is infallible.

## Required first steps

1. Read `Agent.md`, `instructions.md`, `todo plan.md`, `checklist.md`, and the relevant README sections.
2. Inspect at least `mmnext/ui/app_context.py`, `mmnext/ui/main_window.py`, `mmnext/ui/screens/jobs_screen.py`, `mmnext/infrastructure/repository/job_repository.py`, `mmnext/infrastructure/transcript_adapter.py`, transcript completion callbacks/workers, `mmnext/domain/models.py`, `mmnext/domain/paths.py`, and their focused tests.
3. State a concise implementation plan, naming the persistence root, metadata/artifact write sequence, repository discovery API, UI binding, and tests. Then implement the plan in small changes. Preserve the existing layered design and public contracts unless the inspected code demonstrates a necessary change.

## Behavior to implement

### Stable startup persistence

- Configure a stable, user-writable jobs directory during normal application startup. Inspect current path helpers and application identity/configuration first; prefer the existing convention or an appropriate per-user application-data location. Do not use the process working directory, a temporary folder, a source-media folder, or a silent demo fallback.
- Keep dependency injection for tests: callers must be able to pass a temporary jobs root. Demo and REAL modes must remain visibly and behaviorally separate.
- Ensure the same normal startup configuration is used by transcript creation, repository discovery, Jobs listing, and explicit opening.

### Persist successful transcript jobs

- After the REAL transcript is validated and its transcript artifact has been atomically committed, persist a versioned Job metadata record with state `COMPLETE`, `is_demo=False`, source identity, mode, source/settings/schema fingerprint, artifact location, and the minimum metadata required to locate and validate the artifact later.
- Do not mark a job COMPLETE before the artifact commit and validation succeed. On failure or stop, retain the existing incomplete/failed semantics and do not create a misleading completed record.
- Use existing JobRepository/domain path APIs where possible. Keep writes job-scoped and atomic. Do not modify the source media.

### Restart discovery and explicit open

- Add or extend a repository read/list API that can discover stored completed REAL transcript jobs after restart in addition to the repository’s existing recoverable/corrupt-job scan.
- Keep completed-job discovery separate from resume eligibility. **Never auto-resume** a recovered or completed job.
- Populate the Jobs screen from the persisted repository state on ordinary app startup. Make “Open transcript” available only for a completed REAL transcript whose record and artifact are present and eligible. Opening remains an explicit user action.
- Do not rely only on in-memory demo `JobManager` rows. Avoid duplicate job IDs and ensure refresh/reload does not duplicate entries.
- Do not block the Qt GUI thread with large artifact reads or validation. If the current code performs these synchronously, introduce the smallest worker-based load path consistent with existing `QThread` conventions, and return results/errors to the UI through signals. Do not migrate to QRunnable without a demonstrated need.

### Fingerprint and artifact validation

- Recompute the fingerprint from the current source and the relevant persisted settings/mode/schema using the project’s existing fingerprint helper. Compare it to the saved Job and transcript artifact fingerprints; merely finding a `fingerprint` field is not validation.
- Reject a source that is missing, no longer the same file, or changed since the artifact was produced. Handle Windows path casing/canonicalization safely; do not weaken the check to basename equality.
- Verify the Job is COMPLETE and REAL; verify job/artifact schema compatibility, mode consistency, artifact location within the expected job tree, and successful JSON parsing before binding anything into the active session.
- Validate rows before mutation: nonempty unique IDs; finite start/duration; nonnegative start; positive duration; and end time bounded by authoritative source duration when available. Reject malformed, empty, duplicate, NaN/Infinity, negative, or out-of-range rows.
- On any mismatch or read failure, show a clear user-visible error and preserve the current project/session and all Exact Dubbing source rows. Never silently fall back to demo rows.

### Project invariants

- Preserve Exact Dubbing immutables exactly: `id`, `original`, `start`, and `duration`. Only `burmese` and `gender` may be edited. Reopened source dialogue must not be summarized, omitted, reordered, merged, retimed, translated automatically, or invented.
- Do not add translation, Gemini, TTS, rendering, downloading, or unrelated mode work in this slice.
- Do not expose secrets, change legacy output conventions, delete user artifacts, or commit changes.

## Tests and acceptance

Add focused tests that use temporary jobs roots and prove at minimum:

1. A successful REAL transcript artifact and COMPLETE Job record are persisted atomically in the required order.
2. A newly constructed application/repository discovers the completed record after restart and presents it in the Jobs UI.
3. No job is auto-resumed; opening happens only after explicit user action.
4. A valid unchanged source/fingerprint opens and preserves transcript rows and Exact Dubbing immutable fields exactly.
5. Source identity/fingerprint, mode, job schema, artifact schema, missing artifact, corrupt JSON, demo marker, incomplete state, malformed/duplicate rows, NaN/Infinity, and out-of-range timestamps are rejected without mutating the current session or source rows.
6. Large artifact reading/validation does not run on the GUI thread, and an obsolete result is not applied after the selected source/job changes.
7. Jobs refresh/startup is idempotent and does not duplicate entries.

Use existing test conventions and run focused tests first, then the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

Use only local fixtures/tools. Do not introduce network-dependent tests. If optional real-media/model tests need local environment configuration, report clearly whether they ran or skipped; do not claim they passed when they did not run.

## Completion response

When finished, report in Burmese Unicode:

- what changed and why;
- exact files changed;
- tests run and exact pass/skip/failure counts;
- whether restart discovery, fingerprint comparison, and explicit UI open were verified end to end;
- any remaining limitations.

Do not claim the slice is complete unless the persisted record is discovered by a fresh application context, fingerprint mismatches are rejected, the UI explicitly opens valid artifacts, and the acceptance tests pass.
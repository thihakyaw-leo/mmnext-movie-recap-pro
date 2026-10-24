# GitHub Copilot coding task — persisted transcript restart discovery and fingerprint validation

Use this prompt in GitHub Copilot with the MMNext Movie Recap Pro repository open. If the `mmnext-coder` custom agent is available, select it; otherwise use the current Copilot coding agent. The coding model is whatever model is explicitly selected and available in the user's Copilot environment. Do not claim that Copilot is using Nemotron or Step-5 Preview unless that model is actually selected and available there.

---

Implement the first bounded MMNext task: make saved REAL transcript jobs discoverable after application restart and enforce source/artifact fingerprint validation before a transcript is explicitly reopened in the Production Workspace.

Nemotron is the separate Project Planner and will decide later tasks. Do not replan the project. After you finish, return a factual implementation handoff for an independent reviewer. Do not review or approve your own changes.

## 1. Read and inspect before editing

Read the current repository versions of `Agent.md`, `instructions.md`, `todo plan.md`, `checklist.md`, `README.md`, and any applicable `AGENTS.md` files from the repository root to directories you change.

Inspect the current source and tests before assuming any reported gap is still present. At minimum, inspect:

- `mmnext/ui/app_context.py`
- `mmnext/ui/main_window.py` and `mmnext/bootstrap.py`
- `mmnext/ui/screens/jobs_screen.py`
- `mmnext/infrastructure/repository/job_repository.py`
- `mmnext/infrastructure/transcript_adapter.py` and transcript completion callbacks/workers
- `mmnext/domain/models.py`, `mmnext/domain/paths.py`, and relevant service protocols
- `tests/test_transcript_open.py`, `tests/test_live_transcript_workspace.py`, transcript regression tests, and JobRepository tests

A separate Nemotron review reported that transcript artifacts/checkpoints/fingerprints exist, but restart discovery and UI binding are incomplete, reopen does not compare the current source fingerprint, and restart/error-path coverage is insufficient. Verify every finding against the current code. Treat review notes and documentation as leads, not proof.

Before editing, give a short implementation plan that names the persistent jobs-root choice, metadata/artifact write sequence, repository discovery, UI binding, fingerprint comparison, and focused tests. Then proceed with this task only.

## 2. Required behavior

### Stable persistence root

- Configure one stable, user-writable jobs directory in normal application startup. Inspect existing path conventions and application identity first. Use the project's established per-user application-data convention if available.
- Do not use the current working directory, a temporary directory, or a source-media directory for real-job data. Do not silently switch to demo mode if the real repository cannot be configured.
- Keep explicit jobs-root injection for tests so tests can use isolated temporary folders. Ensure transcript creation, startup discovery, Jobs listing, and reopening use the same configured root.

### Persist completed transcript job metadata

- Verify how REAL transcript artifacts and checkpoints are currently written.
- After transcription succeeds, rows pass validation, and the transcript artifact is atomically committed, persist a versioned REAL Job metadata record with `COMPLETE` state, source identity, mode, fingerprint/schema details, and the artifact location needed for later validation.
- Do not mark the job COMPLETE before the artifact commit and validation succeed. Preserve failure/stopped behavior; never create a misleading completed record for a failed or partial transcript.
- Use existing JobRepository and atomic-write helpers wherever possible. Keep artifacts job-scoped and never modify source media.

### Discover completed jobs after restart

- Add or extend a repository read/list API so a fresh application context can discover completed REAL transcript jobs, as well as the existing incomplete/recoverable and corrupt records.
- Keep completed-job discovery separate from resume eligibility. Never auto-resume a job.
- Wire the normal application startup to the persistent repository and populate the Jobs screen from persisted records. Avoid duplicate rows when demo jobs and persisted jobs share IDs; do not let demo records impersonate REAL persisted jobs.
- Show or enable **Open transcript** only when a completed REAL job and its artifact are present and eligible. Opening must remain an explicit user action.
- Keep test setup deterministic by allowing a temporary jobs root to be passed into the app/repository.

### Validate fingerprints and artifacts before binding

- Recompute the current source fingerprint using existing project helpers and relevant mode/settings/schema information. Compare it with the fingerprint saved in the Job record and transcript artifact. A saved `fingerprint` field alone is not proof of validation.
- Reject a missing or changed source and handle Windows path canonicalization/case safely. Do not compare only filenames or basenames.
- Verify Job state is `COMPLETE`, the Job is REAL, schemas are supported, modes agree, the artifact is inside the expected job directory, and the artifact parses successfully.
- Validate all rows before changing the active session: nonempty unique IDs; finite start and duration; start is nonnegative; duration is positive; end timestamps do not exceed authoritative media duration when it is available. Reject empty, malformed, duplicate, NaN/Infinity, negative, or out-of-range rows.
- On any failure, show a clear user-visible error and preserve the current project/session and its Exact Dubbing source rows. Never silently fall back to demo rows.
- Do not perform large artifact reads or validation on the Qt GUI thread. Follow the existing `QThread` worker pattern if the current loader is synchronous. Prevent stale worker results from replacing a different job/source selected while loading.

## 3. Project invariants and scope boundaries

- Preserve Exact Dubbing source row fields exactly: `id`, `original`, `start`, and `duration` are immutable. Only `burmese` and `gender` are editable.
- Reopening must not summarize, omit, reorder, merge, retime, automatically translate, or invent dialogue.
- Keep Narrator Mode separate from Exact Dubbing.
- Do not add translation, Gemini, TTS, download, splitter-render, common-editing-render, or final-render features in this task.
- Never expose secrets. Do not change legacy output conventions, delete user artifacts, commit, push, or create a pull request.
- Preserve the current architecture. Make small changes and avoid unrelated refactoring or new dependencies.

## 4. Required tests and acceptance criteria

Add focused tests using temporary jobs roots. Prove at least:

1. A successful REAL transcript produces an atomically committed artifact and a COMPLETE Job record in the correct order.
2. A newly constructed application/repository discovers that completed record after restart and displays it in the Jobs screen.
3. Discovery does not auto-resume jobs; opening occurs only after an explicit user action.
4. An unchanged source with matching fingerprints opens successfully and preserves transcript rows and Exact Dubbing immutable fields exactly.
5. Changed/missing source, fingerprint mismatch, mode/schema mismatch, missing artifact, corrupt JSON, demo record, incomplete Job, malformed/duplicate rows, NaN/Infinity, and timestamps outside source bounds are rejected without changing the current session/source rows.
6. Artifact loading/validation does not block the GUI thread, and stale results are ignored if the selected source/job changes.
7. Repeated startup/refresh does not add duplicate Jobs.

Run focused tests first, then the full suite. Use local resources only; do not download models/media or add network-dependent tests.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

Report exact pass, skip, and failure counts. Do not claim optional real-media/model acceptance ran unless it actually ran. If a focused test fails, diagnose it; do not weaken assertions or change unrelated behavior just to pass.

## 5. Completion handoff for Nemotron and the independent reviewer

Return the final report in correct Burmese Unicode. Include:

- What changed and which acceptance criteria it addresses.
- Every changed file and the reason for each change.
- Exact test commands and pass/skip/failure counts.
- Direct evidence that a fresh application context discovers the completed REAL Job, the UI explicitly opens a valid artifact, and a fingerprint mismatch is rejected.
- Any acceptance criteria not met, known risks, or behavior not tested.
- A neutral handoff for independent review, including the complete Git diff or pull-request link if one exists.

Do not choose the next task. Do not claim completion unless restart discovery, explicit opening, fingerprint checks, GUI responsiveness, and the relevant tests are all demonstrated.
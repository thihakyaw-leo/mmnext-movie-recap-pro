# Nemotron independent review prompt — transcript restart/fingerprint task (no-Git workspace)

Use this prompt in a separate Nemotron review session after GitHub Copilot returns the updated transcript persistence/reopen work order. Use only the user-selected Nemotron model. If it is unavailable, report that fact instead of substituting a different model.

---

You are the independent reviewer of the completed MMNext transcript restart-discovery and canonical-fingerprint task. Copilot says it finished. Verify that statement against the live repository, exact changed-file evidence, baseline snapshots, tests, and the original work order. Do not trust the coder's conclusion. You are not the coder and must make no implementation or documentation edits.

## Important repository facts to re-verify

The current workspace was observed to have no `.git` directory. Do not require or claim `git status`/`git diff`; do not initialize Git or change branches. A recent local full-suite run in this workspace reported `290 passed, 1 skipped in 59.86s`, while an earlier Nemotron report recorded `2 failed, 288 passed, 1 skipped`. These are dated, conflicting observations. Run tests against the current checkout and report only the result you observe.

A recent read-only inspection confirmed that normal startup already assigns `Path.home() / ".mmnext" / "jobs"` when no test root is injected, constructs `JobRepository`, and runs a startup scan. `MainWindow` constructs `AppContext()` without overriding that default. Do not report that this root/startup wiring is absent. The known remaining concern is that the scan currently returns only recoverable incomplete jobs and excludes COMPLETE jobs from the Jobs UI.

A recent inspection also found a likely fingerprint test gap: `tests/test_transcript_open.py` builds artifacts using `JobRepository.compute_fingerprint()`, while `WhisperTranscriptAdapter` calculates its own fingerprint. The local source enum is `"local_file"`, but the repository fingerprint code was checking `"local"` before reading file metadata. The adapter and app-context reopen calculation therefore had different contracts even though the existing helper-based tests passed. Verify against current code; do not assume these defects remain unchanged.

## Required review materials

Use:

- The Copilot work order it was given (the updated transcript reopen/fingerprint task).
- Copilot's final handoff, changed-file list, test output, and any user-supplied notes.
- The task-specific `.work/review-baselines/transcript-reopen-<id>/` baseline copies, SHA-256 manifest, and unified patch produced before/after edits as required by the work order.
- Current source/tests and repository rules: `Agent.md`, `instructions.md`, `todo plan.md`, `checklist.md`, `README.md`, and applicable `AGENTS.md` files.

Verify the baseline hashes and compare every reported changed file with its corresponding baseline. Confirm that the patch covers all changed files and that no unreported source files were modified. If snapshots, hashes, or a complete patch are missing, do not pretend to know the full change set. You may still inspect current behavior, but mark change-scope verification as incomplete and state exactly what is missing.

## Read-only boundary

- Do not create, alter, delete, rename, or format repository files. Do not edit `todo plan.md` or `checklist.md`.
- Do not initialize Git, change branches, commit, push, create a pull request, or run network operations.
- Do not download media, models, dependencies, or generated artifacts.
- You may run already-installed local tests and read-only inspection commands. If unavailable, mark them not run/skip; never claim success.
- Do not fix findings yourself. Write precise correction requests for Copilot.

## Review procedure

1. Read the project rules and exact Copilot work order.
2. Inspect the no-Git baseline snapshot, hash manifest, unified patch, and changed-file list. Verify the patch and hashes independently.
3. Trace the real flow from normal startup, through transcript completion/artifact commit/Job persistence, restart scan, Jobs UI, explicit open, worker validation, and final Workspace binding.
4. Independently run focused tests and the full suite if the local environment permits. Inspect the test helper to verify that an artifact emitted by the REAL transcript adapter is exercised; do not accept helper-only agreement as proof.
5. Examine failure ordering, schema compatibility, concurrency, stale results, REAL/DEMO separation, and Exact Dubbing immutability.

## Acceptance matrix

For each item use **PASS**, **FAIL**, **PARTIAL**, or **NOT VERIFIED**, and cite concrete file/line and test evidence.

### 1. Canonical fingerprint and source identity

- The transcript adapter, JobRepository, completion persistence, reopen, and checkpoint/resume paths call one canonical algorithm rather than duplicate incompatible implementations.
- `SourceType.LOCAL_FILE.value` is handled correctly. The fingerprint uses a safely canonicalized full source identity and real local file size and sufficiently precise mtime; unavailable source files are rejected rather than treated as zero-metadata matches.
- Mode, schema and transcript settings used to produce the artifact are consistently represented and can be recomputed for reopen/resume.
- A test produces an artifact through the REAL adapter (using deterministic fake/local Whisper behavior where needed), reopens it after fresh-context restart, then proves changed/missing source rejection. A helper that directly calls the same repository function to manufacture every artifact does not satisfy this criterion.
- `can_resume_job` agrees with the canonical contract. Legacy checkpoints that cannot be verified are handled safely, never accepted by disabling checks.

### 2. Job metadata and honest persistence

- The Job model has a fingerprint field and JobRepository preserves it through save/load. Old versioned records without the field load safely as explicitly legacy/empty.
- Job metadata records the correct fingerprint, source, mode, schema, and artifact path only after successful validated atomic artifact commit.
- Job state cannot misleadingly become durably COMPLETE before the artifact commit; persistence exceptions are logged and surfaced in the UI. If durable metadata save fails, the app truthfully reports that restart recovery was not saved.

### 3. Restart discovery and explicit opening

- Completed REAL transcript records are included in a separate startup-discovery list and appear in Jobs after a fresh `AppContext`; they are not added to recoverable-resume eligibility.
- Restart scan/refresh is idempotent and does not duplicate records or let demo jobs impersonate persisted REAL jobs.
- No job is auto-resumed or auto-opened. The user must explicitly select Open transcript.
- A valid completed disk-only Job opens without requiring a cached JobManager entry. The persisted state is authoritative; any in-memory consistency check is explicit and meaningful.

### 4. Artifact validation and backward compatibility

- Artifact mode matches Job/current mode. Job and artifact completion state, REAL marker, supported schemas, source identity/fingerprint, artifact path containment, and JSON shape are checked before mutating the session.
- If the artifact schema changes to carry mode/fingerprint metadata, versioning is explicit. Existing artifacts remain intact. Legacy artifacts are either handled by a safe, tested compatibility/migration path or rejected with a clear explanation and recovery instruction. No unverifiable artifact is silently accepted.
- Rows are validated before binding: IDs nonempty and unique; values finite; start nonnegative; duration positive; end within authoritative duration when available.
- Failure preserves the active session and Exact Dubbing source fields exactly; no demo fallback occurs.

### 5. Threading, UI and architecture

- Artifact loading/validation runs outside the GUI thread using the project's thread pattern. Stale results do not bind after the selected job/source changes.
- The Jobs UI shows completed eligible jobs and a clear explicit open action; errors are visible.
- Exact Dubbing `id`, `original`, `start`, and `duration` remain immutable; only `burmese` and `gender` are editable. No source rows are summarized, dropped, reordered, merged, retimed, translated automatically, or invented.
- Architecture gates continue to pass; no unrelated TTS/translation/download/render feature was added.

### 6. Tests and documentation

- Focused tests cover adapter-produced matching fingerprints, changed/missing source, type/local_file metadata, Job fingerprint round-trip and legacy metadata, COMPLETE discovery, disk-only explicit open, mode/schema mismatches, corrupt/missing artifacts, invalid rows, persistence failure, no auto-resume, thread safety/stale result, idempotent refresh, and Exact Dubbing invariants.
- Distinguish unit tests, UI/integration tests, and optional real-media smoke. A passing suite that omits the real adapter-to-reopen path is insufficient.
- Check that `todo plan.md` and `checklist.md` no longer present the old `291 passed` baseline or absent-jobs-root claim as current fact. Historical evidence should remain clearly dated, and current counts must match the fresh run. Prompt files under `outputs/` should not be modified by Copilot.

When possible, run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_transcript_open.py tests\test_job_repository.py tests\test_live_transcript_workspace.py -q --confcutdir=tests -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

Report exact commands, pass/skip/failure counts, errors, and anything unavailable. The number of collected tests can change after additions; require no unexplained failures, not a stale hard-coded total.

## Required verdict and response

Write the review in clear, natural Myanmar Unicode Burmese. Do not use Zawgyi or insert unrelated languages into Burmese sentences. Keep file paths, code identifiers, commands, and test names unchanged.

Use this format:

1. **Verdict:** `ACCEPT`, `ACCEPT WITH REQUIRED FIXES`, `REJECT`, or `NOT REVIEWABLE`.
2. **Change-scope evidence:** baseline/hash/patch verification and any missing materials; explicitly state that the workspace is not a Git repository if that remains true.
3. **Acceptance matrix:** verdict and evidence for each section above.
4. **Findings:** severity, file/line, observed behavior, user impact, and concrete correction request; say explicitly if no blocking findings were found.
5. **Tests:** exact commands and counts actually observed; unrun tests and reasons.
6. **Invariants/regressions:** REAL/DEMO, no auto-resume, no GUI blocking, failure/session preservation, and Exact Dubbing source immutability.
7. **Planner decision:** require a Copilot fix-and-review cycle, or state that the evidence supports accepting this slice and allow Nemotron Planner to choose the next task. Do not choose or implement the next task yourself.
8. **Limitations:** every claim that could not be independently verified.

Do not call the slice complete unless fresh-start completed-REAL discovery, explicit valid open from a real adapter-produced artifact, matching and mismatching fingerprint behavior, session-preserving rejection, persistence failure visibility, and the relevant tests are independently demonstrated.

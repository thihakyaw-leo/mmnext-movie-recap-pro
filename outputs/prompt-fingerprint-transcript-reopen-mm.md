# MMNext — Verify and Complete REAL Transcript Fingerprint Reopening

You are the primary implementation agent working in the existing repository at:

```text
J:\mmnext-movie-recap-pro
```

Your goal is to verify that a transcript artifact produced by the real transcript adapter carries a reproducible canonical fingerprint and can be reopened from the persisted Jobs workflow. Use source inspection and regression tests as evidence. Do not restart or redesign the project.

## Critical first step: verify before changing anything

The project roadmap and checklist may already record a fix for this issue, including artifact-settings-based fingerprint verification, mode/schema/source checks, path containment, and background-thread reopening. Before editing code, inspect the current source and tests and determine whether this request is already fully satisfied. If it is, do not make redundant production-code changes; run the relevant tests and report the evidence and any remaining limitations.

Read these project instructions first:

```text
Agent.md
instructions.md
todo plan.md
checklist.md
README.md
```

Then inspect the current relevant implementation and tests. File names may have changed; verify the current tree rather than assuming a path exists.

```text
mmnext/domain/fingerprint.py
mmnext/domain/models.py
mmnext/infrastructure/transcript_adapter.py
mmnext/infrastructure/repository/job_repository.py
mmnext/application/job_manager.py
mmnext/ui/app_context.py
mmnext/ui/reopen_transcript_worker.py
mmnext/ui/screens/jobs_screen.py
mmnext/ui/main_window.py
tests/test_fingerprint.py
tests/test_transcript_open.py
tests/test_transcript_reopen_thread.py
tests/test_job_repository.py
tests/test_architecture_gates.py
```

If documentation disagrees with the current source or tests, trust the source and tests, then update the documentation with dated evidence without erasing historical notes.

## Scope

Keep this to one small vertical slice: verifying and, only if needed, fixing persisted REAL transcript fingerprint/reopen behavior.

1. Inspect the production artifact writer in `WhisperTranscriptAdapter`. Confirm that the artifact preserves the exact inputs used to compute its canonical fingerprint, including `fingerprint_settings`, `fingerprint_source_type`, `fingerprint_schema_version`, mode, and source identity.
2. Verify an integration regression test that uses the production adapter’s actual artifact-writing code, persists the corresponding job record, creates a fresh repository/application context, and reopens the artifact through the user-facing Jobs/reopen path. The expensive inference/runtime may be replaced at the test boundary so the test remains offline and does not require Whisper, GPU, FFmpeg, or network access. Do not mock away the artifact writer or the reopen validation being tested.
3. Verify that reopening preserves transcript row IDs, source text, start times, and durations exactly. For Exact Dubbing, verify the immutable source fields remain unchanged and Burmese/gender values are not invented or silently filled.
4. Verify rejection tests for invalid fingerprints, missing or legacy contract fields, mode/source/schema mismatches, demo artifacts, and corrupt JSON. Rejected artifacts must not partially replace or mutate the existing project session or source rows.
5. If reopening uses a worker, verify that reading and validation occur off the GUI thread and that session application occurs on the GUI thread. Verify that a stale result is discarded if the selected job/source changes while loading.

## If a gap remains

Make only the smallest production-code and regression-test changes needed for this reopen slice. Prefer a failing regression test first, then implement the fix and confirm the test passes. Use the existing `canonical_fingerprint()` contract; do not create a second fingerprint algorithm. Preserve job-scoped paths, atomic writes, strict REAL-versus-DEMO separation, and the Exact Dubbing immutable-field contract.

Do not expand scope into YouTube downloading, translation/Gemini, TTS, rendering, packaging, or unrelated Narrator/Splitter/Common Editing features. Treat both legacy projects as read-only references. Do not copy legacy implementations into the new UI or modify legacy files. No NVIDIA API or external network access is needed for this task.

## Required verification

First run the focused tests that actually exist in the current checkout. For example:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_fingerprint.py tests\test_transcript_open.py tests\test_transcript_reopen_thread.py -q --confcutdir=tests -p no:cacheprovider
```

If one of those files does not exist, inspect the current tests and use the actual relevant paths. Report the exact command used.

Then run the full suite using the Windows-required `--confcutdir` option:

```powershell
.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

If UI or thread wiring changes, also run the offscreen shell smoke test:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
.venv\Scripts\python.exe scripts\check_shell.py
```

Do not claim real Whisper inference was tested unless it actually ran with an approved media fixture and cached model. If the optional real-media test is skipped, report the skip and its reason. Passing an adapter-artifact integration test does not prove production inference or full product readiness.

Update `todo plan.md` and `checklist.md` with a dated entry using their existing structure. Preserve historical notes; distinguish code changes, exact test results, skips, and remaining limitations. Do not commit, push, change branches, or open a PR unless explicitly requested.

## Completion report must state

- Whether the fix was already present and whether production code was changed during this task.
- The name and result of the integration test that reopens an artifact written by the production adapter through a fresh persisted-job/reopen path.
- Which tests cover rejection cases and Exact Dubbing source-field immutability.
- Exact focused and full-suite results, including any skips or failures.
- Files changed and remaining limitations.

Before declaring completion, ensure the implementation, tests, and updated project notes agree with one another.

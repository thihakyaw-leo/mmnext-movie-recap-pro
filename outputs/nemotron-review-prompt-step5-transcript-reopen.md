# Read-only code review prompt — Step 5 transcript reopening

You are an independent senior Python/PySide6 reliability reviewer. Review the current MMNext Movie Recap Pro repository as it exists on disk. Your task is to audit the saved-REAL-transcript reopening implementation attributed to “Step 5 Preview.” This is a **read-only review**: do not edit, create, delete, or reformat any repository files, do not commit, and do not implement fixes. Do not make network calls or download dependencies/media/models.

## Review objective

Determine whether a completed REAL transcript can be safely discovered after an application restart and explicitly opened into the Production Workspace, and whether the implementation and its test evidence justify calling this feature complete. Treat every claim in the reported completion summary as a hypothesis to verify against the current source and tests—not as ground truth. In particular, independently establish whether the saved transcript fingerprint is recomputed and compared during reopen; finding a `fingerprint` field in JSON is not proof that it is checked.

## Repository and files to inspect

Repository root: `J:\\mmnext-movie-recap-pro`

Inspect at minimum:

- `mmnext/ui/app_context.py` — `AppContext` construction, startup repository scan, `open_transcript_from_job()` and session binding.
- `mmnext/ui/main_window.py` and `mmnext/bootstrap.py` — normal application startup and jobs-root configuration.
- `mmnext/ui/screens/jobs_screen.py` — job population, Open transcript visibility/enabling, selection, errors, and action wiring.
- `mmnext/infrastructure/repository/job_repository.py` — metadata/checkpoint schemas, source-scoped paths, completed/incomplete listing, scan, corruption handling, and fingerprint/resume checks.
- `mmnext/infrastructure/transcript_adapter.py` — REAL transcript artifact/checkpoint writes and Job metadata integration (if any).
- `tests/test_transcript_open.py`, `tests/test_live_transcript_workspace.py`, `tests/test_transcript_regressions.py`, and `tests/test_job_repository.py`.
- `todo plan.md`, `checklist.md`, and `outputs/transcript-boundary-report.md` only to compare documentation claims with implementation. Source and test code are authoritative.

The workspace may not contain Git metadata. If no diff/commit is available, state that you reviewed the current working tree and do not invent a Step-5 diff or authorship evidence.

## Non-negotiable project invariants

- Never silently fall back from REAL data to demo rows or report simulated work as production completion.
- Never auto-resume a recovered job; recovery must be presented for explicit user action.
- Exact Dubbing must preserve every source row and its identity, original text, start, and duration; Burmese and gender are the only editable fields. Do not summarize, omit, reorder, merge, or invent dialogue.
- Do not begin translation, TTS, or final rendering as part of this review.
- Source media must remain untouched; artifact/checkpoint writes must remain atomic and job-scoped.
- Expensive or large file work must not block the PySide6 GUI thread.
- Failures must remain visible and must not bind partial or incompatible data into a REAL session.

## Review questions

1. **Normal startup and persistence:** Does the regular app configure a stable, user-writable jobs root? Does REAL transcription persist a versioned Job metadata record as well as the transcript artifact/checkpoint? After restart, are completed REAL transcript jobs discoverable in the Jobs screen? Distinguish repository capability from a path actually wired into the normal application.
2. **Artifact identity/integrity:** Is the artifact’s stored fingerprint recomputed and compared to the current source and relevant model/language/mode/schema settings? Does the loader validate the job source, artifact source, mode, schema version, REAL/demo marker, COMPLETE state, artifact existence, and output location without trusting an unverified path?
3. **Transcript row safety:** Are row IDs nonempty and unique? Are start/end/duration finite, positive, ordered, and bounded by authoritative media duration? Are malformed JSON, NaN/Infinity, missing fields, empty rows/text, duplicates, and out-of-range rows rejected before replacing the current session? Is valid existing state preserved on failure?
4. **Exact Dubbing contract:** Do reopened rows retain ID, original text, start, and duration exactly, with Burmese empty and no generated narration? Does validation still block production readiness until user edits and validates the translation?
5. **UI/thread safety:** Is potentially large artifact reading/validation kept off the GUI thread? Are results rejected if the selected job/source/session changes during loading? Does the Jobs button reflect the actual persisted job set, and are errors shown without crashing or silently changing sessions?
6. **Test adequacy:** Which of the above are truly covered by current tests? Check whether UI button activation and restart discovery are tested, rather than only direct method calls. Identify missing positive, negative, corruption, boundary, mismatch, race, and off-GUI-thread tests. If you run tests, use only local resources and a no-cache pytest mode; do not change source or fixtures.
7. **Truthful status:** Is “feature complete” or “source fingerprint match” justified? Give a precise verdict: complete, partial, or not operational end-to-end, and explain which scope boundary your verdict uses.

## Required response format

Return a concise but evidence-rich review with these sections:

1. **Verdict** — one of `Complete`, `Partially implemented`, or `Not operational end-to-end`; include a one-paragraph rationale.
2. **Claim verification table** — claim, `Verified / Partially verified / Not verified / Contradicted`, evidence (`file:line`), and explanation. Include explicit rows for fingerprint comparison, normal-startup repository wiring, persisted completed Job metadata, restart discovery, atomic artifact integrity, and Exact Dubbing invariants.
3. **Findings by severity** — Critical/High/Medium/Low, each with exact file and line references, impact, and a minimal fix direction. Do not report style preferences as correctness bugs.
4. **Test evidence and coverage gaps** — tests actually inspected/run and specific untested failure modes.
5. **Ordered acceptance plan** — the smallest safe changes/tests needed before the feature can be called complete; keep the plan limited to persisted transcript recovery/reopen and do not expand into translation/TTS/rendering.

For every important conclusion, cite the current source/test line(s). Clearly label direct evidence versus inference. Do not assume that a status document proves behavior, and do not change any files.
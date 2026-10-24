# MMNext Movie Recap Pro — Code Audit Report

**Audit date:** 2026-10-24  
**Repository:** `J:\mmnext-movie-recap-pro`  
**Method:** Read-only review of current source and related tests across six independent areas. Key findings were checked against current source lines. No source or test files were edited; only this report file was created.

## Executive summary

The complete test suite reported **466 passed, 4 skipped in 297.99 seconds**. A passing suite does not prove every workflow is correct. The code review confirmed false-success paths, Exact Dubbing rendering from stale text, possible loss of unsaved work, unsafe worker shutdown paths, recovery/path validation gaps, and UI controls that do not affect the project state.

The highest-priority fixes are: use validated Exact Dubbing translations in rendering; fail REAL Narrator operations when translation or media validation fails; remove silent REAL-to-DEMO fallback in Common Editing; protect unsaved data when changing sources; and manage active `QThread` workers during Stop and window close.

## Test evidence

Command executed:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider
```

Result: **466 passed, 4 skipped, 297.99s**. Skips:

- `tests/test_exact_dubbing_render.py:842` — opt-in live Edge TTS smoke test.
- `tests/test_narrator_pipeline.py:475, 532` — approved media fixture and locally cached Whisper model required.
- `tests/test_transcript_regressions.py:166` — approved media fixture and locally cached Whisper model required.

Those optional real-service/media paths were not exercised. `scripts/check_shell.py` was not separately run in this audit.

## Confirmed findings

### High priority — correctness, data loss, and shutdown

1. **Exact Dubbing discards the validated translation before rendering.** `mmnext/application/exact_dubbing_service.py:195-204` calls `validate_translation()` but discards its returned rows, then passes `source_rows` to the render coordinator. The coordinator synthesizes using each row's `burmese` and voice values (`mmnext/application/exact_dubbing_render_coordinator.py:180-195`). A valid edited translation file can therefore pass validation while rendering stale text or speaker values. Use the validated editable values while preserving immutable `id`, `original`, `start`, and `duration`; add a test where file values differ from in-memory rows.

2. **REAL Narrator translation failures can be converted to blank text and continue.** `mmnext/services/adapters/narrator_translation.py:58-60, 74-94` returns empty strings when the translation entry point is missing or raises. `mmnext/application/narrator_pipeline_coordinator.py:190-199` checks only result count and accepts blanks; `:251-252` skips blank narration. A REAL run may continue and appear complete without translated narration. Propagate explicit failure to the UI and reject blank translations.

3. **REAL Narrator output can be published without validation when FFmpeg/FFprobe are unavailable.** `mmnext/application/narrator_pipeline_coordinator.py:332-359` validates only when `self._tools.available()` is true. Otherwise it renames the `.partial` file to the final path and reports “Render complete.” A non-empty but invalid or unplayable file can be published as a successful REAL output. Fail closed when REAL validation is unavailable.

4. **REAL Common Editing export ignores requested edits.** `mmnext/services/adapters/common_editing.py:30-39` ignores the session/settings and invokes FFmpeg with `-c copy`, copying the source rather than applying requested trim, overlay, ratio, or fill changes. `mmnext/ui/app_context.py:694-717` treats the result as a completed export. Implement the requested transformations or refuse unsupported settings rather than reporting a successful edited export.

5. **REAL Common Editing can silently fall back to a DEMO placeholder.** `mmnext/ui/app_context.py:694-698` selects `DemoCommonEditingExporter` when the REAL exporter is unavailable. `mmnext/services/adapters/common_editing.py:8-15` writes non-media placeholder bytes and returns success; the completion state does not label this as DEMO (`app_context.py:710-717`). REAL mode should fail visibly; use the placeholder only in explicit DEMO mode and label it clearly.

6. **Importing a different source can discard unsaved work without confirmation.** `mmnext/ui/screens/import_screen.py:173-208` calls `set_source()` without checking dirty edits. For a changed source, `mmnext/application/project_controller.py:94-102` clears transcript and other working rows. Require explicit save/discard/cancel confirmation and preserve the old session on cancel.

7. **Closing during transcript reopen does not manage the active reopen thread.** `mmnext/ui/app_context.py:1019, 1028` creates and starts a `ReopenTranscriptThread` parented to `AppContext`. `mmnext/ui/main_window.py:516-531` does not wait for or cancel that thread before closing. This risks Qt's “QThread: Destroyed while thread is still running” failure. Add a non-blocking safe shutdown path.

8. **Common Editing export is omitted from Global Stop and close handling.** The worker starts in `mmnext/ui/app_context.py:684-708`, but `mmnext/ui/main_window.py:445-470, 501-531` does not stop or join it. `mmnext/ui/common_editing_export_worker.py:53-54` has a no-op `stop()`. Track this operation in active-work state and cancel it safely or defer close until completion.

### Medium priority — persistence, isolation, and UI behavior

9. **Resume eligibility may accept an unverifiable or fully completed checkpoint.** `mmnext/infrastructure/repository/job_repository.py:453-467` compares the checkpoint fingerprint only when it is truthy and does not enforce `JobCheckpoint.can_resume()` or completed-unit eligibility (`mmnext/domain/models.py:465-475`). Require a non-empty matching fingerprint and reject fully completed checkpoints.

10. **Malformed checkpoint schema values can escape as exceptions.** `mmnext/infrastructure/repository/job_repository.py:344-346` converts `schema_version` with `int()` without catching `TypeError` or `ValueError`; `can_resume_job()` does not turn this into a safe refusal. Add malformed-schema recovery tests and return a structured corrupt-checkpoint result.

11. **`job_id` is used as an unchecked filesystem path component.** `mmnext/infrastructure/repository/job_repository.py:111-112, 234-237` joins the supplied ID into a path without rejecting traversal or absolute paths. Validate IDs as single path components and enforce resolved-path containment before filesystem access.

12. **A delayed reopen can overwrite a newer project/source.** `mmnext/ui/app_context.py:250-252, 1100-1107` does not invalidate the reopen request when source/session changes. The result handler (`:1036-1055`) checks the request ID but not active project/source identity. Invalidate on source/reset and verify identity again before applying.

13. **Invalid artifact duration can disable transcript row-bound validation.** `mmnext/application/job_service.py:214-217, 238-240` can substitute `0.0` for absent or invalid `duration_s`, then skip the row-end bound check. Require a finite positive duration and reject malformed artifacts.

14. **Concurrent Exact Dubbing renders can share fixed work files.** `mmnext/application/exact_dubbing_service.py:128-133` uses a common `exact_dubbing_work` directory. `mmnext/infrastructure/exact_dubbing_render.py:404-410, 456-458, 499-513` uses fixed intermediate names and cleanup paths. Give each render a unique work directory and add a parallel-render isolation test.

15. **The documented Exact Dubbing source-duration gate is not applied at render start.** `mmnext/domain/validation.py:305-320` defines a 0.05-second blocking threshold, but `mmnext/ui/app_context.py:514-568` does not invoke it. The renderer instead warns only above 0.5 seconds (`mmnext/infrastructure/exact_dubbing_render.py:391-401`). Consolidate the threshold and enforce it before synthesis/render.

16. **Narrator fallback planning can leave timeline gaps.** `mmnext/services/adapters/narrator.py:120-139` does not extend intervals to the next row start or create gap units. Rows at 0–1s and 3–4s leave 1–3s uncovered. Define the gap policy and test full timeline coverage.

17. **Narrator translation checkpoints are not job-scoped.** `mmnext/ui/app_context.py:821-826` defaults all jobs to the same `narrator_translation_checkpoint.json`; `mmnext/application/narrator_pipeline_coordinator.py:220-229` overwrites it per batch without job ID or source fingerprint. Use per-job paths and include job/source identity.

18. **Common Editing writes directly to the final output path.** `mmnext/services/adapters/common_editing.py:36-39` does not render to a `.partial` file, validate, atomically publish, or clean up failed output. A truncated file can remain under the final name. Render to a temporary path, validate, then atomically replace.

19. **Splitter's directory-level renderer ignores per-part failures.** `mmnext/infrastructure/splitter_render.py:150-156` discards each `render_part()` result and returns `True` after the loop. Propagate the first failure and identify the failed part.

20. **Splitter cache keys do not include source content/revision.** `mmnext/application/splitter_render_coordinator.py:53-57, 84-92` can reuse a previous output after the file at the same path changes. Add a stable source revision (size/mtime or content identity) to the cache key.

21. **Splitter completion can clear the active Common Editing thread reference.** `mmnext/ui/app_context.py:755-761` sets `_common_editing_thread = None` from the splitter completion handler. The Common Editing single-run guard depends on that reference (`:684-686`). Remove the cross-worker reset and clear only the matching completed thread.

22. **Settings controls do not update project/render settings.** `mmnext/ui/screens/settings_screen.py:60-74, 193-208` displays aspect ratio, frame fill, and output-folder controls but does not persist changes into the project session. Splitter reads old values (`mmnext/ui/app_context.py:667-669`). Wire the controls to persistence or label them unavailable.

23. **Resume can be enabled for FAILED jobs while requesting an illegal transition.** `mmnext/ui/screens/jobs_screen.py:209-213, 225-234` may enable Resume but always requests `DOWNLOADING`; `mmnext/application/job_manager.py:114-120` does not permit FAILED -> DOWNLOADING. Match button enablement and target transition to the current job state.

### Low priority and architecture

24. **Optional REAL Narrator smoke tests wait on the wrong state and reference an undefined variable.** `tests/test_narrator_pipeline.py:491-496, 550-555` waits on `ctx.transcript_state` instead of `narrator_state` and later refers to undefined `context.narrator_message`. Fix before enabling those optional tests.

25. **Application/services import concrete infrastructure implementations.** `mmnext/application/job_service.py:29-32` imports the concrete repository; `narrator_pipeline_coordinator.py:33-34` imports `FfmpegTools`; `mmnext/services/adapters/splitter.py:14-16` and `common_editing.py:24-33` also import infrastructure directly. Use protocols/composition boundaries and add architecture gates for these dependency directions.

## Intentional limitations not counted as defects

- Some Download/import flows are explicitly labelled DEMO.
- Narrator planning and translation are separate stages by design.
- Some Exact Dubbing controls are explicitly marked as simulated milestone behavior.
- Transcript stop is cooperative at a safe operation boundary; immediate mid-operation resume is not promised.

## Recommended fix order

1. Correct Exact Dubbing translation use; make REAL Narrator failures fail visibly; remove silent Common Editing DEMO fallback.
2. Protect dirty work on source change; manage reopen/Common Editing threads on Stop and close; reject stale reopen results.
3. Harden checkpoint validation, `job_id` containment, job-scoped checkpoints, artifact duration, and per-render work directories.
4. Fix Splitter failure propagation/cache identity, Common Editing atomic output, and Exact Dubbing duration validation.
5. Connect Settings/Resume UI, repair optional smoke tests, expand architecture gates, and add regression coverage for each fix.

## Workspace note

The workspace already contained modified and untracked files when the full test run began. Their origin was not determined, and this audit did not alter them. The only new deliverable from this audit is this Markdown report.

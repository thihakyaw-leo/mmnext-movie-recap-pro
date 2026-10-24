# No-Git review evidence - transcript reopen / canonical fingerprint fix cycle

This workspace is not a Git repository, so a baseline snapshot is used instead of a
Git commit. Files under `baseline/` are byte-for-byte copies of the files the
fix cycle touched, captured BEFORE the first edit.

- `manifest.sha256` - SHA-256 of every baseline copy plus the marker for files that
  did not exist yet (new files).
- `baseline/` - the untouched copies, relative paths preserved.
- `changes.diff` - unified diff produced after the edits. It covers every
  changed file **and** the two new files (diffed against an empty file, so
  the whole content appears as an addition).
- `changed-files.sha256` - SHA-256 of each file after the edits, labelled
  `changed` / `new` / `unchanged` / `deleted` relative to the baseline.

## How the diff was produced

`changes.diff` was generated with the Git-bundled
`C:\Program Files\Git\usr\bin\diff.exe -u` against the `baseline/` copies, one
file at a time, with `--label a/<path>` and `--label b/<path>` so the headers
are repository-relative. Only files that actually differ produce a hunk.
Re-running the same command reproduces the file byte-for-byte. The output is
UTF-8 with LF line endings.

## Ownership of the changed files

The fix cycle is split into two lanes, and the diff spans both:

- **Lane 1 (canonical fingerprint - domain + infrastructure)**:
  `mmnext/domain/fingerprint.py` (new), `mmnext/domain/__init__.py`,
  `mmnext/domain/models.py`,
  `mmnext/infrastructure/repository/job_repository.py`,
  `mmnext/infrastructure/transcript_adapter.py`,
  `tests/test_fingerprint.py` (new), plus the documentation update in
  `todo plan.md` and `checklist.md`.
- **Lane 2 (re-open path - UI + application)**: `mmnext/ui/app_context.py`,
  `tests/test_transcript_open.py`.

The baseline was captured once, before either lane started, so the diff is a
single continuous view of the whole cycle rather than two overlapping ones.

## Known limitation of this evidence

The baseline covers the files the fix cycle was expected to touch. It is not a
snapshot of the whole repository, so it cannot prove that an *untracked* file
elsewhere was left untouched. For that, use the `changed-files.sha256` list as
the authoritative set of files touched during the cycle.

This evidence is a **point-in-time snapshot**. The two lanes were still working
when it was generated, so a lane-2 file may have changed after the hash was
taken. Re-run the comparison (see the command shape in the "How the diff was
produced" section) to refresh it before relying on the exact hashes.

Baseline id: transcript-reopen-fixcycle-01

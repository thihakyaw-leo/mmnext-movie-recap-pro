# AGENTS.md — MMNext Movie Recap Pro

Compact orientation for Kilo/Copilot agents. Read `Agent.md` (governing contract),
`instructions.md` (engineering rules), `todo plan.md` (live roadmap) and
`checklist.md` (per-item evidence) before changing code. Where docs disagree with
source or tests, **trust the source and tests**.

## Commands (run from repo root; use the project venv at `.venv\Scripts\python.exe`)

- Full suite: `.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests -p no:cacheprovider`
  - `--confcutdir=tests` is **required on Windows**: without it pytest walks to the
    drive root and can fail with a permission error.
- Single test / file: append the path, e.g. `... -m pytest tests/test_workers.py -q --confcutdir=tests`
- Offscreen UI smoke: `QT_QPA_PLATFORM=offscreen .venv\Scripts\python.exe scripts\check_shell.py`
- Launch app: `.venv\Scripts\python.exe -m mmnext.main` (or `scripts\run_app.py`)

The suite is fully offline (no keys, network, FFmpeg, mpv, Whisper, GPU). `conftest.py`
forces `QT_QPA_PLATFORM=offscreen` and holds one session-scoped `QApplication`.

Optional real-media smoke tests **skip** unless `MMNEXT_TRANSCRIPT_SMOKE_MEDIA` and
`MMNEXT_TRANSCRIPT_SMOKE_MODEL` point at a real media file and a cached Whisper model.

## Architecture (layered, enforced by tests/test_architecture_gates.py)

`ui -> application -> services -> domain` (infrastructure below services).

- `domain` — pure typed models/enums/validation, no Qt, no application import.
- `application` — controllers/coordinators, Qt-free, no UI import.
- `services` — protocols + demo and real adapters (e.g. faster-whisper, metadata, narrator).
- `infrastructure` — runtime probes, job repository, transcript adapter, mpv player.
- `ui` — PySide6 shell; talks to `AppContext` via signals only.

Enforced gates (a change that trips these fails CI-style): no Qt in `domain`/`application`,
no Tkinter anywhere, no network SDK (`requests`, `httpx`, `openai`, `anthropic`,
`google.generativeai`, `urllib3`) anywhere in `mmnext/`, UI must not mention legacy
project names, every subpackage needs `__init__.py`, and **UI must never connect a
self-capturing lambda/`functools.partial` to a signal** (creates a PySide6 teardown
reference cycle that aborts the interpreter). Pass extra payload via
`sender().setProperty(...)` and connect bound methods.

## Invariants that will break the product if violated

- Never block the GUI thread with FFmpeg/yt-dlp/Whisper/TTS/model calls; use `QThread` workers.
- Never silently fall back from REAL to DEMO; label demo work and surface REAL failures.
- Never write real-job checkpoints to the CWD; use job-scoped paths + atomic `.partial` rename.
- Never overwrite source media or mutating exact-dubbing source rows.
- No auto-resume: present recovered jobs for explicit user action.

### Mode contracts (deliberately NOT shared)
- **Exact Dubbing**: `id`, `original`, `start`, `duration` are immutable; only `burmese`
  and `gender` are editable. Never summarize/omit/reorder/merge/retime. Render blocked
  until validation passes.
- **Narrator**: freely re-orderable summarised rows; must never be routed through Exact
  Dubbing or vice-versa.
- Myanmar text must be Unicode (never Zawgyi) and round-trip unchanged.

## Repo-specific gotchas

- **`pyproject.toml` `[tool.setuptools] packages` is incomplete.** It omits
  `mmnext.infrastructure.repository` and `mmnext.services.adapters`, so a non-editable
  install produces a broken wheel. Tests pass only because `conftest.py`/scripts insert the
  repo root into `sys.path`. Add any new subpackage to that list when you add it.
- Jobs root is `~/.mmnext/jobs`, overridable with `MMNEXT_JOBS_DIR`.
- No lint/typecheck/CI config exists in-repo; do not claim one runs. No `kilo.json` yet.
- There is no `.git` in the working folder (only `git` history in two legacy reference
  projects on `J:`); do not assume commit/PR evidence exists.
- Legacy reference projects (`J:\recap-en-to-mm-main`, `J:\movie-recap`) are read-only
  contracts to preserve — wrap via subprocess adapters, never copy into UI or edit them.

## Working style

- One small vertical slice per task; keep `todo plan.md` and `checklist.md` evidence current.
- Add/update tests for every behavior change; run focused tests first, then the full suite
  before claiming a milestone. Never report a simulated feature as real completion.
- Never commit, push, open PRs, or change branches unless explicitly asked.

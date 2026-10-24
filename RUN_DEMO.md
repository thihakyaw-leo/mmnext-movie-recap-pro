# MMNext Movie Recap Pro — Milestone 1

Run the demo UI shell:

```powershell
J:\mmnext-movie-recap-pro\.venv\Scripts\python.exe -m mmnext.main
```

Or from repo root:

```powershell
J:\mmnext-movie-recap-pro\.venv\Scripts\python.exe mmnext\main.py
```

Features demonstrated:
- PySide6 main window with left navigation rail
- Home, Import, Analyze, Downloads, Jobs, Workspace, Settings screens
- Mode switcher (Common Editing, Splitter, Narrator, Exact Dubbing)
- Demo project data, simulated download queue with pause/resume/stop/retry
- Segment table, timeline placeholder, preview placeholder, inspector panel
- Collapsible log drawer

No API keys, no FFmpeg, no mpv required for this milestone.

## Tests

```powershell
J:\mmnext-movie-recap-pro\.venv\Scripts\python.exe -m pytest tests -q --confcutdir=tests
```

145 tests pass. A headless smoke check of the whole shell:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
J:\mmnext-movie-recap-pro\.venv\Scripts\python.exe scripts\check_shell.py
```

See `README.md` for the full capability table and the known limitations.

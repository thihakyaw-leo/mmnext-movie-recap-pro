"""Behavioral regression coverage, not worker-construction-only assertions."""
from types import SimpleNamespace
from threading import Event
from unittest.mock import MagicMock
import json

import pytest
from PySide6.QtCore import QThread, Qt

from mmnext.domain.enums import AppMode, JobState
from mmnext.ui.main_window import MainWindow
from mmnext.ui.navigation.nav_rail import NavTarget
from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter


@pytest.fixture
def real_window(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("MMNEXT_JOBS_DIR", str(tmp_path / "jobs"))
    win = MainWindow()
    win.context._jobs_dir = str(tmp_path / "jobs")
    def clear_dirty(widget):
        widget.context.project.mark_exact_rows_clean()
        widget.context.project.mark_narration_clean()
    qtbot.addWidget(win, before_close_func=clear_dirty)
    win.show()
    win.navigate_to(NavTarget.WORKSPACE)
    win.context.set_mode(AppMode.NARRATOR)
    yield win
    if win.context.transcript_running:
        win.context.stop_transcript()
        qtbot.waitUntil(lambda: not win.context.transcript_running, timeout=5000)
    win.context.project.mark_exact_rows_clean()
    win.context.project.mark_narration_clean()
    win._worker.shutdown(wait_ms=1000)


def fake_backend(monkeypatch, tmp_path, segments=None, language="fr"):
    import mmnext.infrastructure.transcript_adapter as adapter_module
    monkeypatch.setattr(WhisperTranscriptAdapter, "_probe_duration", lambda self, p: 12.0)
    monkeypatch.setattr(WhisperTranscriptAdapter, "_prepare_audio", lambda self, p, d: (str(tmp_path / "audio.wav"), ""))
    segments = segments if segments is not None else iter([
        SimpleNamespace(start=0.25, end=2.75, text=" First source line "),
        SimpleNamespace(start=4.5, end=8.125, text="မြန်မာ မူရင်းစာ"),
    ])
    model = MagicMock()
    model.transcribe.return_value = (segments, SimpleNamespace(language=language))
    monkeypatch.setattr(adapter_module, "WhisperModel", MagicMock(return_value=model))
    return model


def start(win, tmp_path):
    source = tmp_path / "မြန်မာ video.mp4"
    source.write_bytes(b"fixture source; backend is mocked")
    win.context.start_local_transcript(str(source), auto_detect=True)
    return source


def wait_finished(qtbot, win):
    qtbot.waitUntil(lambda: win.context._transcript_thread is None, timeout=8000)


def test_live_workspace_transcript_binding(real_window, qtbot, monkeypatch, tmp_path):
    win = real_window
    fake_backend(monkeypatch, tmp_path)
    source = start(win, tmp_path)
    wait_finished(qtbot, win)
    assert win.context.transcript_state == "complete"
    assert win.demo_badge.text() == "REAL"
    session = win.context.session
    assert session.is_demo is False
    assert session.source.location == str(source)
    expected = [("s0", 0.25, 2.5, "First source line"), ("s1", 4.5, 3.625, "မြန်မာ မူရင်းစာ")]
    assert [(r.row_id, r.start, r.duration, r.text) for r in session.transcript] == expected
    assert not session.narration_segments  # no invented recap
    assert not session.split_parts and not session.overlays
    assert [(r.row_id, r.start, r.duration, r.original) for r in session.exact_dubbing_rows] == expected
    model = win._workspace.transcript_model
    assert model.rowCount() == 2
    assert model.data(model.index(1, 3)) == "မြန်မာ မူရင်းစာ"
    assert not model.flags(model.index(0, 3)) & Qt.ItemFlag.ItemIsEditable
    win._workspace.transcript_view.selectRow(1)
    assert win.context.selection.row_id == "s1"
    assert win.context.selection.kind == "transcript"
    win._workspace.on_activate()
    assert win._workspace.transcript_view.currentIndex().row() == 1
    assert win.context.selection.row_id == "s1"
    win.context.set_mode(AppMode.EXACT_DUBBING)
    exact = win._workspace.table.exact_model
    assert exact.rowCount() == 2
    assert not win.context.validate().ok  # untranslated rows never ready
    win.context.project.update_exact_row("s0", burmese="မြန်မာစာ")
    assert session.transcript[0].text == "First source line"
    assert session.narration_segments == []
    artifact = next((tmp_path / "jobs").rglob("*.transcript.json"))
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["language"] == "fr"
    assert payload["is_demo"] is False
    assert payload["rows"][1]["start"] == 4.5
    assert "Artifact:" in win._workspace.transcript_status.text()
    assert win._workspace.transcript_progress.value() == 100


def test_completed_transcript_persists_job_metadata_and_restart_discovery(
    real_window, qtbot, monkeypatch, tmp_path
):
    """A successful REAL run persists a completed Job and is rediscovered."""
    fake_backend(monkeypatch, tmp_path)
    source = start(real_window, tmp_path)
    wait_finished(qtbot, real_window)
    assert real_window.context.transcript_state == "complete"

    metadata_files = list((tmp_path / "jobs").rglob("metadata.json"))
    assert len(metadata_files) == 1
    payload = json.loads(metadata_files[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["state"] == "complete"
    assert payload["is_demo"] is False
    assert payload["source"]["location"] == str(source)

    artifact = next((tmp_path / "jobs").rglob("*.transcript.json"))
    artifact_payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == artifact_payload["fingerprint"]
    assert payload["artifact_path"] == str(artifact)

    live_jobs = [j for j in real_window.context.all_jobs() if not j.is_demo]
    assert any(
        j.job_id == payload["job_id"] and j.state == JobState.COMPLETE
        for j in live_jobs
    )

    from mmnext.ui.app_context import AppContext

    fresh = AppContext(jobs_dir=str(tmp_path / "jobs"))
    try:
        discovered = [
            j for j in fresh.all_jobs() if j.job_id == payload["job_id"]
        ]
        assert len(discovered) == 1
        assert discovered[0].state == JobState.COMPLETE
        assert discovered[0].is_demo is False
        assert discovered[0].fingerprint == artifact_payload["fingerprint"]
    finally:
        fresh.jobs.clear()


def test_job_persistence_failure_is_visible_and_not_silent(
    real_window, qtbot, monkeypatch, tmp_path
):
    fake_backend(monkeypatch, tmp_path)
    ctx = real_window.context
    repository = ctx._job_repository

    def fail(*_args, **_kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(repository, "save", fail)
    start(real_window, tmp_path)
    wait_finished(qtbot, real_window)

    assert ctx.transcript_state == "failed"
    assert "Failed to persist transcript job" in ctx.transcript_message
    assert any(
        "Job persistence failed" in entry.message for entry in ctx.log_entries()
    )


def test_real_tool_failure_visible_in_ui(real_window, qtbot, monkeypatch, tmp_path):
    def missing(self, path):
        raise RuntimeError("FFprobe not found")
    monkeypatch.setattr(WhisperTranscriptAdapter, "_probe_duration", missing)
    start(real_window, tmp_path)
    wait_finished(qtbot, real_window)
    ctx = real_window.context
    assert ctx.transcript_state == "failed"
    assert "FFprobe not found" in real_window._workspace.transcript_status.text()
    assert "restart" in real_window._workspace.transcript_status.text()
    assert ctx.session.transcript == []
    assert ctx.session.exact_dubbing_rows == []
    assert ctx.session.narration_segments == []
    assert real_window._workspace.transcript_model.rowCount() == 0
    assert real_window._workspace.table.exact_model.rowCount() == 0
    assert real_window._workspace.transcribe_button.isEnabled()
    checkpoint = json.loads(next((tmp_path / "jobs").rglob("checkpoint.json")).read_text(encoding="utf-8"))
    assert checkpoint["state"] == "failed" and checkpoint["resume_supported"] is False


def test_out_of_range_whisper_fails_without_binding(real_window, qtbot, monkeypatch, tmp_path):
    fake_backend(monkeypatch, tmp_path, iter([
        SimpleNamespace(start=0.0, end=3.0, text="valid source"),
        SimpleNamespace(start=10.0, end=13.0, text="out of range source"),
    ]))
    start(real_window, tmp_path)
    wait_finished(qtbot, real_window)
    assert real_window.context.transcript_state == "failed"
    assert "authoritative video duration" in real_window._workspace.transcript_status.text()
    assert real_window._workspace.transcript_progress.value() < 100
    assert not real_window.context.session.transcript
    assert not real_window.context.session.exact_dubbing_rows
    assert not list((tmp_path / "jobs").rglob("*.transcript.json"))
    assert real_window._workspace.transcribe_button.isEnabled()


def test_whisper_never_runs_on_gui_thread(real_window, qtbot, monkeypatch, tmp_path):
    fake_backend(monkeypatch, tmp_path)
    threads = []
    original = WhisperTranscriptAdapter._run_whisper
    def record(self, *args):
        threads.append(QThread.currentThread())
        return original(self, *args)
    monkeypatch.setattr(WhisperTranscriptAdapter, "_run_whisper", record)
    start(real_window, tmp_path)
    wait_finished(qtbot, real_window)
    assert threads and threads[0] != real_window.thread()


def test_stop_waits_for_boundary_and_durable_checkpoint(real_window, qtbot, monkeypatch, tmp_path):
    entered, release = Event(), Event()
    def segments():
        entered.set()
        release.wait(5)
        yield SimpleNamespace(start=0.0, end=1.0, text="completed source segment")
        pytest.fail("Stopped work must not consume the next segment")
    fake_backend(monkeypatch, tmp_path, segments())
    source = start(real_window, tmp_path)
    qtbot.waitUntil(entered.is_set, timeout=5000)
    # Closing must not destroy a running QThread or block the GUI.
    assert real_window.close() is False
    assert real_window.context.transcript_state == "stopping"
    assert real_window.context.transcript_running
    release.set()
    wait_finished(qtbot, real_window)
    assert real_window.context.transcript_state == "stopped"
    assert real_window.context.session.transcript == []
    checkpoint = json.loads(next((tmp_path / "jobs").rglob("checkpoint.json")).read_text(encoding="utf-8"))
    assert checkpoint["state"] == "stopped"
    assert checkpoint["completed_units"] == 1
    assert checkpoint["resume_supported"] is False
    partial = json.loads(__import__("pathlib").Path(checkpoint["partial_path"]).read_text(encoding="utf-8"))
    assert partial["rows"][0]["text"] == "completed source segment"
    assert not list((tmp_path / "jobs").rglob("*.transcript.json"))
    assert real_window._workspace.transcribe_button.isEnabled()


def test_real_ui_button_starts_flow(real_window, qtbot, monkeypatch, tmp_path):
    fake_backend(monkeypatch, tmp_path)
    source = tmp_path / "button.mp4"
    source.write_bytes(b"fixture")
    from mmnext.ui.workspace import workspace_screen
    monkeypatch.setattr(workspace_screen.QFileDialog, "getOpenFileName", lambda *a: (str(source), ""))
    qtbot.mouseClick(real_window._workspace.transcribe_button, Qt.MouseButton.LeftButton)
    wait_finished(qtbot, real_window)
    assert real_window.context.transcript_state == "complete"
    assert real_window._workspace.transcript_model.rowCount() == 2


@pytest.mark.parametrize("change_kind", ["session", "source"])
def test_stale_result_cannot_bind_new_source(real_window, qtbot, monkeypatch, tmp_path, change_kind):
    entered, release = Event(), Event()
    def segments():
        entered.set()
        release.wait(5)
        yield SimpleNamespace(start=0.0, end=1.0, text="old source")
    fake_backend(monkeypatch, tmp_path, segments())
    start(real_window, tmp_path)
    qtbot.waitUntil(entered.is_set, timeout=5000)
    if change_kind == "session":
        real_window.context.load_demo_project()
    else:
        from mmnext.domain.models import VideoSource
        real_window.context.set_source(VideoSource.local(tmp_path / "new-source.mp4"))
    release.set()
    wait_finished(qtbot, real_window)
    assert real_window.context.transcript_state == "failed"
    assert real_window.context.session.is_demo is (change_kind == "session")
    assert all(r.text != "old source" for r in real_window.context.session.transcript)

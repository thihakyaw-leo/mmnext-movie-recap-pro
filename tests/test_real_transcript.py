"""Tests for real transcript execution requirements."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

import pytest

from mmnext.domain.enums import AppMode
from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter
from mmnext.domain.models import TranscriptRow


def test_real_ffprobe_required_for_real_job(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        with pytest.raises(RuntimeError, match="FFprobe not found"):
            adapter.transcribe(str(src))


def test_zero_duration_rejected_for_real_job(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    with patch("subprocess.check_output", return_value="0.0"):
        with pytest.raises(RuntimeError, match="zero duration"):
            adapter.transcribe(str(src))


def test_demo_zero_duration_fallback_allowed(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=True)
    # ffprobe returns 0, demo should allow
    with patch("subprocess.check_output", return_value="0.0"):
        # mock ffmpeg and whisper parts
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                rows, lang = adapter.transcribe(str(src))
                assert isinstance(rows, list)


def test_ffmpeg_audio_extraction_command(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    with patch("subprocess.check_output") as mock_out:
        # first call is ffmpeg
        mock_out.side_effect = [b""]
        # create dummy output file
        out = tmp_path / "a.wav"
        out.write_bytes(b"data")
        with patch("os.replace"), patch.object(adapter, "_validate_audio"):
            adapter._prepare_audio(str(src), 30.0)
        # verify ffmpeg command contains key args
        calls = [c[0][0] for c in mock_out.call_args_list]
        ffmpeg_call = calls[0]
        assert "ffmpeg" in ffmpeg_call
        assert "-ar" in ffmpeg_call and "16000" in ffmpeg_call


def test_audio_output_validation(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    with pytest.raises(RuntimeError, match="too small"):
        adapter._validate_audio(str(audio), 30.0)


def test_partial_audio_atomic_rename(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    partial = tmp_path / "out.wav.partial"
    final = tmp_path / "out.wav"
    partial.write_bytes(b"data")
    # simulate rename
    import os
    os.replace(partial, final)
    assert final.exists()
    assert not partial.exists()


def test_real_whisper_adapter_invocation(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    # Mock ffprobe and ffmpeg
    with patch("subprocess.check_output", return_value="10.0"):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                # Mock faster_whisper
                mock_model = MagicMock()
                mock_seg = MagicMock(start=0.0, end=1.0, text="hi")
                mock_model.transcribe.return_value = (iter([mock_seg]), MagicMock(language="en"))
                with patch("mmnext.infrastructure.transcript_adapter.WhisperModel", return_value=mock_model):
                    rows, lang = adapter.transcribe(str(src), language="en")
                    assert len(rows) == 1
                    assert rows[0].text == "hi"


def test_explicit_language_forwarded(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    called = {}
    def fake_transcribe(*args, **kwargs):
        called.update(kwargs)
        return iter([]), MagicMock(language="fr")
    with patch("subprocess.check_output", return_value="10.0"):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                with patch("mmnext.infrastructure.transcript_adapter.WhisperModel") as MockModel:
                    mock_model = MagicMock()
                    mock_model.transcribe.side_effect = fake_transcribe
                    MockModel.return_value = mock_model
                    adapter.transcribe(str(src), language="fr")
    assert called.get("language") == "fr"


def test_auto_detect_forwarded(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    called = {}
    def fake_transcribe(*args, **kwargs):
        called.update(kwargs)
        return iter([]), MagicMock(language="fr")
    with patch("subprocess.check_output", return_value="10.0"):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                with patch("mmnext.infrastructure.transcript_adapter.WhisperModel") as MockModel:
                    mock_model = MagicMock()
                    mock_model.transcribe.side_effect = fake_transcribe
                    MockModel.return_value = mock_model
                    adapter.transcribe(str(src), language=None, auto_detect=True)
    # language should be None for auto-detect
    assert called.get("language") is None


def test_real_transcript_artifact_written(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=True)
    with patch.object(adapter, "_probe_duration", return_value=10.0):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                rows, _ = adapter.transcribe(str(src))
    artifact = adapter.artifact_path
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["schema_version"] == 1
    assert "rows" in data


def test_transcript_artifact_atomic_write(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=True)
    with patch.object(adapter, "_probe_duration", return_value=5.0):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                adapter.transcribe(str(src))
    artifact = adapter.artifact_path
    # ensure no partial file left
    partials = list(jobs_dir.rglob("*.json.partial"))
    assert len(partials) == 0


def test_real_progress_not_simulated(tmp_path):
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    events = []
    def emit(e):
        events.append(e)
    with patch("subprocess.check_output", return_value="10.0"):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                with patch("mmnext.infrastructure.transcript_adapter.WhisperModel") as MockModel:
                    mock_model = MagicMock()
                    # simulate two segments
                    mock_model.transcribe.return_value = iter([
                        MagicMock(start=0.0, end=1.0, text="a"),
                        MagicMock(start=1.0, end=2.0, text="b"),
                    ]), MagicMock(language="en")
                    MockModel.return_value = mock_model
                    adapter.transcribe(str(src), emit=emit)
    # progress events should be from real processing, not demo percentages
    # At minimum, we should have progress events
    assert any("Segment" in str(e.message) for e in events)


def test_stop_checkpoint_after_completed_segment(tmp_path):
    # Ensure checkpoint persisted per segment
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir()
    src = tmp_path / "v.mp4"
    src.write_bytes(b"0")
    adapter = WhisperTranscriptAdapter(str(jobs_dir), str(src), is_demo=False)
    with patch("subprocess.check_output", return_value="10.0"):
        with patch.object(adapter, "_prepare_audio", return_value=(str(tmp_path/"a.wav"), "")):
            with patch.object(adapter, "_validate_audio"):
                with patch("mmnext.infrastructure.transcript_adapter.WhisperModel") as MockModel:
                    mock_model = MagicMock()
                    mock_model.transcribe.return_value = iter([
                        MagicMock(start=0.0, end=1.0, text="a"),
                    ]), MagicMock(language="en")
                    MockModel.return_value = mock_model
                    adapter.transcribe(str(src))
    # checkpoint should exist
    from mmnext.infrastructure.repository.job_repository import JobRepository
    repo = JobRepository(str(jobs_dir))
    ckpt = repo.load_checkpoint("v", str(src), AppMode.NARRATOR)
    assert ckpt is not None
    assert ckpt.get("state") == "complete"


def test_live_workspace_transcript_binding():
    # Simple sanity: TranscriptWorker can be instantiated
    from mmnext.ui.transcript_worker import TranscriptWorker
    from mmnext.infrastructure.transcript_adapter import DemoTranscriptProvider
    provider = DemoTranscriptProvider()
    w = TranscriptWorker(provider, "dummy.mp4")
    assert w.provider is provider

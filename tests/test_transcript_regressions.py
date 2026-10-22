"""Regression cases the original completion report did not really exercise."""
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import wave

import pytest

from mmnext.domain.enums import AppMode
from mmnext.domain.events import ProgressEvent
from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter


def backend(monkeypatch, tmp_path, rows=None):
    import mmnext.infrastructure.transcript_adapter as module
    src = tmp_path / "video.mp4"
    src.write_bytes(b"source")
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(src))
    monkeypatch.setattr(adapter, "_probe_duration", lambda p: 10.0)
    monkeypatch.setattr(adapter, "_prepare_audio", lambda p, d: (str(tmp_path / "audio.wav"), ""))
    model = MagicMock()
    model.transcribe.return_value = (
        iter(rows or [SimpleNamespace(start=1.25, end=4.5, text="bonjour")]),
        SimpleNamespace(language="fr"))
    monkeypatch.setattr(module, "WhisperModel", MagicMock(return_value=model))
    return adapter, src, model


def checkpoint(adapter, src):
    return adapter.repo.load_checkpoint(src.stem, str(src), adapter.mode)


def test_real_tuple_language_progress_and_artifact(monkeypatch, tmp_path):
    adapter, src, model = backend(monkeypatch, tmp_path)
    events = []
    rows, lang = adapter.transcribe(str(src), auto_detect=True, emit=events.append)
    assert lang == "fr"
    assert (rows[0].row_id, rows[0].start, rows[0].duration, rows[0].text) == ("s0", 1.25, 3.25, "bonjour")
    assert model.transcribe.call_args.kwargs["language"] is None
    progress = [e.percent for e in events if isinstance(e, ProgressEvent)]
    assert progress == [0.0, 45.0, 100.0]  # measured segment end / probed duration
    payload = json.loads(adapter.artifact_path.read_text(encoding="utf-8"))
    ckpt = checkpoint(adapter, src)
    assert payload["language"] == "fr" and payload["is_demo"] is False
    assert payload["fingerprint"] == ckpt["fingerprint"]
    assert ckpt["output_path"] == str(adapter.artifact_path)
    assert ckpt["state"] == "complete" and ckpt["resume_supported"] is False
    assert ckpt["completed_units"] == ckpt["total_units"] == 1


def test_generator_failure_is_failed_not_silent_success(monkeypatch, tmp_path):
    def broken():
        yield SimpleNamespace(start=0, end=1, text="first")
        raise RuntimeError("decoder failed")
    adapter, src, model = backend(monkeypatch, tmp_path)
    model.transcribe.return_value = broken(), SimpleNamespace(language="en")
    with pytest.raises(RuntimeError, match="decoder failed"):
        adapter.transcribe(str(src))
    assert not adapter.artifact_path.exists()
    ckpt = checkpoint(adapter, src)
    assert ckpt["state"] == "failed" and ckpt["completed_units"] == 1
    assert Path(ckpt["partial_path"]).exists()


def test_checkpoint_failure_is_not_swallowed(monkeypatch, tmp_path):
    adapter, src, _ = backend(monkeypatch, tmp_path)
    original = adapter.repo.save_checkpoint
    def fail_segment(job, source, mode, ckpt):
        if ckpt.completed_units:
            raise OSError("disk full")
        original(job, source, mode, ckpt)
    monkeypatch.setattr(adapter.repo, "save_checkpoint", fail_segment)
    with pytest.raises(OSError, match="disk full"):
        adapter.transcribe(str(src))
    assert not adapter.artifact_path.exists()


def test_artifact_commit_failure_never_marks_complete(monkeypatch, tmp_path):
    adapter, src, _ = backend(monkeypatch, tmp_path)
    def fail(*a):
        raise OSError("artifact commit failed")
    monkeypatch.setattr(adapter, "_write_transcript_artifact", fail)
    with pytest.raises(OSError, match="artifact commit failed"):
        adapter.transcribe(str(src))
    assert checkpoint(adapter, src)["state"] == "failed"


@pytest.mark.parametrize("duration", ["nan", "inf", "-1", "0"])
def test_invalid_real_duration_rejected(monkeypatch, tmp_path, duration):
    adapter = WhisperTranscriptAdapter(str(tmp_path), str(tmp_path / "a.mp4"))
    monkeypatch.setattr("subprocess.check_output", lambda *a, **kw: duration)
    with pytest.raises(RuntimeError, match="duration"):
        adapter._probe_duration("a.mp4")


def wav_bytes(rate=16000, channels=1, seconds=1.0):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(rate * channels * seconds))
    return output.getvalue()


def test_audio_is_validated_before_atomic_rename(monkeypatch, tmp_path):
    src = tmp_path / "a.mp4"
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(src))
    commands = []
    def extract(command, **kw):
        commands.append(command)
        Path(command[-1]).write_bytes(wav_bytes())
        return b""
    monkeypatch.setattr("subprocess.check_output", extract)
    final, partial = adapter._prepare_audio(str(src), 2.0)
    assert Path(final).is_file() and not Path(partial).exists()
    assert commands[0][-1].endswith(".partial")
    assert commands[0][commands[0].index("-c:a") + 1] == "pcm_s16le"
    with wave.open(final) as audio:
        assert audio.getframerate() == 16000 and audio.getnchannels() == 1
    # Invalid new output cannot replace the previous valid WAV.
    def invalid(command, **kw):
        Path(command[-1]).write_bytes(b"invalid" * 1000)
    monkeypatch.setattr("subprocess.check_output", invalid)
    before = Path(final).read_bytes()
    with pytest.raises(RuntimeError, match="Invalid PCM"):
        adapter._prepare_audio(str(src), 2.0)
    assert Path(final).read_bytes() == before


@pytest.mark.parametrize("kwargs, message", [({"channels": 2}, "mono"), ({"rate": 8000}, "16 kHz"), ({"seconds": 3.0}, "duration")])
def test_audio_contract_checked(tmp_path, kwargs, message):
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), "a.mp4")
    audio = tmp_path / "audio.wav.partial"
    audio.write_bytes(wav_bytes(**kwargs))
    with pytest.raises(RuntimeError, match=message):
        adapter._validate_audio(str(audio), 2.0)


def test_same_stem_sources_and_modes_have_isolated_artifacts(tmp_path):
    a = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(tmp_path / "one" / "v.mp4"))
    b = WhisperTranscriptAdapter(str(tmp_path / "jobs"), str(tmp_path / "two" / "v.mp4"))
    c = WhisperTranscriptAdapter(str(tmp_path / "jobs"), a.source_path, mode=AppMode.EXACT_DUBBING)
    assert len({a.artifact_path, b.artifact_path, c.artifact_path}) == 3
    assert len({a.work_dir / "audio_tmp", b.work_dir / "audio_tmp", c.work_dir / "audio_tmp"}) == 3


def test_optional_real_local_transcript(tmp_path):
    """Opt-in only: do not download models or touch arbitrary user media.

    Use the *full-speech* fixture, not an artificially clipped one.  A clip
    cuts an utterance in half, so Whisper's final segment legitimately ends
    after the clip boundary; the strict adapter rejects that on purpose and
    this test must fail for a clipped source.  The accepted fixture keeps the
    complete recording, so every row ends inside the authoritative duration
    with zero tolerance.
    """
    import importlib.util
    import os
    import shutil
    media = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MEDIA")
    model = os.environ.get("MMNEXT_TRANSCRIPT_SMOKE_MODEL")
    if not media or not model:
        pytest.skip(
            "Provide an approved media fixture and a local cached Whisper model directory for real smoke"
        )
    if not Path(media).is_file() or not Path(model).is_dir():
        pytest.skip("Local media/model fixture unavailable")
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg") or not importlib.util.find_spec("faster_whisper"):
        pytest.skip("Optional local transcription tools unavailable")
    adapter = WhisperTranscriptAdapter(str(tmp_path / "jobs"), media, whisper_model=model)
    rows, language = adapter.transcribe(media, auto_detect=True)
    assert adapter.artifact_path.exists()
    assert language and isinstance(rows, list)
    # Zero tolerance: every row must end inside the authoritative duration.
    assert rows and all(0 <= r.start < r.end <= adapter._duration for r in rows)
    assert checkpoint(adapter, Path(media))["state"] == "complete"


@pytest.mark.parametrize("end", [10.000001, 11.0, 13.0])
def test_out_of_bounds_segment_never_commits_or_completes(monkeypatch, tmp_path, end):
    adapter, src, _ = backend(monkeypatch, tmp_path, [
        SimpleNamespace(start=0.25, end=2.75, text="မြန်မာ မူရင်းစာ"),
        SimpleNamespace(start=9.0, end=end, text="unchanged rejected source"),
    ])
    events = []
    with pytest.raises(RuntimeError, match="authoritative video duration"):
        adapter.transcribe(str(src), emit=events.append)
    ckpt = checkpoint(adapter, src)
    assert ckpt["state"] == "failed" and ckpt["completed_units"] == 1
    assert "s1" in ckpt["message"] and "restart" in ckpt["message"]
    assert all(e.percent < 100 for e in events if isinstance(e, ProgressEvent))
    assert not adapter.artifact_path.exists()
    partial = json.loads(Path(ckpt["partial_path"]).read_text(encoding="utf-8"))
    assert partial["rows"] == [{"row_id": "s0", "start": 0.25,
                               "duration": 2.5, "text": "မြန်မာ မူရင်းစာ"}]


def test_exact_duration_boundary_preserves_source(monkeypatch, tmp_path):
    adapter, src, _ = backend(monkeypatch, tmp_path, [
        SimpleNamespace(start=8.25, end=10.0, text="Original မူရင်းစာ"),
    ])
    rows, _ = adapter.transcribe(str(src))
    assert (rows[0].row_id, rows[0].start, rows[0].duration, rows[0].text) == (
        "s0", 8.25, 1.75, "Original မူရင်းစာ")
    assert checkpoint(adapter, src)["state"] == "complete"


def test_artifact_writer_rechecks_bounds_and_keeps_existing_file(monkeypatch, tmp_path):
    from mmnext.domain.models import TranscriptRow
    adapter, src, _ = backend(monkeypatch, tmp_path)
    adapter.artifact_path.parent.mkdir(parents=True, exist_ok=True)
    adapter.artifact_path.write_text("previous valid artifact", encoding="utf-8")
    with pytest.raises(RuntimeError, match="authoritative video duration"):
        adapter._write_transcript_artifact(str(src), [
            TranscriptRow("stable-id", 9.0, 2.0, "unchanged")], "en", 10.0)
    assert adapter.artifact_path.read_text(encoding="utf-8") == "previous valid artifact"


def test_final_gate_rejects_invalid_provider_rows(monkeypatch, tmp_path):
    from mmnext.domain.models import TranscriptRow
    adapter, src, _ = backend(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter, "_run_whisper", lambda *a: [
        TranscriptRow("stable-id", 9.0, 2.0, "unchanged")])
    events = []
    with pytest.raises(RuntimeError, match="authoritative video duration"):
        adapter.transcribe(str(src), emit=events.append)
    assert checkpoint(adapter, src)["state"] == "failed"
    assert not adapter.artifact_path.exists()
    assert all(e.percent < 100 for e in events if isinstance(e, ProgressEvent))


@pytest.mark.parametrize("start,end", [(-1.0, 1.0), (1.0, 1.0), (2.0, 1.0),
                                        (float("nan"), 2.0), (0.0, float("inf"))])
def test_invalid_timing_never_completes(monkeypatch, tmp_path, start, end):
    adapter, src, _ = backend(monkeypatch, tmp_path, [
        SimpleNamespace(start=start, end=end, text="unchanged source")])
    events = []
    with pytest.raises(RuntimeError, match="invalid segment timing"):
        adapter.transcribe(str(src), emit=events.append)
    assert checkpoint(adapter, src)["state"] == "failed"
    assert not adapter.artifact_path.exists()
    assert all(e.percent < 100 for e in events if isinstance(e, ProgressEvent))


def test_adapter_fingerprint_matches_artifact_fingerprint(monkeypatch, tmp_path):
    """The persisted artefact carries the same canonical fingerprint the
    adapter exposes, so re-open can re-derive and verify it instead of
    guessing which settings produced it."""
    import json
    adapter, src, _ = backend(monkeypatch, tmp_path)
    rows, language = adapter.transcribe(str(src), auto_detect=True)
    assert adapter.fingerprint, "adapter fingerprint must be set after transcribe"
    payload = json.loads(adapter.artifact_path.read_text(encoding="utf-8"))
    assert payload["fingerprint"] == adapter.fingerprint
    assert payload["fingerprint"].startswith("fp2:")
    assert payload["fingerprint_settings"] == adapter._fingerprint_settings_value
    assert payload["fingerprint_schema_version"] == 1
    assert payload["fingerprint_source_type"] == "local_file"
    assert rows, "real transcription should produce rows"

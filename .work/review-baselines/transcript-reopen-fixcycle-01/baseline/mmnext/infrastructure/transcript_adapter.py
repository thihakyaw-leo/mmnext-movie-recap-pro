"""Local transcript adapters. Real work never falls back to demo rows."""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from threading import Event
from typing import Callable, Optional, Tuple

from ..domain.models import TranscriptRow, JobCheckpoint
from ..domain.events import ProgressEvent, LogEvent
from ..domain.enums import Stage, TaskState, AppMode
from ..domain.paths import atomic_write_json
from .repository.job_repository import JobRepository

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

__all__ = ["DemoTranscriptProvider", "WhisperTranscriptAdapter", "TranscriptStopped"]


class TranscriptStopped(RuntimeError):
    """Cooperative stop, raised only after the checkpoint is durable."""


class DemoTranscriptProvider:
    def __init__(self, rows: Optional[list[TranscriptRow]] = None):
        self._rows = rows or []

    def transcribe(self, media_path, language=None, auto_detect=False, emit=None):
        if emit:
            for p in [0, 25, 50, 75, 100]:
                emit(ProgressEvent(stage=Stage.TRANSCRIBE, percent=float(p), message=f"Demo progress {p}%"))
        return self._rows, "en" if auto_detect else (language or "en").lower()


class WhisperTranscriptAdapter:
    """FFprobe -> validated PCM audio -> faster-whisper -> atomic transcript.

    Stop waits for the current blocking operation/segment. Restart, not
    mid-operation resume, is supported. No translation/planning happens here.
    """
    def __init__(self, jobs_dir: str, source_path: str, mode: AppMode = AppMode.NARRATOR,
                 whisper_model: str = "base", device: str = "cpu", is_demo: bool = False):
        self.jobs_dir = Path(jobs_dir)
        self.source_path = source_path
        self.mode = mode
        self.whisper_model = whisper_model
        self.device = device
        self.is_demo = is_demo
        self.repo = JobRepository(jobs_dir)
        self.task_id = f"transcribe_{Path(source_path).stem}"
        self.job_id = Path(source_path).stem
        self._stop = Event()
        self._detected_language = ""
        self._duration = 0.0
        self._fingerprint_value = ""
        # Keep the v1 file name, but scope its parent to source and mode to
        # prevent two same-stem videos or modes overwriting one another.
        self.work_dir = self.repo._job_dir(self.job_id, source_path) / mode.value
        self.artifact_path = self.work_dir / "transcripts" / f"{Path(source_path).stem}.transcript.json"

    def request_stop(self):
        self._stop.set()

    def _save(self, ckpt):
        ckpt.updated_at = self._now()
        self.repo.save_checkpoint(self.job_id, self.source_path, self.mode, ckpt)

    def _check_stop(self, ckpt):
        if self._stop.is_set():
            ckpt.state = TaskState.STOPPED
            ckpt.message = "Stopped at safe boundary; resume unsupported. Restart transcription."
            self._save(ckpt)
            raise TranscriptStopped(ckpt.message)

    def transcribe(self, media_path: str, language: Optional[str] = None,
                   auto_detect: bool = False, emit: Optional[Callable[[object], None]] = None
                   ) -> Tuple[list[TranscriptRow], str]:
        if Path(media_path).resolve() != Path(self.source_path).resolve():
            raise ValueError("Transcript source does not match job source")
        self._fingerprint_value = self._fingerprint(media_path, language, auto_detect)
        ckpt = JobCheckpoint(task_id=self.task_id, mode=self.mode.value,
                             state=TaskState.RUNNING, resume_supported=False,
                             fingerprint=self._fingerprint_value, message="Probing local media")
        self._save(ckpt)
        try:
            self._check_stop(ckpt)
            if emit:
                emit(ProgressEvent(stage=Stage.TRANSCRIBE, message="Probing media and preparing audio"))
            try:
                duration = self._probe_duration(media_path)
            except RuntimeError:
                if not self.is_demo:
                    raise
                duration = 0.0
            self._duration = duration
            self._check_stop(ckpt)
            audio_path, partial = self._prepare_audio(media_path, duration)
            ckpt.partial_path = partial
            ckpt.output_path = audio_path
            ckpt.message = "Audio prepared; loading Whisper (restart only)"
            self._save(ckpt)
            self._check_stop(ckpt)
            self._detected_language = "" if auto_detect else (language or "en")
            rows = self._run_whisper(audio_path, self._detected_language, emit, ckpt)
            self._check_stop(ckpt)
            artifact = self._write_transcript_artifact(media_path, rows, self._detected_language, duration)
            # A complete checkpoint points at the transcript, not merely audio.
            ckpt.output_path = str(artifact)
            ckpt.partial_path = ""
            ckpt.completed_units = len(rows)
            ckpt.total_units = len(rows)
            ckpt.state = TaskState.COMPLETE
            ckpt.message = "Transcript artifact committed"
            self._save(ckpt)
            if emit:
                emit(ProgressEvent(stage=Stage.TRANSCRIBE, percent=100.0, message=ckpt.message))
            return rows, self._detected_language
        except TranscriptStopped:
            raise
        except Exception as exc:
            ckpt.state = TaskState.FAILED
            ckpt.message = f"Transcription failed: {exc}. Fix dependency/input and restart; resume unsupported."
            self._save(ckpt)
            raise

    def _now(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _probe_duration(self, media_path):
        try:
            out = subprocess.check_output([
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", media_path,
            ], stderr=subprocess.DEVNULL, text=True).strip()
            duration = float(out)
        except FileNotFoundError as exc:
            raise RuntimeError("FFprobe not found; install FFmpeg tools and restart") from exc
        except (subprocess.CalledProcessError, ValueError) as exc:
            raise RuntimeError(f"FFprobe failed for {media_path}: {exc}") from exc
        if not math.isfinite(duration) or duration < 0 or (duration == 0 and not self.is_demo):
            raise RuntimeError("FFprobe returned zero duration or invalid duration")
        return duration

    def _prepare_audio(self, media_path, duration):
        out_dir = self.work_dir / "audio_tmp"
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_path = out_dir / f"{Path(media_path).stem}.wav"
        partial = str(audio_path) + ".partial"
        if self.is_demo:
            Path(partial).write_bytes(b"\0" * 2048)
        else:
            try:
                subprocess.check_output([
                    "ffmpeg", "-y", "-i", media_path, "-t", str(duration),
                    "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", partial,
                ], stderr=subprocess.STDOUT)
            except FileNotFoundError as exc:
                raise RuntimeError("FFmpeg not found; install FFmpeg tools and restart") from exc
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"FFmpeg audio extraction failed for {media_path}: {exc}") from exc
        self._validate_audio(partial, duration)
        os.replace(partial, audio_path)
        return str(audio_path), partial

    def _validate_audio(self, audio_path, duration):
        path = Path(audio_path)
        if not path.exists():
            raise RuntimeError("Audio file missing after extraction")
        if path.stat().st_size < 1024:
            raise RuntimeError("Audio file too small, extraction likely failed")
        if not self.is_demo:
            import wave
            try:
                with wave.open(str(path), "rb") as audio:
                    actual = audio.getnframes() / audio.getframerate()
                    if (audio.getnchannels(), audio.getframerate(), audio.getsampwidth()) != (1, 16000, 2):
                        raise RuntimeError("Audio must be mono 16 kHz PCM16")
                    if actual <= 0 or actual > duration + 0.1:
                        raise RuntimeError("Audio duration exceeds authoritative video duration or is empty")
            except (wave.Error, EOFError) as exc:
                raise RuntimeError("Invalid PCM WAV audio") from exc

    def _write_transcript_artifact(self, media_path, rows, language, duration):
        # Validate again at the atomic commit boundary, including alternate
        # provider paths. Never clamp, drop, or retime source rows to pass.
        if not self.is_demo:
            for row in rows:
                self._validate_segment_timing(row.row_id, row.start, row.end, duration)
        atomic_write_json(self.artifact_path, {
            "schema_version": 1, "source_path": media_path,
            "fingerprint": self._fingerprint_value, "model": self.whisper_model,
            "language": language, "duration_s": duration, "created_at": self._now(),
            "is_demo": self.is_demo,
            "rows": [{"row_id": r.row_id, "start": r.start, "duration": r.duration, "text": r.text} for r in rows],
        })
        return self.artifact_path

    def _fingerprint(self, media_path, language, auto_detect):
        settings = {"language": language, "auto_detect": auto_detect, "model": self.whisper_model, "schema": 1}
        try:
            stat = os.stat(media_path)
            size, mtime = stat.st_size, stat.st_mtime_ns
        except OSError:
            size, mtime = 0, 0
        raw = f"{Path(media_path).resolve()}|{size}|{mtime}|{self.mode.value}|" + json.dumps(settings, sort_keys=True)
        return hashlib.sha1(raw.encode()).hexdigest()

    def _validate_segment_timing(self, row_id, start, end, duration):
        if (not all(math.isfinite(v) for v in (start, end, duration))
                or duration <= 0 or start < 0 or end <= start):
            raise RuntimeError(f"Whisper returned invalid segment timing for {row_id}: [{start}, {end}]")
        if end > duration:
            raise RuntimeError(
                f"Whisper segment {row_id} [{start}, {end}] exceeds authoritative video duration "
                f"{duration}s for {self.source_path}; source timing unchanged. "
                "Inspect input/model output and restart transcription")

    def _run_whisper(self, audio_path, language, emit, ckpt):
        if self.is_demo:
            rows = [TranscriptRow(f"s{i}", float(i * 5), 4.5, f"Demo transcript segment {i}") for i in range(10)]
            if emit:
                emit(ProgressEvent(stage=Stage.TRANSCRIBE, percent=50.0, message="Demo transcription"))
            return rows
        if WhisperModel is None:
            raise RuntimeError("faster-whisper not available; install the optional local transcription dependency")
        model = WhisperModel(self.whisper_model, device=self.device, compute_type="int8")
        self._check_stop(ckpt)
        segments, info = model.transcribe(audio_path, language=language or None, beam_size=5)
        self._detected_language = str(info.language or language or "")
        rows = []
        for segment in segments:
            start, end = float(segment.start), float(segment.end)
            self._validate_segment_timing(f"s{len(rows)}", start, end, self._duration)
            # Never silently invent, merge, or drop source rows.
            row = TranscriptRow(f"s{len(rows)}", start, end - start, str(segment.text).strip())
            rows.append(row)
            ckpt.completed_units = len(rows)
            ckpt.message = f"Segment {row.row_id} processed; restart only"
            # Preserve completed text/timing too, not just an in-memory count.
            partial = self.artifact_path.with_suffix(".segments.json")
            atomic_write_json(partial, {"schema_version": 1, "fingerprint": self._fingerprint_value,
                                       "rows": [{"row_id": r.row_id, "start": r.start, "duration": r.duration, "text": r.text} for r in rows]})
            ckpt.partial_path = str(partial)
            self._save(ckpt)
            self._check_stop(ckpt)
            if emit:
                percent = min(99.0, max(0.0, end / self._duration * 100.0)) if self._duration > 0 else 0.0
                emit(ProgressEvent(stage=Stage.TRANSCRIBE, percent=percent, message=f"Segment {row.row_id} ({end:.2f}s processed)"))
        return rows

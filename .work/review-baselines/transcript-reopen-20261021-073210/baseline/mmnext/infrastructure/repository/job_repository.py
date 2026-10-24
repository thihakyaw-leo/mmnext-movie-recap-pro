"""Disk-backed job repository with versioned schema and recovery.

The repository never touches the current working directory. All paths are
derived from the configured ``jobs_dir`` together with source identity,
mode and job id, so jobs are isolated per source and per mode.

The schema version is explicit and every write is atomic. Corrupt JSON
files are detected and reported without crashing the application.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from mmnext.domain.enums import AppMode, JobState, TaskState, SourceType, Stage
from mmnext.domain.models import Job, JobProgress, JobCheckpoint, VideoSource
from mmnext.domain.paths import atomic_write_json, read_json, safe_name
from mmnext.domain.models import CHECKPOINT_SCHEMA_VERSION

__all__ = [
    "JOB_SCHEMA_VERSION",
    "JobRepository",
    "FingerprintError",
    "ResumeCheckResult",
]

JOB_SCHEMA_VERSION = 1

class FingerprintError(ValueError):
    pass

class ResumeCheckResult:
    """Structured result for a resume eligibility check."""
    def __init__(self, allowed: bool, reasons: Optional[List[str]] = None) -> None:
        self.allowed = allowed
        self.reasons = reasons or []

    def __bool__(self) -> bool:
        return self.allowed

    def __repr__(self) -> str:
        return f"ResumeCheckResult(allowed={self.allowed}, reasons={self.reasons})"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()

def _source_identity(source_path: str, source_type: str) -> str:
    return f"{source_type}:{source_path}"

def _file_meta(path: str) -> Tuple[int, float]:
    try:
        st = os.stat(path)
        return int(st.st_size), float(st.st_mtime)
    except OSError:
        return 0, 0.0

def compute_fingerprint(
    source_path: str,
    source_type: str,
    mode: AppMode,
    settings: Optional[Dict[str, Any]] = None,
    schema_version: int = JOB_SCHEMA_VERSION,
) -> str:
    settings = settings or {}
    settings_bytes = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode("utf-8")
    size, mtime = _file_meta(source_path) if source_type == "local" else (0, 0.0)
    raw = f"{_source_identity(source_path, source_type)}|{size}|{mtime:.3f}|{mode.value}|{schema_version}|"
    raw_bytes = raw.encode("utf-8") + settings_bytes
    return _sha1_hex(raw_bytes)


class JobRepository:
    """Versioned, atomic, job-scoped persistence."""

    def __init__(self, jobs_dir: str | Path) -> None:
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _source_hash(self, source_path: str) -> str:
        try:
            resolved = Path(source_path).resolve()
        except Exception:
            resolved = Path(source_path)
        return hashlib.sha1(str(resolved).encode("utf-8")).hexdigest()[:8]

    def _source_dir(self, source_path: str) -> Path:
        stem = safe_name(Path(source_path).stem)
        h = self._source_hash(source_path)
        return self.jobs_dir / f"{stem}_{h}"

    def _job_dir(self, job_id: str, source_path: str) -> Path:
        return self._source_dir(source_path) / "jobs" / job_id

    def _metadata_path(self, job_id: str, source_path: str) -> Path:
        return self._job_dir(job_id, source_path) / "metadata.json"

    def _checkpoint_path(self, job_id: str, source_path: str, mode: AppMode) -> Path:
        ckpt_dir = self._job_dir(job_id, source_path) / "checkpoints" / mode.value
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        return ckpt_dir / "checkpoint.json"

    def _job_to_dict(self, job: Job) -> Dict[str, Any]:
        stage_val = job.progress.stage.value if isinstance(job.progress.stage, Stage) else str(job.progress.stage)
        data = {
            "schema_version": JOB_SCHEMA_VERSION,
            "job_id": job.job_id,
            "title": job.title,
            "mode": job.mode.value,
            "state": job.state.value,
            "task_state": job.task_state.value,
            "is_demo": bool(job.is_demo),
            "created_at": job.created_at or _iso_now(),
            "updated_at": _iso_now(),
            "output_path": job.output_path,
            "error_message": job.error_message,
            "progress": {
                "percent": job.progress.percent,
                "stage": stage_val,
                "message": job.progress.message,
                "bytes_done": job.progress.bytes_done,
                "bytes_total": job.progress.bytes_total,
                "speed_bps": job.progress.speed_bps,
                "eta_s": job.progress.eta_s,
            },
            "source": {
                "type": job.source.source_type.value if job.source else None,
                "location": job.source.location if job.source else "",
                "display_name": job.source.display_name if job.source else "",
                "duration_s": job.source.duration_s if job.source else 0.0,
            } if job.source else None,
            "fingerprint": getattr(job, "fingerprint", ""),
        }
        return data

    def _dict_to_job(self, data: Dict[str, Any]) -> Job:
        from mmnext.domain.models import VideoSource
        from mmnext.domain.enums import SourceType, Stage
        src_data = data.get("source")
        src = None
        if src_data:
            st = src_data.get("type")
            try:
                st_enum = SourceType(st) if st else SourceType.LOCAL_FILE
            except ValueError:
                st_enum = SourceType.LOCAL_FILE
            src = VideoSource(
                source_type=st_enum,
                location=str(src_data.get("location", "")),
                display_name=str(src_data.get("display_name", "")),
                duration_s=float(src_data.get("duration_s", 0.0) or 0.0),
            )
        prog = data.get("progress", {})
        stage_val = prog.get("stage", Stage.IDLE.value)
        try:
            stage_enum = Stage(stage_val)
        except Exception:
            stage_enum = Stage.IDLE
        progress = JobProgress(
            percent=float(prog.get("percent", 0.0) or 0.0),
            stage=stage_enum,
            message=str(prog.get("message", "") or ""),
            bytes_done=int(prog.get("bytes_done", 0) or 0),
            bytes_total=int(prog.get("bytes_total", 0) or 0),
            speed_bps=float(prog.get("speed_bps", 0.0) or 0.0),
            eta_s=float(prog.get("eta_s", 0.0) or 0.0),
        )
        try:
            mode_enum = AppMode(data.get("mode", AppMode.COMMON_EDITING.value))
        except Exception:
            mode_enum = AppMode.COMMON_EDITING
        try:
            state_enum = JobState(data.get("state", JobState.NEW.value))
        except Exception:
            state_enum = JobState.NEW
        try:
            task_state_enum = TaskState(data.get("task_state", TaskState.QUEUED.value))
        except Exception:
            task_state_enum = TaskState.QUEUED

        job = Job(
            job_id=str(data.get("job_id", "")),
            title=str(data.get("title", "")),
            mode=mode_enum,
            state=state_enum,
            task_state=task_state_enum,
            progress=progress,
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            source=src,
            output_path=str(data.get("output_path", "") or ""),
            error_message=str(data.get("error_message", "") or ""),
            is_demo=bool(data.get("is_demo", True)),
        )
        return job

    def create(self, job: Job, source_path: str) -> Job:
        path = self._metadata_path(job.job_id, source_path)
        if path.exists():
            raise FileExistsError(f"Job {job.job_id} already exists")
        self.save(job, source_path)
        return job

    def save(self, job: Job, source_path: str) -> None:
        job_dir = self._job_dir(job.job_id, source_path)
        job_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self._metadata_path(job.job_id, source_path), self._job_to_dict(job))

    def load(self, job_id: str, source_path: str) -> Optional[Job]:
        path = self._metadata_path(job_id, source_path)
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            return None
        sv = int(data.get("schema_version", 0) or 0)
        if sv != JOB_SCHEMA_VERSION:
            return None
        try:
            return self._dict_to_job(data)
        except Exception:
            return None

    def list_jobs(self, source_path: Optional[str] = None) -> List[Job]:
        jobs: List[Job] = []
        if source_path:
            base = self._source_dir(source_path) / "jobs"
            if not base.exists():
                return jobs
            for job_dir in base.iterdir():
                if not job_dir.is_dir():
                    continue
                meta = job_dir / "metadata.json"
                if not meta.exists():
                    continue
                data = read_json(meta)
                if not data:
                    continue
                try:
                    job = self._dict_to_job(data)
                    jobs.append(job)
                except Exception:
                    continue
        else:
            if not self.jobs_dir.exists():
                return jobs
            for src_dir in self.jobs_dir.iterdir():
                if not src_dir.is_dir():
                    continue
                jobs_dir = src_dir / "jobs"
                if not jobs_dir.exists():
                    continue
                for job_dir in jobs_dir.iterdir():
                    if not job_dir.is_dir():
                        continue
                    meta = job_dir / "metadata.json"
                    if not meta.exists():
                        continue
                    data = read_json(meta)
                    if not data:
                        continue
                    try:
                        job = self._dict_to_job(data)
                        jobs.append(job)
                    except Exception:
                        continue
        return jobs

    def list_incomplete(self, source_path: Optional[str] = None) -> List[Job]:
        all_jobs = self.list_jobs(source_path)
        return [j for j in all_jobs if j.state not in (JobState.COMPLETE, JobState.CANCELLED)]

    def update_state(self, job_id: str, source_path: str, new_state: JobState, progress: Optional[JobProgress] = None) -> Optional[Job]:
        job = self.load(job_id, source_path)
        if not job:
            return None
        job.state = new_state
        if progress:
            job.progress = progress
        self.save(job, source_path)
        return job

    def mark_complete(self, job_id: str, source_path: str) -> Optional[Job]:
        return self.update_state(job_id, source_path, JobState.COMPLETE)

    def mark_failed(self, job_id: str, source_path: str, message: str = "") -> Optional[Job]:
        job = self.load(job_id, source_path)
        if not job:
            return None
        job.state = JobState.FAILED
        job.error_message = message
        self.save(job, source_path)
        return job

    def save_checkpoint(self, job_id: str, source_path: str, mode: AppMode, checkpoint: Any) -> None:
        path = self._checkpoint_path(job_id, source_path, mode)
        if hasattr(checkpoint, "to_dict"):
            data = checkpoint.to_dict()
        else:
            data = dict(checkpoint)
        atomic_write_json(path, data)

    def load_checkpoint(self, job_id: str, source_path: str, mode: AppMode) -> Optional[dict]:
        path = self._checkpoint_path(job_id, source_path, mode)
        if not path.exists():
            return None
        data = read_json(path)
        if not data:
            try:
                path.unlink()
            except Exception:
                pass
            return None
        sv = int(data.get("schema_version", 0) or 0)
        if sv != CHECKPOINT_SCHEMA_VERSION:
            return None
        return data

    def scan(self) -> Dict[str, List[Any]]:
        recoverable: List[Tuple[Job, str]] = []
        corrupt: List[Path] = []
        if not self.jobs_dir.exists():
            return {"recoverable": [], "corrupt": []}
        for src_dir in self.jobs_dir.iterdir():
            if not src_dir.is_dir():
                continue
            jobs_dir = src_dir / "jobs"
            if not jobs_dir.exists():
                continue
            for job_dir in jobs_dir.iterdir():
                if not job_dir.is_dir():
                    continue
                meta_path = job_dir / "metadata.json"
                if not meta_path.exists():
                    continue
                try:
                    data = read_json(meta_path)
                    if not data:
                        corrupt.append(meta_path)
                        continue
                    sv = int(data.get("schema_version", 0) or 0)
                    if sv != JOB_SCHEMA_VERSION:
                        corrupt.append(meta_path)
                        continue
                    job = self._dict_to_job(data)
                    if job.state not in (JobState.COMPLETE, JobState.CANCELLED):
                        recoverable.append((job, str(src_dir)))
                except Exception:
                    corrupt.append(meta_path)
                    continue
        return {"recoverable": recoverable, "corrupt": corrupt}

    def can_resume_job(self, job_id: str, source_path: str, mode: AppMode) -> ResumeCheckResult:
        job = self.load(job_id, source_path)
        if not job:
            return ResumeCheckResult(False, ["Job not found"])
        if job.state == JobState.COMPLETE:
            return ResumeCheckResult(False, ["Job already complete"])
        if job.mode != mode:
            return ResumeCheckResult(False, ["Mode mismatch"])
        ckpt_data = self.load_checkpoint(job_id, source_path, mode)
        if not ckpt_data:
            return ResumeCheckResult(False, ["No checkpoint found"])
        try:
            ckpt = JobCheckpoint.from_dict(ckpt_data)
        except Exception:
            return ResumeCheckResult(False, ["Corrupt checkpoint"])
        if not ckpt.resume_supported:
            return ResumeCheckResult(False, ["Resume not supported"])
        if ckpt.state not in (TaskState.PAUSED, TaskState.STOPPED):
            return ResumeCheckResult(False, [f"Checkpoint state not resumable: {ckpt.state.value}"])
        current_fp = compute_fingerprint(
            source_path,
            job.source.source_type.value if job.source else "",
            mode,
            schema_version=JOB_SCHEMA_VERSION,
        )
        if ckpt.fingerprint and ckpt.fingerprint != current_fp:
            return ResumeCheckResult(False, ["Fingerprint mismatch"])
        if ckpt.partial_path and not Path(ckpt.partial_path).exists():
            return ResumeCheckResult(False, ["Partial artifact missing"])
        return ResumeCheckResult(True, [])

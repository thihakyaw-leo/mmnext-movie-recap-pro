"""Real metadata adapters for local files and YouTube."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ...domain.enums import SourceType
from ...domain.models import SourceMetadata, VideoQuality, VideoSource
from ...services.protocols import MetadataService


class ToolUnavailableError(RuntimeError):
    """Raised when a required external tool is unavailable for real mode."""


class LocalFileMetadataService(MetadataService):
    """Probe a local video file with ffprobe, fallback to basic info."""

    def analyze(self, source: VideoSource, is_demo: bool = True) -> SourceMetadata:
        if source.source_type is not SourceType.LOCAL_FILE:
            raise ValueError("LocalFileMetadataService requires a local file source")
        path = Path(source.location)
        if not path.is_file():
            raise FileNotFoundError(f"Local file not found: {source.location}")

        # Try ffprobe for duration
        duration = 0.0
        tool_ok = False
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                out = result.stdout.strip()
                if out:
                    duration = float(out)
                    tool_ok = True
        except Exception:
            tool_ok = False
        if not tool_ok and not is_demo:
            raise ToolUnavailableError("ffprobe is required for real local file analysis but is unavailable")


        # Basic quality list – one entry derived from file size
        stats = path.stat()
        size_mb = stats.st_size / (1024 * 1024)
        qualities = [
            VideoQuality(
                quality_id="source",
                label="Source",
                width=0,
                height=0,
                fps=0,
                bitrate_kbps=0,
                filesize_mb=size_mb,
            )
        ]

        return SourceMetadata(
            title=path.stem,
            channel="Local",
            duration_s=duration,
            published="",
            description="",
            thumbnail_hint="",
            qualities=qualities,
            has_audio=True,
            has_video=True,
            language="en",
        )


class YouTubeMetadataService(MetadataService):
    """Fetch metadata via yt-dlp without downloading."""

    def analyze(self, source: VideoSource, is_demo: bool = True) -> SourceMetadata:
        if source.source_type is not SourceType.YOUTUBE:
            raise ValueError("YouTubeMetadataService requires a YouTube source")
        url = source.location.strip()
        if not url or "youtube.com" not in url and "youtu.be" not in url:
            raise ValueError("Invalid YouTube URL")

        tool_ok = False
        # Try yt-dlp
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--dump-json",
                "--skip-download",
                url,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and result.stdout:
                import json
                data = json.loads(result.stdout.splitlines()[0])
                duration = float(data.get("duration") or 0)
                qualities = [
                    VideoQuality(
                        quality_id=f"{h}p",
                        label=f"{h}p",
                        width=data.get("width", 0) or 0,
                        height=data.get("height", 0) or 0,
                        fps=data.get("fps", 0) or 0.0,
                        bitrate_kbps=0,
                        filesize_mb=data.get("filesize_approx", 0) or 0.0 / (1024*1024),
                    )
                    for h in [360, 480, 720, 1080]
                    if duration > 0
                ]
                if not qualities:
                    qualities = [
                        VideoQuality(
                            quality_id="best",
                            label="Best",
                            width=0,
                            height=0,
                            fps=0,
                            bitrate_kbps=0,
                            filesize_mb=0,
                        )
                    ]
                tool_ok = True
                return SourceMetadata(
                    title=data.get("title", url),
                    channel=data.get("uploader", ""),
                    duration_s=duration,
                    published=data.get("upload_date", ""),
                    description=data.get("description", ""),
                    thumbnail_hint=data.get("thumbnail", ""),
                    qualities=qualities,
                    has_audio=True,
                    has_video=True,
                    language=data.get("language", "en"),
                )
        except Exception:
            tool_ok = False
        if not tool_ok:
            if is_demo:
                return SourceMetadata(
                    title="YouTube video (demo)",
                    channel="",
                    duration_s=0,
                    published="",
                    description="",
                    qualities=[
                        VideoQuality(
                            quality_id="best",
                            label="Best",
                            width=0,
                            height=0,
                            fps=0,
                            bitrate_kbps=0,
                            filesize_mb=0,
                        )
                    ],
                    has_audio=True,
                    has_video=True,
                    language="en",
                )
            raise ToolUnavailableError("yt-dlp is required for real YouTube analysis but is unavailable")

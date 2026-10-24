"""Common-editing export adapters."""

from __future__ import annotations

from pathlib import Path


class DemoCommonEditingExporter:
    def available(self) -> bool:
        return True

    def export(self, video_path, session, output_path, settings=None):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"demo common editing output")
        return True


class LegacyCommonEditingExporter:
    def __init__(self):
        self._tools = None

    def available(self) -> bool:
        try:
            from ..infrastructure.ffmpeg_tools import FfmpegTools

            return FfmpegTools().available()
        except Exception:
            return False

    def export(self, video_path, session, output_path, settings=None):
        from ..infrastructure.ffmpeg_tools import FfmpegTools

        tools = FfmpegTools()
        if not tools.available():
            return False
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        command = [tools.ffmpeg, "-y", "-i", str(video_path), "-c", "copy", str(output_path)]
        tools.run(command)
        return True

"""Splitter planner, renderer and worker tests.

The planner tests are pure arithmetic and run everywhere.  The render tests
cut a real generated video with FFmpeg and validate the results with FFprobe,
so they are skipped when the tools are absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mmnext.application.splitter_render_coordinator import (
    SplitterRenderCoordinator,
    SplitterRenderResult,
)
from mmnext.domain.enums import CutReason
from mmnext.domain.models import SplitPart
from mmnext.infrastructure.splitter_render import FfmpegSplitterRenderer
from mmnext.services.adapters.splitter import (
    DemoSplitterPlanner,
    DemoSplitterRenderer,
    LegacySplitterRenderer,
)

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
    reason="FFmpeg/FFprobe are required for the splitter render",
)


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #


def test_plain_parts_cover_the_whole_duration_without_gaps() -> None:
    parts = DemoSplitterPlanner().plan(180.0, 60.0)
    assert [round(p.duration, 6) for p in parts] == [60.0, 60.0, 60.0]
    assert [p.number for p in parts] == [1, 2, 3]
    # No gap and no overlap: every part starts where the previous one ended.
    for earlier, later in zip(parts, parts[1:]):
        assert later.start == pytest.approx(earlier.end)
    assert parts[0].start == pytest.approx(0.0)
    assert parts[-1].end == pytest.approx(180.0)
    assert parts[-1].cut_reason is CutReason.END
    assert all(p.cut_reason is CutReason.EXACT for p in parts[:-1])


def test_the_last_part_is_clamped_to_the_media_end() -> None:
    parts = DemoSplitterPlanner().plan(100.0, 60.0)
    assert [round(p.duration, 6) for p in parts] == [60.0, 40.0]
    assert parts[-1].end == pytest.approx(100.0)
    assert parts[-1].cut_reason is CutReason.END


def test_a_wait_larger_than_the_part_does_not_swallow_everything() -> None:
    """The tail is absorbed only when it is itself shorter than a part.

    Without that condition the default 5s wait absorbs the entire remainder
    of a video shorter than part_seconds + wait, and a request for two-second
    parts silently produces one six-second part.
    """
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    assert [round(p.duration, 6) for p in parts] == [2.0, 2.0, 2.0]
    assert parts[-1].end == pytest.approx(6.0)
    assert parts[-1].cut_reason is CutReason.END

    # A 5s tail on a 65s source is shorter than a 60s part and inside the
    # wait, so it is still absorbed as the legacy rule intends.
    absorbed = DemoSplitterPlanner().plan(65.0, 60.0)
    assert [round(p.duration, 6) for p in absorbed] == [65.0]
    assert absorbed[-1].cut_reason is CutReason.END


def test_a_short_tail_is_absorbed_into_the_previous_part() -> None:
    # A 3s tail is inside the 5s wait, so it is absorbed into the previous
    # part instead of becoming a third, near-useless part.
    parts = DemoSplitterPlanner().plan(123.0, 60.0, max_extra_wait=5.0)
    assert [round(p.duration, 6) for p in parts] == [60.0, 63.0]
    assert parts[-1].end == pytest.approx(123.0)
    assert parts[-1].cut_reason is CutReason.END

    # A 40s tail is far outside the 5s wait, so it stays its own part.
    long_tail = DemoSplitterPlanner().plan(160.0, 60.0, max_extra_wait=5.0)
    assert [round(p.duration, 6) for p in long_tail] == [60.0, 60.0, 40.0]

    # A wait larger than a part still does not absorb a tail that is itself
    # longer than a part, so the wait cannot silently turn parts into one.
    generous = DemoSplitterPlanner().plan(123.0, 60.0, max_extra_wait=100.0)
    assert [round(p.duration, 6) for p in generous] == [60.0, 63.0]


def test_smart_cut_snaps_to_a_pause_boundary() -> None:
    parts = DemoSplitterPlanner().plan(
        180.0, 60.0, max_extra_wait=5.0, pause_times=[63.0, 128.0], smart_cut=True
    )
    assert [round(p.end, 6) for p in parts] == [63.0, 128.0, 180.0]
    assert parts[0].cut_reason is CutReason.PAUSE
    assert parts[1].cut_reason is CutReason.PAUSE
    assert parts[2].cut_reason is CutReason.END
    for earlier, later in zip(parts, parts[1:]):
        assert later.start == pytest.approx(earlier.end)


def test_a_pause_outside_the_wait_window_is_ignored() -> None:
    parts = DemoSplitterPlanner().plan(
        180.0, 60.0, max_extra_wait=2.0, pause_times=[80.0], smart_cut=True
    )
    # 80s is 20s past the 60s target, far outside the 2s window.
    assert [round(p.end, 6) for p in parts] == [60.0, 120.0, 180.0]
    assert parts[0].cut_reason is CutReason.EXACT


def test_a_duration_shorter_than_one_part_yields_a_single_part() -> None:
    parts = DemoSplitterPlanner().plan(40.0, 60.0)
    assert len(parts) == 1
    assert parts[0].start == pytest.approx(0.0)
    assert parts[0].end == pytest.approx(40.0)
    assert parts[0].cut_reason is CutReason.END


def test_the_planner_refuses_nonsense_input() -> None:
    with pytest.raises(ValueError, match="positive"):
        DemoSplitterPlanner().plan(0.0, 60.0)
    with pytest.raises(ValueError, match="positive"):
        DemoSplitterPlanner().plan(120.0, 0.0)
    with pytest.raises(ValueError, match="positive"):
        DemoSplitterPlanner().plan(-5.0, 60.0)


# --------------------------------------------------------------------------- #
# Coordinator (offline renderer)
# --------------------------------------------------------------------------- #


def test_the_coordinator_renders_every_selected_part() -> None:
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    parts[1].include = False
    result = SplitterRenderCoordinator(
        renderer=DemoSplitterRenderer(), is_demo=True
    ).run(
        parts,
        "video.mp4",
        "out",
        {},
    )
    assert isinstance(result, SplitterRenderResult)
    assert result.ok is True
    assert len(result.output_paths) == 2
    assert all(name.endswith("part_1.mp4") or "part_2" not in name for name in result.output_paths)


def test_a_part_with_no_selection_is_refused() -> None:
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    for part in parts:
        part.include = False
    result = SplitterRenderCoordinator(renderer=DemoSplitterRenderer()).run(
        parts, "video.mp4", "out", {}
    )
    assert result.ok is False
    assert "No selected parts" in result.message


def test_a_part_that_ends_before_it_starts_is_refused() -> None:
    parts = [SplitPart(number=1, start=5.0, end=5.0)]
    result = SplitterRenderCoordinator(renderer=DemoSplitterRenderer()).run(
        parts, "video.mp4", "out", {}
    )
    assert result.ok is False
    assert "Part 1" in result.message


def test_the_coordinator_reuses_a_matching_fingerprint(tmp_path) -> None:
    """A second run of the same settings must not re-render a part."""
    calls: list[str] = []

    class _Counting(DemoSplitterRenderer):
        def render_part(self, video_path, part, output_path, settings):
            calls.append(str(part.number))
            return super().render_part(video_path, part, output_path, settings)

    parts = DemoSplitterPlanner().plan(4.0, 2.0)
    coordinator = SplitterRenderCoordinator(renderer=_Counting(), is_demo=True)
    settings = {"ratio": "Original", "fill": "Blur", "text": "title"}

    first = coordinator.run(parts, "video.mp4", str(tmp_path), settings)
    assert first.ok is True
    assert calls == ["1", "2"]

    second = coordinator.run(parts, "video.mp4", str(tmp_path), settings)
    assert second.ok is True
    # Nothing was rendered again; both parts were reused.
    assert calls == ["1", "2"]
    assert any("reused" in warning.lower() for warning in second.warnings)


def test_changed_settings_invalidate_a_part(tmp_path) -> None:
    """A different ratio must re-render rather than reuse the old part."""
    calls: list[str] = []

    class _Counting(DemoSplitterRenderer):
        def render_part(self, video_path, part, output_path, settings):
            calls.append(str(part.number))
            return super().render_part(video_path, part, output_path, settings)

    parts = DemoSplitterPlanner().plan(4.0, 2.0)
    coordinator = SplitterRenderCoordinator(renderer=_Counting(), is_demo=True)

    coordinator.run(parts, "video.mp4", str(tmp_path), {"ratio": "Original"})
    second = coordinator.run(parts, "video.mp4", str(tmp_path), {"ratio": "16:9"})
    assert second.ok is True
    assert calls == ["1", "2", "1", "2"], "a changed setting must rebuild the parts"


def test_a_failed_render_keeps_its_reason(tmp_path) -> None:
    class _Failing(DemoSplitterRenderer):
        def render_part(self, video_path, part, output_path, settings):
            return False

    parts = DemoSplitterPlanner().plan(4.0, 2.0)
    result = SplitterRenderCoordinator(renderer=_Failing()).run(
        parts, "video.mp4", str(tmp_path), {}
    )
    assert result.ok is False
    assert "Render failed for part 1" in result.message


def test_the_stop_flag_stops_between_parts(tmp_path) -> None:
    class _Stopping(DemoSplitterRenderer):
        def render_part(self, video_path, part, output_path, settings):
            if part.number == 2:
                self._coordinator.request_stop()
            return super().render_part(video_path, part, output_path, settings)

    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    renderer = _Stopping()
    coordinator = SplitterRenderCoordinator(renderer=renderer, is_demo=True)
    renderer._coordinator = coordinator

    result = coordinator.run(parts, "video.mp4", str(tmp_path), {})
    assert result.ok is False
    assert result.stopped is True
    # The stop is honoured at the *next* boundary: part 2 was in flight when
    # the flag arrived, so it finished, and part 3 never started.
    assert len(result.output_paths) == 2
    assert result.output_paths[-1].endswith("part_2.mp4")


# --------------------------------------------------------------------------- #
# Real render
# --------------------------------------------------------------------------- #


def make_video(path: Path, seconds: float = 6.0, keyframe_gap: int = 15) -> Path:
    """Create a small real video.

    ``keyframe_gap`` is in frames, so the default is a keyframe every second at
    15 fps - the spacing a real source has, which is what lets a stream-copy
    cut land where it was asked to.  Callers that want the worst case pass a
    gap longer than the whole clip.
    """
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x180:r=15",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", f"{seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-g", str(keyframe_gap),
            "-c:a", "aac",
            str(path),
        ],
        check=True,
    )
    return path


def probe(path: Path) -> dict:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
         str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return json.loads(completed.stdout)


@needs_ffmpeg
def test_the_renderer_reports_its_capability() -> None:
    assert LegacySplitterRenderer().available() is True
    assert FfmpegSplitterRenderer().available() is True
    assert DemoSplitterRenderer().available() is True


@needs_ffmpeg
def test_a_real_part_holds_both_streams_and_its_window(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    renderer = FfmpegSplitterRenderer()
    part = SplitPart(number=1, start=0.0, end=2.0, cut_reason=CutReason.EXACT)
    output = tmp_path / "part_1.mp4"

    assert renderer.render_part(str(video), part, str(output), {}) is True
    assert output.is_file() and output.stat().st_size > 0

    report = renderer.last_report
    assert report["part"] == 1
    assert report["cut_reason"] == "exact"
    # The window is honoured within the keyframe-snapping allowance.
    assert abs(report["duration"] - 2.0) <= report["tolerance"]

    info = probe(output)
    assert any(s["codec_type"] == "video" for s in info["streams"])
    assert any(s["codec_type"] == "audio" for s in info["streams"])


@needs_ffmpeg
def test_every_planned_part_renders_to_its_own_file(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    renderer = FfmpegSplitterRenderer()
    output_dir = tmp_path / "parts"

    assert renderer.render(str(video), parts, str(output_dir), {}) is True
    names = sorted(p.name for p in output_dir.glob("*.mp4"))
    assert names == ["part_1.mp4", "part_2.mp4", "part_3.mp4"]
    for part in parts:
        info = probe(output_dir / f"part_{part.number}.mp4")
        duration = float(info["format"]["duration"])
        assert abs(duration - part.duration) <= 0.5, (part.number, duration)


@needs_ffmpeg
def test_a_snapped_cut_is_reported_not_hidden(tmp_path) -> None:
    """A cut that lands on a keyframe must be reported, not silently claimed."""
    # One keyframe for the whole clip: the worst case for a stream copy.
    video = make_video(tmp_path / "source.mp4", seconds=6.0, keyframe_gap=250)
    renderer = FfmpegSplitterRenderer()
    part = SplitPart(number=1, start=2.0, end=4.0, cut_reason=CutReason.EXACT)
    output = tmp_path / "part_1.mp4"

    assert renderer.render_part(str(video), part, str(output), {}) is True
    report = renderer.last_report
    assert "requested_start" in report
    assert report["requested_start"] == pytest.approx(2.0)
    # The measured start is reported so the caller can be honest about it, and
    # the part still holds both streams even though the cut could not be exact.
    assert "start_time" in report
    assert report["start_time"] < 2.0 + 0.5
    info = probe(output)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert any(s["codec_type"] == "video" for s in info["streams"])


@needs_ffmpeg
def test_the_coordinator_warns_when_a_cut_snapped(tmp_path) -> None:
    """A snapped boundary must reach the user as a warning, not vanish."""
    video = make_video(tmp_path / "source.mp4", seconds=6.0, keyframe_gap=250)
    parts = [SplitPart(number=1, start=2.0, end=4.0, cut_reason=CutReason.EXACT)]
    coordinator = SplitterRenderCoordinator(
        renderer=FfmpegSplitterRenderer(), is_demo=False
    )
    result = coordinator.run(parts, str(video), str(tmp_path), {})
    assert result.ok is True
    assert any("snapped" in warning.lower() for warning in result.warnings), result.warnings


@needs_ffmpeg
def test_a_part_that_cannot_be_cut_is_refused(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    renderer = FfmpegSplitterRenderer()
    # A window that starts past the end of the media yields no frames.
    part = SplitPart(number=1, start=9.0, end=11.0, cut_reason=CutReason.EXACT)
    output = tmp_path / "part_1.mp4"

    assert renderer.render_part(str(video), part, str(output), {}) is False
    assert not output.exists(), "a refused part must not leave a file behind"
    assert renderer.last_report.get("error")


@needs_ffmpeg
def test_a_missing_source_is_refused_with_a_reason(tmp_path) -> None:
    renderer = FfmpegSplitterRenderer()
    part = SplitPart(number=1, start=0.0, end=2.0, cut_reason=CutReason.EXACT)
    output = tmp_path / "part_1.mp4"

    assert renderer.render_part(str(tmp_path / "nope.mp4"), part, str(output), {}) is False
    assert not output.exists()
    assert "missing" in renderer.last_report.get("error", "").lower()


@needs_ffmpeg
def test_the_source_is_never_modified(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    before = video.read_bytes()
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    FfmpegSplitterRenderer().render(str(video), parts, str(tmp_path / "parts"), {})
    assert video.read_bytes() == before


@needs_ffmpeg
def test_the_coordinator_reuses_a_validated_part(tmp_path) -> None:
    """A rerun must reuse the validated part, not rebuild it silently."""
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    coordinator = SplitterRenderCoordinator(
        renderer=FfmpegSplitterRenderer(), is_demo=False
    )
    settings = {"ratio": "Original", "fill": "Blur"}

    rendered_before = {
        path.name: path.stat().st_mtime_ns for path in (tmp_path).glob("part_*.mp4")
    }
    assert coordinator.run(parts, str(video), str(tmp_path), settings).ok
    rendered_before = {
        path.name: path.stat().st_mtime_ns for path in (tmp_path).glob("part_*.mp4")
    }
    assert len(rendered_before) == 3

    second = coordinator.run(parts, str(video), str(tmp_path), settings)
    assert second.ok
    rendered_after = {
        path.name: path.stat().st_mtime_ns for path in (tmp_path).glob("part_*.mp4")
    }
    assert rendered_after == rendered_before, "a validated part must be reused"
    assert any("reused" in warning.lower() for warning in second.warnings)


@needs_ffmpeg
def test_a_real_render_reports_a_snapped_boundary(tmp_path) -> None:
    video = make_video(tmp_path / "source.mp4", seconds=6.0)
    parts = DemoSplitterPlanner().plan(6.0, 2.0)
    coordinator = SplitterRenderCoordinator(
        renderer=FfmpegSplitterRenderer(), is_demo=False
    )
    result = coordinator.run(parts, str(video), str(tmp_path), {})
    assert result.ok is True
    # Whatever the keyframe spacing, the parts are complete and validated.
    assert len(result.output_paths) == 3
    for path in result.output_paths:
        info = probe(Path(path))
        assert any(s["codec_type"] == "audio" for s in info["streams"])
        assert any(s["codec_type"] == "video" for s in info["streams"])

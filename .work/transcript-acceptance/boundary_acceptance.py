"""Offline real-model acceptance: strict rejection + full source + offscreen UI."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ['HF_HOME'] = str(WORK / 'hf-cache')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['TMP'] = os.environ['TEMP'] = str(WORK / 'tmp')
os.environ['PATH'] = str(WORK / 'win32') + os.pathsep + os.environ['PATH']
from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter
from mmnext.domain.enums import AppMode
from mmnext.domain.events import ProgressEvent

MODEL = str(WORK / 'models/tiny.en')
SOURCE = WORK / 'inputs/harvard.wav'
VIDEO = WORK / 'inputs/harvard-full.mp4'
RESULT = WORK / 'boundary-acceptance-result.json'
result = {'status': 'RUNNING', 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'model': MODEL, 'device': 'cpu/int8', 'timing_tolerance_s': 0,
          'source_url': 'https://raw.githubusercontent.com/realpython/python-speech-recognition/master/audio_files/harvard.wav'}

def persist():
    RESULT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')

def adapter(video, name):
    return WhisperTranscriptAdapter(str(WORK / name), str(video), whisper_model=MODEL, device='cpu', is_demo=False)

def strict_rows(rows, duration):
    assert rows and all(r.text.strip() for r in rows)
    assert len({r.row_id for r in rows}) == len(rows)
    assert all(0 <= r.start < r.end <= duration for r in rows), [(r.start, r.end) for r in rows]
    assert all(a.start <= b.start for a, b in zip(rows, rows[1:]))

try:
    # Same clipped fixture as the previous failure; new jobs keep old evidence untouched.
    clipped = WORK / 'inputs/osr-harvard-12s.mp4'
    bad = adapter(clipped, 'boundary-rejection-jobs')
    events = []
    try:
        bad.transcribe(str(clipped), auto_detect=True, emit=events.append)
    except RuntimeError as exc:
        assert 'authoritative video duration' in str(exc), str(exc)
        ckpt = bad.repo.load_checkpoint(bad.job_id, str(clipped), bad.mode)
        assert ckpt['state'] == 'failed' and not bad.artifact_path.exists()
        assert all(e.percent < 100 for e in events if isinstance(e, ProgressEvent))
        result['clipped_rejection'] = {'status': 'PASS', 'error': str(exc), 'checkpoint': ckpt,
                                       'max_progress': max(e.percent for e in events if isinstance(e, ProgressEvent))}
    else:
        raise AssertionError('Known clipped source unexpectedly passed; inspect changed model behavior')
    persist()

    with wave.open(str(SOURCE), 'rb') as wav:
        source_duration = wav.getnframes() / wav.getframerate()
    # Keep the complete speech recording: no arbitrary 12s cut, no stretched audio,
    # no invented trailing silence. Video length is the natural frame-rounded source length.
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'color=c=black:s=320x180:r=15', '-i', str(SOURCE),
                    '-t', str(source_duration), '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '16000', '-ac', '1', str(VIDEO)], check=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format',
                                               '-show_streams', '-of', 'json', str(VIDEO)], text=True))
    duration = float(probe['format']['duration'])
    assert {s['codec_type'] for s in probe['streams']} == {'video', 'audio'}
    good = adapter(VIDEO, 'boundary-full-jobs')
    events = []
    started = time.perf_counter()
    rows, language = good.transcribe(str(VIDEO), auto_detect=True, emit=events.append)
    elapsed = time.perf_counter() - started
    strict_rows(rows, duration)
    assert language == 'en'
    assert 'stale' in ' '.join(r.text for r in rows).lower()
    payload = json.loads(good.artifact_path.read_text(encoding='utf-8'))
    expected = [{'row_id': r.row_id, 'start': r.start, 'duration': r.duration, 'text': r.text} for r in rows]
    assert payload['rows'] == expected and payload['duration_s'] == duration and not payload['is_demo']
    ckpt = good.repo.load_checkpoint(good.job_id, str(VIDEO), good.mode)
    assert ckpt['state'] == 'complete' and ckpt['output_path'] == str(good.artifact_path)
    assert not ckpt['resume_supported'] and ckpt['completed_units'] == ckpt['total_units'] == len(rows)
    assert events[-1].percent == 100
    with wave.open(str(good.work_dir / 'audio_tmp' / (VIDEO.stem + '.wav')), 'rb') as wav:
        audio = {'channels': wav.getnchannels(), 'rate': wav.getframerate(),
                 'sample_width': wav.getsampwidth(), 'duration_s': wav.getnframes() / wav.getframerate()}
    assert (audio['channels'], audio['rate'], audio['sample_width']) == (1, 16000, 2)
    assert 0 < audio['duration_s'] <= duration + 0.1
    result['full_source'] = {'status': 'PASS', 'fixture': str(VIDEO), 'original_audio_duration_s': source_duration,
                             'duration_s': duration, 'elapsed_s': round(elapsed, 3), 'language': language,
                             'rows': expected, 'audio': audio, 'artifact': str(good.artifact_path), 'checkpoint': ckpt}
    persist()

    # Actual workspace button -> QThread -> real FFmpeg/Whisper -> live models.
    # Only replace file picker selection and model configuration, not inference or results.
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from mmnext.bootstrap import create_application
    from mmnext.ui.main_window import MainWindow
    from mmnext.ui.navigation.nav_rail import NavTarget
    app = create_application([])
    window = MainWindow()
    window.context._jobs_dir = str(WORK / 'boundary-ui-jobs')
    window.show()
    window.navigate_to(NavTarget.WORKSPACE)
    window.context.set_mode(AppMode.NARRATOR)
    providers = []
    def configured(*args, **kwargs):
        kwargs['whisper_model'] = MODEL
        provider = WhisperTranscriptAdapter(*args, **kwargs)
        providers.append(provider)
        return provider
    ui_events = []
    window.context.transcriptProgress.connect(ui_events.append)
    try:
        with patch('mmnext.infrastructure.transcript_adapter.WhisperTranscriptAdapter', side_effect=configured), \
             patch('mmnext.ui.workspace.workspace_screen.QFileDialog.getOpenFileName', return_value=(str(VIDEO), '')):
            QTest.mouseClick(window._workspace.transcribe_button, Qt.MouseButton.LeftButton)
            assert window.context._transcript_thread is not None
            deadline = time.monotonic() + 120
            while window.context._transcript_thread is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
            assert window.context._transcript_thread is None, 'UI worker timed out'
        assert window.context.transcript_state == 'complete', window.context.transcript_message
        assert window.demo_badge.text() == 'REAL'
        session = window.context.session
        strict_rows(session.transcript, duration)
        assert [(r.row_id, r.start, r.duration, r.text) for r in session.transcript] == [
            (r['row_id'], r['start'], r['duration'], r['text']) for r in expected]
        assert window._workspace.transcript_model.rowCount() == len(expected)
        assert window._workspace.transcript_progress.value() == 100
        assert not session.narration_segments
        assert [(r.row_id, r.start, r.duration, r.original) for r in session.exact_dubbing_rows] == [
            (r['row_id'], r['start'], r['duration'], r['text']) for r in expected]
        window.context.set_mode(AppMode.EXACT_DUBBING)
        assert not window.context.validate().ok
        assert all(not r.burmese for r in session.exact_dubbing_rows)
        result['real_ui'] = {'status': 'PASS', 'row_count': len(expected), 'badge': window.demo_badge.text(),
                              'progress': window._workspace.transcript_progress.value(),
                              'artifact': str(providers[0].artifact_path), 'exact_untranslated_blocked': True,
                              'mode': 'offscreen; real worker and inference; cached model injected via constructor'}
    finally:
        if window.context._transcript_thread is not None:
            window.context.stop_transcript()
            window.context._transcript_thread.wait(120000)
            app.processEvents()
        window.context.project.mark_exact_rows_clean()
        window.context.project.mark_narration_clean()
        window._worker.shutdown(wait_ms=1000)
        window.close()
        app.processEvents()
    result['status'] = 'PASS'
except Exception as exc:
    result['status'] = 'FAIL'
    result['error'] = repr(exc)
    persist()
    raise
persist()
print(json.dumps(result, indent=2, ensure_ascii=False))

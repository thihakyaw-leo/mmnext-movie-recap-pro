from pathlib import Path
import os,sys,json,subprocess,time,wave,hashlib
ROOT=Path(r'J:\mmnext-movie-recap-pro');sys.path.insert(0,str(ROOT))
WORK=ROOT/'.work/transcript-acceptance'
os.environ['HF_HOME']=str(WORK/'hf-cache')
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TMP']=os.environ['TEMP']=str(WORK/'tmp')
os.environ['PATH']=str(WORK/'win32')+os.pathsep+os.environ['PATH']
from mmnext.infrastructure.transcript_adapter import WhisperTranscriptAdapter
from mmnext.domain.enums import AppMode,TaskState
src=WORK/'inputs/harvard.wav'
video=WORK/'inputs/osr-harvard-12s.mp4'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=15','-i',str(src),'-t','12','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-ar','16000','-ac','1',str(video)],check=True)
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(video)],text=True))
assert {s['codec_type'] for s in probe['streams']}=={'video','audio'}
assert abs(float(probe['format']['duration'])-12)<0.2
adapter=WhisperTranscriptAdapter(str(WORK/'acceptance-jobs'),str(video),mode=AppMode.NARRATOR,whisper_model=str(WORK/'models/tiny.en'),device='cpu',is_demo=False)
events=[]; started=time.perf_counter()
rows,language=adapter.transcribe(str(video),auto_detect=True,emit=events.append)
elapsed=time.perf_counter()-started
assert language=='en',language
assert rows and all(r.text.strip() for r in rows)
assert len({r.row_id for r in rows})==len(rows)
timing_valid=all(0<=r.start<r.end<=12.25 for r in rows)
assert all(a.start<=b.start for a,b in zip(rows,rows[1:]))
text=' '.join(r.text for r in rows)
assert 'stale' in text.lower() and 'beer' in text.lower(),text
artifact=json.loads(adapter.artifact_path.read_text(encoding='utf-8'))
assert artifact['is_demo'] is False and len(artifact['rows'])==len(rows)
ckpt=adapter.repo.load_checkpoint(adapter.job_id,str(video),AppMode.NARRATOR)
assert ckpt['state']==TaskState.COMPLETE.value and ckpt['output_path']==str(adapter.artifact_path)
assert ckpt['resume_supported'] is False
wav=adapter.work_dir/'audio_tmp'/f'{video.stem}.wav'
with wave.open(str(wav),'rb') as f:
 audio={'channels':f.getnchannels(),'rate':f.getframerate(),'sample_width':f.getsampwidth(),'duration':f.getnframes()/f.getframerate()}
 assert (audio['channels'],audio['rate'],audio['sample_width'])==(1,16000,2)
assert events[-1].percent==100
result={'status':'PASS' if timing_valid else 'FAIL', 'timing_within_video':timing_valid, 'timing_tolerance_s':0.25,'source':'Real Python speech recognition tutorial (MIT repository)','source_url':'https://raw.githubusercontent.com/realpython/python-speech-recognition/master/audio_files/harvard.wav','source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'fixture':str(video),'duration_s':float(probe['format']['duration']),'model':'Systran/faster-whisper-tiny.en (local)','device':'cpu/int8','elapsed_s':round(elapsed,3),'language':language,'rows':artifact['rows'],'audio':audio,'artifact':str(adapter.artifact_path),'checkpoint':ckpt,'last_progress':events[-1].percent,'ui_acceptance':'not exercised by this runner'}
(WORK/'acceptance-result.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=False))



if not timing_valid: sys.exit('FAIL: transcript segment exceeds authoritative video duration')


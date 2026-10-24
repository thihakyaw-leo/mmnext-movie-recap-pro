import os,sys,pathlib,concurrent.futures,urllib.request,json,hashlib
ROOT=pathlib.Path(r'J:\mmnext-movie-recap-pro')
WORK=ROOT/'.work/transcript-acceptance'
os.environ['HF_HOME']=str(WORK/'hf-cache')
os.environ['HF_HUB_DISABLE_XET']='1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'
os.environ['TMP']=os.environ['TEMP']=str(WORK/'tmp')
(WORK/'tmp').mkdir(exist_ok=True)
def tools():
 import static_ffmpeg,shutil,subprocess
 static_ffmpeg.add_paths(download_dir=str(WORK/'tools'))
 for name in ('ffmpeg','ffprobe'):
  p=shutil.which(name); print(name,p,flush=True)
  print(subprocess.check_output([p,'-version'],text=True).splitlines()[0],flush=True)
 return 'tools ready'
def model():
 from huggingface_hub import snapshot_download
 p=snapshot_download('Systran/faster-whisper-tiny.en',local_dir=str(WORK/'models/tiny.en'),allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'],max_workers=2)
 return 'model ready: '+p
def speech():
 url='https://www.voiptroubleshooter.com/open_speech/american/OSR_us_000_0010_8k.wav'
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'*/*','Referer':'https://www.voiptroubleshooter.com/open_speech/american.html'})
 with urllib.request.urlopen(req,timeout=60) as r: data=r.read()
 assert data[:4]==b'RIFF',data[:100]
 p=WORK/'inputs/OSR_us_000_0010_8k.wav';p.write_bytes(data)
 return 'speech ready: '+str(len(data))+' bytes sha256 '+hashlib.sha256(data).hexdigest()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 futures={pool.submit(f):f.__name__ for f in (tools,model,speech)}
 results={}
 for f in concurrent.futures.as_completed(futures):
  name=futures[f]
  try: results[name]={'ok':True,'detail':f.result()}
  except Exception as e: results[name]={'ok':False,'detail':repr(e)}
  print(name,results[name],flush=True)
(WORK/'prepare-result.json').write_text(json.dumps(results,indent=2))
if not all(x['ok'] for x in results.values()):sys.exit(1)

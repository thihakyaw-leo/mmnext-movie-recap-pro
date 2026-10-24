# MMNext Transcript — Timestamp အမှား ပြင်ဆင်ပြီးရလဒ်

Video ကြာချိန်ထက် ကျော်နေသော Whisper segment ကို ယခု **FAILED** အဖြစ် ရပ်တန့်စေသည်။ Timestamp ကို ဖြတ်ညှိခြင်း၊ စာသားဖျောက်ခြင်း၊ segment ပေါင်းခြင်း မလုပ်ပါ။ Valid transcript သိမ်းပြီး checkpoint အောင်မှသာ COMPLETE/100% ရသည်။

## တကယ်စမ်းပြီး အောင်ထားသည်

မူရင်း speech recording အပြည့် **18.356 စက္ကန့်** ကို video ထဲထည့်ပြီး real faster-whisper tiny.en ကို CPU/int8 ဖြင့် ပြေးခဲ့သည်။ FFprobe က container duration **18.357 စက္ကန့်** ဟုတိုင်းသည်။ English segment **၆ ခု** ထွက်ပြီး နောက်ဆုံးအဆုံးချိန် **17.600 စက္ကန့်** ဖြစ်သည်။ အပိုခွင့်ပြုချိန် **0 စက္ကန့်** ဖြင့် အားလုံး အချိန်ဘောင်အတွင်းဝင်သည်။ Inference **2.151 စက္ကန့်** ကြာသည်။

Extracted audio သည် mono၊ 16000 Hz၊ PCM16၊ 18.357 စက္ကန့်ဖြစ်သည်။ သိမ်းထားသော JSON နှင့် returned rows တူညီမှု၊ stable IDs၊ text/timing၊ detected language၊ COMPLETE checkpoint နှင့် 100% ကို စစ်ပြီးအောင်သည်။ [စက်ဖတ်နိုင်သော acceptance result](../.work/transcript-acceptance/boundary-acceptance-result.json) တွင် row အားလုံးနှင့် checkpoint ပါသည်။

REAL UI ခလုတ်မှ worker thread ကိုစ၍ FFmpeg/Whisper တကယ်ပြေးကာ live table ထဲ segment ၆ ခု ပေါ်လာခြင်းကို offscreen စစ်ပြီးအောင်သည်။ REAL badge နှင့် 100% မှန်သည်။ Exact Dubbing source rows တွင် ID/text/timing မပြောင်းဘဲ Burmese translation ဗလာဖြစ်သဖြင့် validation က ဆက်လုပ်ခွင့်မပေးပါ။ File picker နှင့် cached model configuration ကို QA runner မှ သတ်မှတ်ထားပြီး inference/result ကို မအစားထိုးထားပါ။

Speech fixture သည် [Real Python repository](https://github.com/realpython/python-speech-recognition) မှ [harvard.wav](https://raw.githubusercontent.com/realpython/python-speech-recognition/master/audio_files/harvard.wav) ဖြစ်သည်။ MIT license နှင့် attribution ကို project-local inputs ထဲ ထိန်းထားသည်။ Personal media မသုံး၊ inference အတွက် network မသုံး၊ မူရင်းအသံကို မပြောင်းပါ။ Video wrapper သည် acceptance fixture အတွက်သာဖြစ်ပြီး final production rendering feature မဟုတ်ပါ။

## ယခင် ၁၂ စက္ကန့် failure ကို ယခု မှန်ကန်စွာ ပိတ်နိုင်သည်

ယခင် clipped video ကို model အတူတူဖြင့် ပြန်စမ်းရာ s3 သည် **10–13 စက္ကန့်** ဟုထွက်နေဆဲဖြစ်သည်။ Video က 12 စက္ကန့်သာရှိသဖြင့် ယခု **FAILED** ဖြစ်ပြီး final transcript အသစ် မရှိ၊ 100% မရပါ။ Maximum progress **83.3333%** ဖြစ်ပြီး မှန်ကန်သော ရှေ့ segment ၃ ခုကိုသာ partial checkpoint ထဲ ထိန်းထားသည်။

ဤစမ်းသပ်မှု PASS ဆိုသည်မှာ မမှန်သော output ကို တားနိုင်ခြင်းဖြစ်သည်။ ၁၂ စက္ကန့် clip ၏ transcription အောင်မြင်သွားခြင်း မဟုတ်ပါ။ ယခင် FAIL result နှင့် invalid historical artifact ကို evidence အဖြစ် မဖျက်ထားသဖြင့် ၎င်းတို့ကို valid transcript အဖြစ် မသုံးရပါ။

## ဘာတွေပြင်ထားသလဲ

`mmnext/infrastructure/transcript_adapter.py` တွင် raw segment ကို snapshot မသိမ်းမီ bounds စစ်ပြီး atomic final writer မှာလည်း ထပ်စစ်သည်။ NaN/Inf၊ negative၊ zero-length နှင့် reversed timing များလည်း ပယ်ချသည်။ Failure message တွင် source၊ segment ID၊ မူရင်း timing နှင့် restart လမ်းညွှန်ပါသည်။ Demo path ကို သီးခြားထားသည်။ ယခင် valid artifact ကို invalid replacement ဖြင့် မဖုံးရေးပါ။

`tests/test_transcript_regressions.py` တွင် overflow၊ တစ် microsecond ကျော်မှု၊ exact-end success၊ final-writer protection၊ alternate provider rows နှင့် malformed timing tests ထည့်ထားသည်။ Optional real smoke ကိုလည်း strict bounds စစ်စေသည်။ `tests/test_live_transcript_workspace.py` တွင် invalid timing ကြောင့် UI FAILED ဖြစ်ပြီး source rows မချိတ်ဆက်၊ 100% မရကြောင်း စစ်ထားသည်။

`tests/test_phase2_worker_integration.py` တွင် temp directory သည် checkout အပြင်မှာရှိရမည်ဟူသော မှားယွင်းယူဆချက်ကို ဖယ်ထားသည်။ သီးခြား cwd နှင့် path-aware checks ဖြင့် configured jobs root ကို တကယ်စစ်သည်။ Production repository logic မပြောင်းပါ။

## စစ်ဆေးမှုရလဒ်

| စစ်ဆေးချက် | ရလဒ် |
|---|---|
| Regression မပြင်မီ အမှားဖမ်းမိမှု | 5 failed၊ 1 passed |
| နောက်ဆုံး focused suite၊ real opt-in ပါဝင် | **66 passed — 22.18s** |
| Full suite၊ real opt-in ပါဝင်၊ project အတွင်း temp | **285 passed — 73.39s** |
| Python AST syntax | **94 files PASS** |
| Production module imports | **6 modules PASS** |
| Offscreen UI shell smoke | **screen 7 ခု၊ clean close၊ exit 0** |
| Real clipped-source rejection | **PASS — FAILED checkpoint၊ final transcript အသစ်မရှိ** |
| Real full-source + live UI acceptance | **PASS — strict tolerance 0** |

[Full-suite log](../.work/transcript-acceptance/boundary-full-suite.log)၊ [focused log](../.work/transcript-acceptance/boundary-focused-final.log)၊ [syntax/import log](../.work/transcript-acceptance/boundary-syntax-import.log) နှင့် [shell log](../.work/transcript-acceptance/boundary-shell.log) တို့ကို project အတွင်း သိမ်းထားသည်။ Shell smoke သည် default PATH ဖြင့် tool မတွေ့ကြောင်း မှန်ကန်စွာပြသည်။ Real acceptance runner ကသာ project-local tool PATH ကို process အတွင်း ထည့်ပေးသည်။ System PATH မပြောင်းပါ။

ပြန်စမ်းရန် project root မှ အောက်ပါ command ကို အသုံးပြုနိုင်သည်။ Runner သည် fixture video နှင့် သီးသန့် acceptance jobs ကို ပြန်ရေးမည်။

```powershell
.\.venv\Scripts\python.exe .work\transcript-acceptance\boundary_acceptance.py
```

ယခင် `acceptance.py` သည် historical ၁၂ စက္ကန့် failure runner ဖြစ်နေဆဲဖြစ်သဖြင့် acceptance အသစ်အတွက် မသုံးရပါ။

## နောက်ဘာဆက်လုပ်မလဲ

ဤ timestamp-boundary ပြုပြင်မှုနှင့် သတ်မှတ်ထားသော real-media/UI acceptance ကို အထောက်အထားဖြင့် အောင်ထားပြီဖြစ်သော်လည်း **production-complete မဟုတ်သေးပါ**။ နောက်အဆင့်မှာ သိမ်းထားသော transcript ကို app ပြန်ဖွင့်ချိန် ပြန်တင်ခြင်း၊ Jobs recovery နှင့် UI မှ local model/tool configuration ကို ချိတ်ဆက်ခြင်း ဖြစ်သင့်သည်။

အရှည်ကြီး video၊ ဘာသာစုံ၊ GPU၊ clean-machine install နှင့် default UI model setup တို့ကို ယခုရလဒ်က မအာမခံပါ။ Stop သည် safe-boundary stop/restart-only ဖြစ်ပြီး mid-Whisper resume မဟုတ်ပါ။ Router review ကို မပြန်စမ်းခဲ့ပါ။ Translation၊ Gemini၊ TTS နှင့် final rendering မထည့်ထားပါ။ `J:\mmnext-movie-recap-pro` တစ်ခုတည်းတွင်သာ အလုပ်လုပ်ထားပြီး legacy project နှစ်ခု မပြောင်းပါ။ Authoritative folder တွင် `.git` မရှိသဖြင့် Git commit/diff အထောက်အထား မရှိပါ။

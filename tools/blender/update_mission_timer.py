"""Replace only the timing panel; retain the existing mission motion and audio."""
from pathlib import Path
import json,subprocess
from PIL import Image,ImageDraw
from compose_tournament_video import txt,clock,CARD,COLORS,MUTED
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/mission'
meta=json.loads((OUT/'metadata_v3.json').read_text());frames=meta['frames']
source=OUT/'mission_driving_v2.mp4';target=OUT/'mission_driving_v3.mp4'
decode=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-i',str(source),'-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE)
encode=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-i',str(source),'-map','0:v:0','-map','1:a:0','-c:v','libx264','-preset','fast','-crf','18','-threads','4','-pix_fmt','yuv420p','-c:a','copy','-shortest','-movflags','+faststart',str(target)],stdin=subprocess.PIPE)
size=1920*1080*3;k=0
while True:
 raw=decode.stdout.read(size)
 if not raw:break
 assert len(raw)==size
 image=Image.frombytes('RGB',(1920,1080),raw);d=ImageDraw.Draw(image)
 rec=frames[min(max(k-96,0),len(frames)-1)]
 state='waiting' if k<96 else rec['timer_state'];value=0 if k<96 else rec['avoidance_timer']
 # Cover the old elapsed clock, preserving the existing rounded card boundary.
 d.rectangle((1450,116,1874,278),fill=CARD)
 txt(d,(1458,122),'EGO VEHICLE',25,COLORS[0],True)
 txt(d,(1458,159),'M3 랩타이머 · 장애물 회피 시간',21,MUTED)
 txt(d,(1458,195),clock(value),42,b=True)
 label={'waiting':'첫 통과 대기','running':'M3 첫 통과 · 측정 중','finished':'M3 재통과 · 측정 종료'}[state]
 txt(d,(1458,253),label,20,(71,229,132) if state=='finished' else MUTED)
 encode.stdin.write(image.tobytes())
 if k in (0,96,672,870):image.save(OUT/f'timer_check_{k}.png')
 k+=1
encode.stdin.close();assert encode.wait()==0;assert decode.wait()==0
assert k==997,k
print('VIDEO_COMPLETE',k,'frames; avoidance time',meta['lap_timer']['avoidance_duration'])

"""Compose parking footage using the established Korean mission video format."""
import json,subprocess,time
from pathlib import Path
from PIL import Image,ImageDraw
from compose_tournament_video import font,txt,BG,CARD,FG,MUTED,COLORS
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/parking_v5';meta=json.loads((OUT/'metadata.json').read_text());BLUE=COLORS[0];GREEN=(71,229,132)
cache={}
def frame(i,intro=False,outro=False):
 r=meta['frames'][i];key=r['render']
 if key not in cache:
  path=OUT/'frames'/f'parking_{key:04d}.png';deadline=time.monotonic()+1200
  while True:
   try:
    with path.open('rb') as f:
     f.seek(-12,2)
     if f.read()!=bytes.fromhex('0000000049454e44ae426082'):raise OSError('Incomplete frame')
    cache.clear();cache[key]=Image.open(path).convert('RGB');break
   except (OSError,SyntaxError):
    if time.monotonic()>deadline:raise
    time.sleep(.5)
 im=Image.new('RGB',(1920,1080),BG);im.paste(cache[key],(0,80));d=ImageDraw.Draw(im)
 txt(d,(32,23),'수직주차 · 평행주차 미션',33,b=True);txt(d,(565,31),'미션 2 주행 예시',23,MUTED)
 d.rounded_rectangle((1110,18,1380,62),radius=12,fill=CARD);txt(d,(1127,29),'주차·조향 실시간' if r['realtime'] else '이동 2배속',21)
 txt(d,(1440,25),'출발 준비' if intro else '미션 완료' if outro else '주차 미션 진행',31,b=True)
 d.line((1410,80,1410,1030),fill=(47,62,82),width=2)
 x,y=r['screen'];y+=80;d.line((x,y+14,x,y+34),fill=BLUE,width=2);d.ellipse((x-17,y-17,x+17,y+17),fill=BLUE,outline=FG,width=2);d.text((x,y),'E',font=font(22,True),fill=BG,anchor='mm')
 d.rounded_rectangle((1435,100,1888,280),radius=18,fill=CARD);txt(d,(1458,123),'EGO VEHICLE',25,BLUE,True);txt(d,(1458,168),'저장한 IN 위치에서 출발',23);txt(d,(1458,214),'IN → 수직 → 평행 → OUT',23,MUTED)
 done=2 if outro else r['done']
 for j,(title,desc) in enumerate([('01  오른쪽 수직주차','두 차량 사이 빈 구획'),('02  왼쪽 평행주차','두 차량 사이 빈 구획')]):
  y=305+j*175;d.rounded_rectangle((1435,y,1888,y+152),radius=18,fill=CARD)
  txt(d,(1458,y+20),title,27,b=True);txt(d,(1458,y+64),desc,23,MUTED)
  state='완료' if done>j else '진행 중' if done==j and not intro else '대기';txt(d,(1458,y+105),state,23,GREEN if done>j else BLUE,True)
 d.rounded_rectangle((1435,683,1888,858),radius=18,fill=CARD);txt(d,(1458,704),'현재 차량 상태',24,b=True)
 txt(d,(1458,748),'출발 대기' if intro else 'OUT 도달' if outro else r['gear'],34,BLUE,True)
 txt(d,(1458,801),'각 주차구획에서 5초 이상 정차',22,MUTED)
 if r['hold']:
  txt(d,(1445,889),'주차 정지 유지',25,b=True);txt(d,(1445,933),f"{min(r['stop_time'],5.5):04.1f}초 / 5초",36,GREEN,True)
 else:
  txt(d,(1445,891),'앞바퀴 조향 · 뒷바퀴 방향 고정',22,MUTED);txt(d,(1445,934),'출차 전 후진으로 공간 확보',23)
 d.rounded_rectangle((275,133,1125,200),radius=15,fill=BG)
 d.text((700,166),'IN 출발 준비' if intro else '수직주차 · 평행주차 완료' if outro else r['stage'],font=font(29,True),fill=GREEN if outro else BLUE,anchor='mm')
 d.rectangle((0,1030,1920,1080),fill=BG)
 return im
if __name__=='__main__':
 import sys
 if '--preview' in sys.argv:
  for k in [0]+[next(i for i,r in enumerate(meta['frames']) if r['hold'] and r['done']==j) for j in (0,1)]+[len(meta['frames'])-1]:frame(k).save(OUT/f'check_{k}.png')
 else:
  proc=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-threads','4','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'parking_body.mp4')],stdin=subprocess.PIPE)
  for i in range(len(meta['frames'])):
   proc.stdin.write(frame(i).tobytes())
   if i%120==0:print('ENCODING',i,flush=True)
  last=frame(len(meta['frames'])-1,outro=True);last.save(OUT/'parking_poster.png')
  for _ in range(72):proc.stdin.write(last.tobytes())
  proc.stdin.close();assert proc.wait()==0
  signal=ROOT/'output/blender/start_signal'
  subprocess.run(['ffmpeg','-y','-v','error','-i',str(signal/'parking_countdown.mp4'),'-i',str(OUT/'parking_body.mp4'),'-i',str(signal/'user_start_signal_full.mp3'),'-filter_complex',f"[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a]apad=whole_dur={(len(meta['frames'])+212)/24},atrim=duration={(len(meta['frames'])+212)/24}[a]",'-map','[v]','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-threads','4','-c:a','aac','-b:a','192k','-shortest','-movflags','+faststart',str(OUT/'parking_driving.mp4')],check=True)
  print('VIDEO_COMPLETE',(len(meta['frames'])+212)/24)

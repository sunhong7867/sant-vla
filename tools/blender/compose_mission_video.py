"""Compose mission footage in the tournament graphic format."""
from pathlib import Path
import json,time,subprocess,wave
import numpy as np
from PIL import Image,ImageDraw
from compose_tournament_video import font,txt,clock,BG,CARD,FG,MUTED,COLORS
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/mission'
meta=json.loads((OUT/'metadata.json').read_text())
BLUE=COLORS[0]; GREEN=(71,229,132); RED=(255,89,97)
def image_frame(index,phase='drive',count=0):
 path=OUT/'frames'/f'mission_{index+1:04d}.png';deadline=time.monotonic()+900
 while True:
  try:
   with path.open('rb') as f:
    f.seek(-12,2)
    if f.read()!=bytes.fromhex('0000000049454e44ae426082'):raise OSError('Frame incomplete')
   base=Image.open(path).convert('RGB');break
  except (OSError,SyntaxError):
   if time.monotonic()>deadline:raise
   time.sleep(.2)
 image=Image.new('RGB',(1920,1080),BG);image.paste(base,(0,80));d=ImageDraw.Draw(image)
 rec=meta['frames'][index]
 txt(d,(32,23),'장애물 회피 · 신호등 미션',33,b=True)
 txt(d,(585,31),'미션 1 주행 예시',23,MUTED)
 d.rounded_rectangle((1135,18,1380,62),radius=12,fill=CARD)
 txt(d,(1150,29),'심판 확인 대기' if rec['phase']=='stop' else '주행 2배속 · 연출',21)
 txt(d,(1440,25),'출발 준비' if phase=='intro' else '미션 결과' if phase=='outro' else '미션 진행',32,b=True)
 d.line((1410,80,1410,1030),fill=(47,62,82),width=2)
 x,y=rec['screen'];y+=80
 d.line((x,y+16,x,y+37),fill=BLUE,width=2);d.ellipse((x-18,y-18,x+18,y+18),fill=BLUE,outline=FG,width=2)
 d.text((x,y),'E',font=font(23,True),fill=BG,anchor='mm')
 for i,(x,y) in enumerate(rec['obstacles']):
  y+=80
  done=rec['completed']>i and phase!='intro'
  color=GREEN if done else (181,190,205)
  d.line((x,y+14,x,y+32),fill=color,width=2)
  d.ellipse((x-15,y-15,x+15,y+15),fill=CARD,outline=color,width=2)
  d.text((x,y),str(i+1),font=font(19,True),fill=color,anchor='mm')
 d.rounded_rectangle((1435,100,1888,290),radius=18,fill=CARD)
 txt(d,(1458,122),'EGO VEHICLE',25,BLUE,True)
 txt(d,(1458,159),'출발: M3 · 예시 경과시간',21,MUTED)
 txt(d,(1458,195),clock(0 if phase=='intro' else rec['time']),42,b=True)
 d.rounded_rectangle((1435,313,1888,548),radius=18,fill=CARD)
 n=0 if phase=='intro' else rec['completed']
 txt(d,(1458,337),f'장애물 회피   {n} / 3',26,b=True)
 for j in range(3):
  done=n>j;y=391+j*46
  d.ellipse((1460,y+2,1474,y+16),fill=GREEN if done else (79,92,112))
  txt(d,(1488,y-3),f'장애물 {j+1}',23)
  txt(d,(1753,y-3),'통과' if done else '대기',22,GREEN if done else MUTED,True)
 txt(d,(1440,578),'미션 순서',26,b=True)
 for j,text in enumerate(['점선 침범 허용 · 연속 회피','빨간불 정차 · 심판 정차 확인','심판 수동 초록불 → 재출발']):txt(d,(1440,623+j*41),text,22,MUTED)
 d.rounded_rectangle((1435,778,1888,1008),radius=18,fill=CARD)
 txt(d,(1458,795),'현재 신호등',23,b=True)
 active='green' if phase=='intro' else rec['signal']
 for i,(name,color) in enumerate([('red',RED),('yellow',(255,190,55)),('green',GREEN)]):
  x=1516+139*i;y=870;on=active==name
  d.ellipse((x-29,y-29,x+29,y+29),fill=color if on else (45,54,68),outline=color if on else (63,76,94),width=3)
 label='초록불 · 진행' if active=='green' else '빨간불 · 정차 준비'
 if rec['phase']=='stop':label='빨간불 · 정지 유지'
 if rec['phase']=='resume':label='초록불 · 재출발'
 txt(d,(1458,921),label,27,GREEN if active=='green' else RED,True)
 bottom='심판의 정차구역 확인 대기' if rec['phase']=='stop' else '심판 확인 후 수동 신호 전환' if rec['phase']=='resume' else '영상 속 신호등과 동기화'
 txt(d,(1458,964),bottom,21,MUTED)
 if phase=='intro':
  d.rounded_rectangle((260,365,1150,660),radius=24,fill=BG,outline=(62,82,105),width=2)
  txt(d,(310,400),'M3 → 장애물 3대 → 신호등',37,b=True)
  txt(d,(310,464),'첫 초록불 통과 후, 복귀하여 빨간불에 정차',25,MUTED)
  d.text((705,574),str(count),font=font(64,True),fill=BLUE,anchor='mm')
 elif phase=='outro':
  d.rounded_rectangle((330,165,1080,315),radius=20,fill=BG,outline=GREEN,width=2)
  txt(d,(375,187),'장애물 회피 · 신호등 미션 완료',34,b=True)
  txt(d,(375,248),'장애물 3 / 3   ·   심판 확인 후 재출발',26,GREEN)
 else:
  d.rounded_rectangle((385,155,1025,218),radius=15,fill=BG)
  d.text((705,187),rec['stage'],font=font(27,True),fill=RED if rec['phase']=='stop' else BLUE,anchor='mm')
  if rec['phase']=='stop':
   d.rounded_rectangle((425,505,990,665),radius=20,fill=BG,outline=RED,width=2)
   txt(d,(468,531),'정차구역 확인 중',31,b=True)
   txt(d,(468,586),'심판의 수동 신호 전환 대기',27,RED,True)
 d.rectangle((0,1030,1920,1080),fill=BG)
 txt(d,(30,1046),'규정 ver3.1  §2.3 · §4.5 · §4.7  |  Blender 경로 애니메이션 / 실제 제어 기록이 아닌 설명용 예시',20,MUTED)
 return image

if __name__=='__main__':
 import sys
 if '--preview' in sys.argv:
  image_frame(int(sys.argv[-1])).save(OUT/'preview.png');raise SystemExit
 fps=24;intro=96;outro=120;n=len(meta['frames'])
 proc=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','24','-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-threads','4','-pix_fmt','yuv420p','-movflags','+faststart',str(OUT/'mission_silent.mp4')],stdin=subprocess.PIPE)
 for k in range(intro):proc.stdin.write(image_frame(0,'intro',3-k//32).tobytes())
 for k in range(n):
  proc.stdin.write(image_frame(k).tobytes())
  if k%120==0:print('ENCODING',k,'/',n,flush=True)
 last=image_frame(n-1,'outro')
 for k in range(outro):proc.stdin.write(last.tobytes())
 proc.stdin.close();assert proc.wait()==0
 duration=(intro+n+outro)/fps;sr=48000;audio=np.zeros(round(duration*sr),dtype=np.float32)
 for start,length,hz in [(0,.1,600),(1.33,.1,600),(2.66,.1,600),(3.78,.22,1000),(34.5,.18,850)]:
  t=np.arange(round(length*sr))/sr;signal=.13*np.sin(2*np.pi*hz*t)*np.sin(np.pi*np.arange(len(t))/len(t))**2
  j=round(start*sr);audio[j:j+len(t)]+=signal
 with wave.open(str(OUT/'signals.wav'),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())
 subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(OUT/'mission_silent.mp4'),'-i',str(OUT/'signals.wav'),'-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(OUT/'mission_driving.mp4')],check=True)
 last.save(OUT/'mission_poster.png');print('VIDEO_COMPLETE',duration,flush=True)

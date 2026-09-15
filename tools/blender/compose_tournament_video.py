"""Add Korean race graphics and a start tone to Blender-rendered frames."""
from pathlib import Path
import json, math, subprocess, wave, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/blender/tournament'
meta=json.loads((OUT/'metadata.json').read_text())
FONT='/usr/share/fonts/truetype/nanum/NanumBarunGothic.ttf'
BOLD='/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf'
fonts={}
def font(n,b=False):
 key=(n,b)
 if key not in fonts: fonts[key]=ImageFont.truetype(BOLD if b else FONT,n)
 return fonts[key]
BG=(14,21,33); CARD=(25,36,52); FG=(239,244,250); MUTED=(163,180,202)
COLORS=[(81,180,255),(255,180,84)]
def txt(draw,xy,text,size=25,fill=FG,b=False): draw.text(xy,text,font=font(size,b),fill=fill)
def clock(t): return f'{int(t//60):02d}:{t%60:05.2f}'
def frame_image(index,phase='race',count=0):
 deadline=time.monotonic()+900
 while True:
  try:
   frame_path=OUT/'frames'/f'race_{index+1:04d}.png'
   with frame_path.open('rb') as check:
    check.seek(-12,2)
    if check.read()!=bytes.fromhex('0000000049454e44ae426082'):
     raise OSError('Frame still being written')
   base=Image.open(frame_path).convert('RGB')
   break
  except (FileNotFoundError, OSError, SyntaxError):
   if time.monotonic()>deadline: raise
   time.sleep(.2)
 image=Image.new('RGB',(1920,1080),BG)
 image.paste(base,(0,80))
 d=ImageDraw.Draw(image)
 txt(d,(32,20),'자율주행 토너먼트',36,b=True)
 txt(d,(390,29),'본선 1 : 1 주행 예시',23, MUTED)
 d.rounded_rectangle((1150,18,1370,62),radius=12,fill=CARD)
 txt(d,(1170,28),'2배속 · 연출 영상',21)
 state={'intro':'출발 준비','race':'경기 진행','outro':'경기 결과'}[phase]
 txt(d,(1440,25),state,32,b=True)
 d.line((1410,80,1410,1030),fill=(47,62,82),width=2)
 rec=meta['frames'][index]
 for i,c in enumerate(rec['cars']):
  x,y=c['screen']; y+=80
  # A/B identity remains distinct while the body color stays white.
  d.line((x,y+16,x,y+37),fill=COLORS[i],width=2)
  d.ellipse((x-18,y-18,x+18,y+18),fill=COLORS[i],outline=FG,width=2)
  d.text((x,y),chr(65+i),font=font(23,True),fill=BG,anchor='mm')
  top=100+i*215
  d.rounded_rectangle((1435,top,1888,top+192),radius=18,fill=CARD)
  txt(d,(1458,top+20),f'{chr(65+i)}   EGO VEHICLE',25,COLORS[i],True)
  txt(d,(1458,top+57),'출발: '+('Start' if i==0 else 'T3 횡단보도'),20,MUTED)
  value=0 if phase=='intro' else c['time']
  txt(d,(1458,top+87),clock(value),42,b=True)
  lap='대기' if phase=='intro' else ('완주' if c['finished'] else f"{c['lap']} / 2 바퀴")
  txt(d,(1750,top+102),lap,23,COLORS[i],True)
  d.rounded_rectangle((1458,top+155,1866,top+165),radius=5,fill=(46,61,80))
  pct=0 if phase=='intro' else min(1,max(0,c['distance']-.02)/(2*meta['length']))
  if pct>0: d.rectangle((1458,top+155,1458+max(1,408*pct),top+165),fill=COLORS[i])
 txt(d,(1440,552),'경기 조건',26,b=True)
 rules=['Start / T3에서 각각 출발','2차선 · 반시계 방향 · 2바퀴','제한 시간 4분','점선 침범: 회당 +10초','차선 이탈: 경기 실패','상대 차량을 따라잡으면 승리']
 for j,r in enumerate(rules): txt(d,(1440,600+j*40),r,22,MUTED)
 d.rounded_rectangle((1435,862,1888,1008),radius=16,fill=CARD)
 if phase=='outro':
  txt(d,(1458,880),'A 승리 — 완주 시간 비교',25,COLORS[0],True)
  txt(d,(1458,923),'A 64.00초  /  B 70.00초',23)
  txt(d,(1458,965),'예시 페널티: 두 차량 모두 0초',20,MUTED)
 else:
  txt(d,(1458,880),'완주 시간 + 페널티로 판정',24,b=True)
  txt(d,(1458,924),'두 차량 모두 완주하는 예시',22,MUTED)
  txt(d,(1458,963),'실제 제어·평가 기록이 아닙니다',20,MUTED)
 if phase=='intro':
  d.rounded_rectangle((300,375,1110,645),radius=24,fill=BG,outline=(62,82,105),width=2)
  txt(d,(345,407),'Start와 T3, 두 곳에서 출발',35,b=True)
  txt(d,(345,463),'흰색 차량 2대 · 장애물 없는 시간측정 경기',25,MUTED)
  d.text((705,568),str(count) if count else 'READY',font=font(64,True),fill=COLORS[0],anchor='mm')
 elif phase=='race' and rec['time']<1.2:
  d.rounded_rectangle((545,170,845,240),radius=15,fill=BG)
  txt(d,(634,184),'출발!',38,COLORS[0],True)
 elif phase=='outro':
  d.rounded_rectangle((405,155,1010,275),radius=20,fill=BG,outline=COLORS[0],width=2)
  txt(d,(455,180),'두 차량 모두 2바퀴 완주',34,b=True)
  txt(d,(455,231),'예시 결과: A 64초 < B 70초',24,COLORS[0])
 d.rectangle((0,1030,1920,1080),fill=BG)
 txt(d,(30,1046),'규정 ver3.1  §2.2.2 · §3.1.2 · §5.1  |  Blender 경로 애니메이션 / 시간·결과는 설명용 예시',20,MUTED)
 return image

if __name__=='__main__':
 import sys
 if '--preview' in sys.argv:
  idx=int(sys.argv[-1]); frame_image(idx).save(OUT/'preview.png'); raise SystemExit
 fps=24
 intro=96; outro=120; n=len(meta['frames'])
 video=OUT/'tournament_silent.mp4'
 cmd=['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r',str(fps),'-i','-','-an','-c:v','libx264','-preset','fast','-crf','19','-threads','4','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
 proc=subprocess.Popen(cmd,stdin=subprocess.PIPE)
 for k in range(intro):
  count=3 if k<32 else 2 if k<64 else 1
  proc.stdin.write(frame_image(0,'intro',count).tobytes())
 for k in range(n):
  proc.stdin.write(frame_image(k).tobytes())
  if k%120==0: print('ENCODING',k,'/',n,flush=True)
 last=frame_image(n-1,'outro').tobytes()
 for k in range(outro): proc.stdin.write(last)
 proc.stdin.close(); assert proc.wait()==0
 duration=(intro+n+outro)/fps
 sr=48000; audio=np.zeros(round(duration*sr),dtype=np.float32)
 # Three countdown notes, then a final tone ending exactly before motion begins.
 for start,length,hz in [(0,.10,600),(1.33,.10,600),(2.66,.10,600),(3.78,.22,1000)]:
  t=np.arange(round(length*sr))/sr
  signal=.16*np.sin(2*np.pi*hz*t)*np.sin(np.pi*np.arange(len(t))/len(t))**2
  j=round(start*sr); audio[j:j+len(t)]+=signal
 with wave.open(str(OUT/'start_signal.wav'),'wb') as w:
  w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((audio*32767).astype('<i2').tobytes())
 subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-i',str(OUT/'start_signal.wav'),'-c:v','copy','-c:a','aac','-b:a','128k','-shortest','-movflags','+faststart',str(OUT/'tournament_driving.mp4')],check=True)
 frame_image(n-1,'outro').save(OUT/'tournament_poster.png')
 print('VIDEO_COMPLETE',duration,flush=True)

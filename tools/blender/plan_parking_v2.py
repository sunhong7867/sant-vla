"""Plan continuous parking maneuvers from the saved scene and check body clearance."""
import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/parking_v2'
g=json.load(open('/tmp/parking_geometry.json'));ego=g['01 Ego vehicle'];start=np.array(ego['location'][:2]);yaw=ego['rotation'][2]
def hull(p):
 p=np.array(p);return p[ConvexHull(p).vertices]
def rot(a):return np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
body=(hull(ego['points'])-start)@rot(yaw)
obstacles=[hull(v['points']) for k,v in g.items() if k.startswith('02')]
def gap(a,b):
 edges=np.concatenate((np.roll(a,-1,axis=0)-a,np.roll(b,-1,axis=0)-b));axes=np.stack((-edges[:,1],edges[:,0]),axis=1);axes/=np.linalg.norm(axes,axis=1)[:,None]
 ap=a@axes.T;bp=b@axes.T
 return max(np.maximum(bp.min(axis=0)-ap.max(axis=0),ap.min(axis=0)-bp.max(axis=0)))
def bez(p):
 p=np.array(p);t=np.linspace(0,1,301)[:,None];xy=(1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]
 d=3*(1-t)**2*(p[1]-p[0])+6*(1-t)*t*(p[2]-p[1])+3*t*t*(p[3]-p[2]);return xy,np.arctan2(d[:,1],d[:,0])+np.pi/2
perp=np.mean([g['02 obstacle4']['location'][:2],g['02 obstacle5']['location'][:2]],axis=0)
parallel=np.mean([g['02 obstacle6']['location'][:2],g['02 obstacle7']['location'][:2]],axis=0)
a=np.array([start[0],4.5]);b=np.array([-3.,9.4]);end=np.array([-1.9174,17.9385])
segments=[]
def add(p,duration,stage,reverse=False,done=0):
 xy,ang=bez(p)
 if reverse:ang+=np.pi
 segments.append(dict(xy=xy,ang=ang,duration=duration,stage=stage,gear='후진' if reverse else '전진',done=done))
def hold(duration,stage,done):
 last=segments[-1];segments.append(dict(xy=last['xy'][-1:],ang=last['ang'][-1:],duration=duration,stage=stage,gear='정차',done=done))
add([start,start+[0,3],a-[0,3],a],6,'IN 출발 · 수직주차 접근')
hold(.6,'수직주차 · 후진 전환',0)
p=[a,[a[0],perp[1]],[perp[0]-3,perp[1]],perp]
add(p,8,'오른쪽 수직주차 · 후진 진입',True);hold(5.5,'수직주차 · 정지 유지',0)
add(p[::-1],8,'수직주차 완료 · 전진 출차',False,1)
add([a,a+[0,1.5],b-[0,1.5],b],9,'왼쪽 평행주차 · 접근',False,1)
hold(.6,'후진 전환',1)
q=[b,[-3,5.4],[parallel[0],6.2],parallel]
add(q,9,'평행주차 · 후진 진입',True,1);hold(5.5,'평행주차 · 정지 유지',1)
add(q[::-1],9,'평행주차 완료 · 전진 출차',False,2)
add([b,b+[0,3],end-[0,3],end],6,'OUT 통과 · 미션 완료',False,2)
records=[];mins=[]
for seg in segments:
 xy=seg['xy'];ang=np.unwrap(seg['ang']);n=round(seg['duration']*24)
 if len(xy)==1:positions=np.repeat(xy,n,axis=0);angles=np.repeat(ang,n)
 else:
  dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))];t=np.linspace(0,1,n);u=(3*t*t-2*t*t*t)*dist[-1]
  positions=np.stack([np.interp(u,dist,xy[:,i]) for i in (0,1)],axis=1);angles=np.interp(u,dist,ang)
 minimum=100
 for pos,angle in zip(positions,angles):
  poly=body@rot(angle).T+pos;minimum=min(minimum,*[gap(poly,o) for o in obstacles])
  records.append(dict(xy=pos.tolist(),yaw=float(angle),stage=seg['stage'],gear=seg['gear'],done=seg['done'],hold=seg['gear']=='정차' and seg['duration']>5))
 mins.append([seg['stage'],minimum]);print(mins[-1])
assert min(v for _,v in mins)>.12,'Vehicle clearance too small'
assert np.linalg.norm(np.array(records[0]['xy'])-start)<1e-8
# Unwrap across forward/reverse transitions so wheels never spin in place.
angles=np.unwrap([r['yaw'] for r in records]);angles+=round((yaw-angles[0])/(2*np.pi))*2*np.pi
for r,angle in zip(records,angles):r['yaw']=float(angle)
assert np.max(np.abs(np.diff(angles)))<.12
(OUT/'path_plan.json').write_text(json.dumps(dict(fps=24,frames=records,start=ego['location'],perpendicular=perp.tolist(),parallel=parallel.tolist(),clearance_checks=mins),ensure_ascii=False))
print('PATH READY',len(records))

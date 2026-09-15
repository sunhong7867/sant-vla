"""Rear-axle bicycle-model parking with Ackermann steering and swept-body checks."""
import json,math
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/parking_v3'
g=json.load(open('/tmp/parking_geometry.json'));ego=g['01 Ego vehicle'];START=np.array(ego['location'][:2]);L=2.431;REAR=1.2325;TRACK=1.36
rot=lambda a:np.array([[np.cos(a),-np.sin(a)],[np.sin(a),np.cos(a)]])
def hull(p):
 p=np.array(p);return p[ConvexHull(p).vertices]
body=(hull(ego['points'])-START)@rot(ego['rotation'][2]);obs=[hull(v['points']) for k,v in g.items() if k.startswith('02')]
def gap(a,b):
 edges=np.concatenate((np.roll(a,-1,axis=0)-a,np.roll(b,-1,axis=0)-b));axes=np.stack((-edges[:,1],edges[:,0]),axis=1);axes/=np.linalg.norm(axes,axis=1)[:,None];aa=a@axes.T;bb=b@axes.T
 return float(max(np.maximum(bb.min(0)-aa.max(0),aa.min(0)-bb.max(0))))
def center(q):return q[:2]+REAR*np.array([np.cos(q[2]),np.sin(q[2])])
def advance(q,d,k):
 x,y,t=q
 if abs(k)<1e-10:return np.array([x+d*np.cos(t),y+d*np.sin(t),t])
 t2=t+d*k;return np.array([x+(np.sin(t2)-np.sin(t))/k,y+(-np.cos(t2)+np.cos(t))/k,t2])
def clearance(q):return min(gap(body@rot(q[2]+np.pi/2).T+center(q),o) for o in obs)
def check(q,d,k):return min(clearance(advance(q,u,k)) for u in np.linspace(0,d,max(3,int(abs(d)/.025))))
perp=np.mean([g['02 obstacle4']['location'][:2],g['02 obstacle5']['location'][:2]],axis=0);par=np.mean([g['02 obstacle6']['location'][:2],g['02 obstacle7']['location'][:2]],axis=0)
# Search radius and straight approach so the rear axle, not body center, follows each arc.
q0=np.r_[START-[0,REAR],np.pi/2];candidates=[]
for radius in np.arange(3.5,6.51,.1):
 a=np.array([START[0],perp[1]+radius,np.pi/2]);end=advance(a,-radius*np.pi/2,-1/radius);straight=perp[0]+REAR-end[0]
 if straight<0:continue
 margin=min(check(q0,a[1]-q0[1],0),check(a,-radius*np.pi/2,-1/radius),check(end,-straight,0))
 if margin>.25:candidates.append((margin,radius,a,straight))
assert candidates,'No perpendicular maneuver'
margin,R,a,straight=max(candidates,key=lambda x:x[0]);print('PERP',R,margin)
# Reverse S-curve into parallel bay, with a realistic rear-axle turning radius.
pstart=None
for rp in np.arange(3.5,6.01,.1):
 dx=-3-par[0];alpha=np.arccos(1-dx/(2*rp));dy=2*rp*np.sin(alpha)
 qs=np.array([-3.,par[1]-REAR+dy,np.pi/2]);qm=advance(qs,-rp*alpha,1/rp);qe=advance(qm,-rp*alpha,-1/rp)
 margin=min(check(qs,-rp*alpha,1/rp),check(qm,-rp*alpha,-1/rp))
 if margin>.22:pstart=(rp,alpha,qs,qe,margin);break
assert pstart,'No feasible parallel entry'
rp,alpha,qs,qe,margin=pstart;print('PARALLEL',rp,margin,qs)
# Compare departure with and without backing up, then choose sufficient clearance.
options=[]
for back in np.arange(0,1.51,.05):
 qb=advance(qe,-back,0)
 for rx in np.arange(3.5,6.01,.1):
  ax=np.arccos(1-(-3-par[0])/(2*rx));qm=advance(qb,rx*ax,-1/rx)
  margin=min(check(qe,-back,0),check(qb,rx*ax,-1/rx),check(qm,rx*ax,1/rx))
  if margin>.28:options.append((back,rx,ax,margin));break
assert options,'No feasible exit'
back,rx,ax,margin=options[0];print('EXIT',back,rx,margin)
# Prefer a visible rearward clearance maneuver even if the wider theoretical path fits.
if back<.5:
 options=[v for v in options if v[0]>=.5];assert options;back,rx,ax,margin=options[0]
segments=[];q=q0.copy();lastk=0;done=0

def pause(seconds,label,qualify=False,newk=0):
 global lastk
 segments.append(dict(q=q.copy(),d=0.,k=newk,oldk=lastk,seconds=seconds,stage=label,done=done,hold=qualify));lastk=newk

def move(d,k,label,speed=1.5):
 global q,lastk
 if abs(k-lastk)>1e-8:pause(.7,'정지 · 앞바퀴 조향',False,k)
 margin=check(q,d,k);assert margin>.18,(label,margin)
 segments.append(dict(q=q.copy(),d=float(d),k=k,oldk=k,seconds=max(1.2,abs(d)/speed+1),stage=label,done=done,hold=False,margin=margin))
 q=advance(q,d,k);lastk=k

move(a[1]-q[1],0,'IN 출발 · 수직주차 접근',2.5);pause(.6,'후진 전환')
move(-R*np.pi/2,-1/R,'수직주차 · 후진 조향');move(-straight,0,'수직주차 · 후진 정렬',1)
assert np.linalg.norm(center(q)-perp)<1e-5
pause(5.5,'수직주차 · 정지 유지',True);done=1
move(straight,0,'수직주차 · 전진 출차',1);move(R*np.pi/2,-1/R,'수직주차 · 통로로 출차')
# Straight approach preserves heading; small lateral shift uses two broad arcs.
dx=qs[0]-q[0];rr=5.;ang=np.arccos(1-abs(dx)/(2*rr));sign=1 if dx<0 else -1
move(rr*ang,sign/rr,'평행주차 · 접근');move(rr*ang,-sign/rr,'평행주차 · 접근')
move(qs[1]-q[1],0,'평행주차 · 후진 시작 위치',1.5);assert np.linalg.norm(q-qs)<1e-5
pause(.6,'후진 전환');move(-rp*alpha,1/rp,'평행주차 · 후진 진입',1);move(-rp*alpha,-1/rp,'평행주차 · 후진 정렬',1)
assert np.linalg.norm(center(q)-par)<1e-5
pause(5.5,'평행주차 · 정지 유지',True);done=2
move(-back,0,'출차 준비 · 뒤로 이동해 공간 확보',.6);pause(.7,'정지 · 전진 전환')
move(rx*ax,-1/rx,'평행주차 출차 · 앞바퀴 우측 조향',.9);move(rx*ax,1/rx,'평행주차 출차 · 차체 정렬',1.2)
end=np.array([-1.9174,17.9385-REAR,np.pi/2]);dx=end[0]-q[0];rr=5.;ang=np.arccos(1-dx/(2*rr))
move(rr*ang,-1/rr,'OUT 접근');move(rr*ang,1/rr,'OUT 방향 정렬');move(end[1]-q[1],0,'OUT 통과 · 미션 완료',2)
records=[];distance=0
for seg in segments:
 n=math.ceil(seg['seconds']*24);tt=np.linspace(0,1,n);smooth=3*tt**2-2*tt**3
 for t,u in zip(tt,smooth):
  state=advance(seg['q'],seg['d']*u,seg['k']);k=seg['oldk']+(seg['k']-seg['oldk'])*u if seg['d']==0 else seg['k']
  left=np.arctan2(L*k,1-k*TRACK/2);right=np.arctan2(L*k,1+k*TRACK/2)
  assert max(abs(left),abs(right))<np.deg2rad(50)
  records.append(dict(xy=center(state).tolist(),rear=state[:2].tolist(),yaw=float(state[2]+np.pi/2),steer_left=float(left),steer_right=float(right),roll=float((distance+seg['d']*u)/.259),stage=seg['stage'],gear=' 정차'.strip() if seg['d']==0 else '전진' if seg['d']>0 else '후진',done=seg['done'],hold=seg['hold']))
 distance+=seg['d']
# Rear axle motion has zero lateral velocity by construction; verify discretization residual.
r=np.array([v['rear'] for v in records]);h=np.array([v['yaw']-np.pi/2 for v in records]);dh=(h[:-1]+h[1:])/2;delta=np.diff(r,axis=0);slip=abs(-delta[:,0]*np.sin(dh)+delta[:,1]*np.cos(dh));assert max(slip)<1e-8
checks=[[s['stage'],s['margin']] for s in segments if 'margin'in s]
(OUT/'path_plan.json').write_text(json.dumps(dict(fps=24,frames=records,start=ego['location'],wheelbase=L,rear_offset=REAR,back_distance=back,clearance_checks=checks,max_rear_lateral_step=float(max(slip))),ensure_ascii=False));print('READY',len(records),'back',back)

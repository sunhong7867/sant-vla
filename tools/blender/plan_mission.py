"""Plan an illustrative obstacle path and verify geometric separation."""
from pathlib import Path
import json,math
import numpy as np
from scipy.spatial import ConvexHull
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/blender/mission'
p=json.loads((ROOT/'src/sant_vla_pkg/config/track_paths.json').read_text())
q=np.array(p['lane2']); qq=np.vstack((q,q[0])); vec=np.diff(qq,axis=0)
lens=np.linalg.norm(vec,axis=1); arc=np.r_[0,np.cumsum(lens)]; L=arc[-1]
def at(st):
 return np.array([np.interp(st%L,arc,qq[:,i]) for i in (0,1)])
def direction(st):
 v=at(st+.2)-at(st-.2);return v/np.linalg.norm(v)
def project(pt):
 u=np.clip(np.sum((np.array(pt)-q)*vec,axis=1)/lens**2,0,1)
 points=q+u[:,None]*vec;k=np.linalg.norm(points-pt,axis=1).argmin()
 return arc[k]+u[k]*lens[k]
# Locate the actual M3 marker in the texture, not just its nearby named waypoint.
im=np.array(Image.open(ROOT/'src/simulation_pkg/models/race_track/materials/textures/track.png').convert('RGB'))
a=im[230:380,520:590]
mask=(a.max(2)-a.min(2)<5)&(a.min(2)>110)&(a.max(2)<210)
y,x=np.where(mask);x+=520;y+=230
sel=abs(x-(542+.1*(y-177)))<5
slope,intercept=np.polyfit(y[sel],x[sel],1)
candidates=np.linspace(24,30,6001)
def marker_error(st):
 point=at(st);u=(point[1]/58.1364+.5)*2346;v=(point[0]/43.71084+.5)*1759
 return abs(u-slope*v-intercept)
m3=float(min(candidates,key=marker_error))
geometry=json.loads(Path('/tmp/mission_geometry.json').read_text())
objects=json.loads(Path('/tmp/mission_scene_objects.json').read_text())
local=np.array(geometry['01 Ego vehicle']['local']); ego_poly=local[ConvexHull(local).vertices]
nose=-local[:,1].min()
start=m3-nose-.10
signal=project((.559,-24.573))
stop=signal+L-nose-.55
obs_s=[project(objects[f'02 obstacle{i}']['location'][:2]) for i in (1,2,3)]
polys=[]
for i in (1,2,3):
 pts=np.array(geometry[f'02 obstacle{i}']['world']);polys.append(pts[ConvexHull(pts).vertices])
def smooth(t):
 t=np.clip(t,0,1);return t*t*t*(t*(t*6-15)+10)
def offset(st):
 # Cross the dashed line freely. Change sides only to clear the next obstacle.
 # After obstacle 3, stay on the inner route through the signal stop.
 c1,c2,c3=obs_s
 controls=[(start,0),(c1-13,0),(c1-5,3.15),(c1+4,3.15),
           (c2-4,.2),(c2+4,.2),(c3-5,3.15),(stop+10,3.15)]
 for (sa,oa),(sb,ob) in zip(controls,controls[1:]):
  if st<=sb:return oa+(ob-oa)*float(smooth((st-sa)/(sb-sa)))
 return 3.15
def route(st):
 v=direction(st);return at(st)+np.array([-v[1],v[0]])*offset(st)
stations=np.linspace(start,stop+9,5000)
xy=np.array([route(st) for st in stations])
tangent=np.gradient(xy,axis=0)
head=np.unwrap(np.arctan2(tangent[:,1],tangent[:,0])+math.pi/2)
travel=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
stop_distance=float(np.interp(stop,stations,travel))
def sat_gap(a,b):
 edges=np.vstack((np.roll(a,-1,axis=0)-a,np.roll(b,-1,axis=0)-b))
 axes=np.column_stack((-edges[:,1],edges[:,0])); axes/=np.linalg.norm(axes,axis=1)[:,None]
 pa=a@axes.T;pb=b@axes.T
 return float(np.maximum(pb.min(0)-pa.max(0),pa.min(0)-pb.max(0)).max())
clearances=[999.,999.,999.]
for pos,angle in zip(xy[::2],head[::2]):
 r=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
 poly=ego_poly@r.T+pos
 for j,ob in enumerate(polys):
  gap=sat_gap(poly,ob)
  clearances[j]=min(clearances[j],gap)
assert min(clearances)>.3,clearances
spec={'length':float(L),'start':float(start),'stop':float(stop),'signal':float(signal),'obstacles':obs_s,'nose':float(nose),'stations':stations.tolist(),'xy':xy.tolist(),'heading':head.tolist(),'travel':travel.tolist(),'stop_distance':stop_distance,'clearances':clearances}
(OUT/'path_plan.json').write_text(json.dumps(spec))
print('MISSION PLAN:', 'M3',m3,'travel to stop',stop_distance,'obstacle clearances',clearances)

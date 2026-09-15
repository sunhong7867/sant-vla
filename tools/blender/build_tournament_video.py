"""Rule-based illustrative race animation; not a ROS controller evaluation."""
import bpy, json, math
import numpy as np
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/blender/tournament'
FRAMES=OUT/'frames'
FRAMES.mkdir(parents=True,exist_ok=True)
s=bpy.context.scene
path=json.loads((ROOT/'src/sant_vla_pkg/config/track_paths.json').read_text())
q=np.array(path['lane2'],dtype=float)
assert np.sum(q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1))>0
lengths=np.linalg.norm(np.roll(q,-1,axis=0)-q,axis=1)
arc=np.r_[0,np.cumsum(lengths)]
L=arc[-1]
qq=np.vstack([q,q[0]])
def at(distance):
 d=distance%L
 return np.array([np.interp(d,arc,qq[:,k]) for k in (0,1)])
def tangent(distance):
 v=at(distance+.25)-at(distance-.25)
 return math.atan2(v[1],v[0])
def nearest(point):
 best=(1e9,0)
 for i in range(len(q)):
  a=q[i]; v=qq[i+1]-a; u=np.clip(np.dot(np.array(point)-a,v)/np.dot(v,v),0,1)
  distance=np.linalg.norm(a+u*v-point)
  if distance<best[0]: best=(distance,arc[i]+u*lengths[i])
 return best[1]
# Current texture has Start/S1 thin line at x=1.28, T3 broad line at x=.559.
# Set the visible front bumper behind each line. Track uses original simulation scale.
line_s=[nearest((1.28,24.548)),nearest((.559,-24.573))]
cars=[bpy.data.objects['01 Ego vehicle'],bpy.data.objects['01 Ego vehicle 2']]
for o in list(bpy.data.objects):
 if o.type=='EMPTY' and o.name.startswith('02 obstacle'):
  for c in list(o.children_recursive): bpy.data.objects.remove(c,do_unlink=True)
  bpy.data.objects.remove(o,do_unlink=True)
# No signal stop mission in a tournament: hide the display stand for this video only.
for o in bpy.data.objects:
 if o.name.startswith('03 Traffic light'): o.hide_render=True
for car in cars:
 car.animation_data_clear()
 for c in car.children:
  if c.name.split(' / ',1)[-1] in ('Cube','Cube.001','Cylinder.001'):
   c.hide_render=True; c.hide_set(True)
# White body for both cars; A/B overlays distinguish them.
mat=bpy.data.materials.new('Tournament white')
mat.diffuse_color=(.92,.94,.97,1)
for car in cars:
 for c in car.children:
  if c.name.endswith(' / Hybrid'):
   c.data=c.data.copy(); c.data.materials.clear(); c.data.materials.append(mat)
noses=[]
for car in cars:
 points=[c.matrix_basis@Vector(v) for c in car.children if c.type=='MESH' and not c.hide_render for v in c.bound_box]
 noses.append(-min(v.y for v in points))
# Course illustration: A completes in 64 s, B in 70 s; no penalty or catch-up.
times=[64.,70.]
def progress(t,T):
 a=.8; t=max(0,min(t,T)); velocity=(2*L+.04)/(T-a)
 if t<a: return velocity*t*t/(2*a)
 if t>T-a: return 2*L+.04-velocity*(T-t)**2/(2*a)
 return velocity*(t-a/2)
s.render.fps=24
s.frame_start=1; s.frame_end=841
s.render.engine='BLENDER_WORKBENCH'
s.display.shading.light='STUDIO'
s.display.shading.color_type='TEXTURE'
s.display.shading.show_shadows=True
s.display.shading.show_cavity=True
s.display.shading.cavity_type='BOTH'
s.display.shading.show_specular_highlight=True
s.display.shading.background_type='WORLD'
s.world.color=(.025,.035,.055)
s.view_settings.view_transform='Standard'
s.view_settings.exposure=.35
s.render.resolution_x=1400
s.render.resolution_y=1000
s.render.resolution_percentage=100
s.render.image_settings.file_format='PNG'
s.camera=bpy.data.objects['Overview']
s.camera.data.type='ORTHO'; s.camera.data.ortho_scale=80
previous=[None,None]
metadata=[]
for frame in range(1,s.frame_end+1):
 t=(frame-1)/12
 data={'time':t,'cars':[]}
 for i,car in enumerate(cars):
  d=progress(t,times[i]); station=line_s[i]-noses[i]-.02+d
  xy=at(station); angle=tangent(station)+math.pi/2
  if previous[i] is not None:
   angle=previous[i]+(angle-previous[i]+math.pi)%(2*math.pi)-math.pi
  previous[i]=angle
  car.location=(*xy,.01265)
  car.rotation_euler=(0,0,angle)
  car.keyframe_insert(data_path='location',frame=frame)
  car.keyframe_insert(data_path='rotation_euler',frame=frame)
  data['cars'].append({'distance':d,'time':min(t,times[i]),'finished':t>=times[i], 'lap':min(2,1+int(max(0,d-.02)//L))})
 bpy.context.view_layer.update()
 for i,car in enumerate(cars):
  v=world_to_camera_view(s,s.camera,car.location+Vector((0,0,2.6)))
  data['cars'][i]['screen']=[v.x*1400,(1-v.y)*1000]
 metadata.append(data)
for car in cars:
 for fc in car.animation_data.action.fcurves:
  for k in fc.keyframe_points: k.interpolation='LINEAR'
s['Video description']='Illustrative tournament heat: Start/T3, lane 2 CCW, two laps. Example times A=64s B=70s, zero penalties; playback 2x. Not real controller footage.'
s.frame_set(1)
s.render.filepath=str(FRAMES/'race_')
(OUT/'metadata.json').write_text(json.dumps({'length':L,'fps':24,'playback':2,'frames':metadata}))
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'tournament_animated.blend'))
print('ANIMATION_READY',L,noses,flush=True)
bpy.ops.render.render(animation=True)

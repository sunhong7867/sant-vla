"""Animate the planned mission, with a judge-confirmed manual signal change."""
import bpy,json,math
import numpy as np
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'output/blender/mission';FRAMES=OUT/'frames';FRAMES.mkdir(exist_ok=True)
p=json.loads((OUT/'path_plan.json').read_text());s=bpy.context.scene
for root in [o for o in bpy.data.objects if o.type=='EMPTY']:
 if root.name.startswith('02 obstacle') and root.name not in ['02 obstacle1','02 obstacle2','02 obstacle3']:
  for c in list(root.children_recursive):bpy.data.objects.remove(c,do_unlink=True)
  bpy.data.objects.remove(root,do_unlink=True)
for col in list(bpy.data.collections):
 if col.name.startswith('02 obstacle') and not col.objects:bpy.data.collections.remove(col)
ego=bpy.data.objects['01 Ego vehicle'];ego.animation_data_clear()
for o in bpy.data.objects:
 if o.parent and (o.parent.name.startswith('01 Ego') or o.parent.name.startswith('02 obstacle')):
  if o.name.split(' / ',1)[-1] in ('Cube','Cube.001','Cylinder.001'):
   o.hide_render=True;o.hide_set(True)
for o in bpy.data.objects:
 if o.name.startswith('03 Traffic light'):o.hide_render=False;o.hide_set(False)
# Give signal lenses independent keyframed display and render colors.
lamps={}
for suffix,color in [('Cylinder',(1,.025,.025,1)),('Cylinder.001',(1,.65,.02,1)),('Cylinder.002',(.025,1,.08,1))]:
 o=bpy.data.objects['03 Traffic light / '+suffix]
 mat=bpy.data.materials.new('Mission signal '+suffix);mat.use_nodes=True
 o.data=o.data.copy();o.data.materials.clear();o.data.materials.append(mat)
 lamps[suffix]=(mat,color)
s.render.engine='BLENDER_WORKBENCH';s.display.shading.light='STUDIO';s.display.shading.color_type='TEXTURE'
s.display.shading.show_shadows=True;s.display.shading.show_cavity=True;s.display.shading.cavity_type='BOTH'
s.display.shading.show_specular_highlight=True;s.display.shading.background_type='WORLD';s.world.color=(.025,.035,.055)
s.view_settings.view_transform='Standard';s.view_settings.exposure=.35
s.render.resolution_x=1400;s.render.resolution_y=1000;s.render.resolution_percentage=100
s.render.fps=24;s.frame_start=1;s.frame_end=781;s.render.image_settings.file_format='PNG'
s.camera=bpy.data.objects['Overview'];s.camera.data.type='ORTHO';s.camera.data.ortho_scale=80
travel=np.array(p['travel']);points=np.array(p['xy']);heads=np.array(p['heading']);stations=np.array(p['stations'])
D=p['stop_distance'];T=55.;a=2.;b=3.;speed=D/(T-(a+b)/2)
def move(t):
 if t<a:return speed*t*t/(2*a)
 if t>T-b:return D-speed*(T-t)**2/(2*b)
 return speed*(t-a/2)
metadata=[];previous_signal=None
for frame in range(1,782):
 tv=(frame-1)/24
 if tv<27.5: elapsed=tv*2;d=move(elapsed);hold=0;phase='drive'
 elif tv<30.5:elapsed=55+tv-27.5;d=D;hold=tv-27.5;phase='stop'
 else:
  t=(tv-30.5)*2;elapsed=58+t;v=9/3.5;d=D+(v*t*t/2 if t<1 else v*(t-.5));hold=3;phase='resume'
 st=float(np.interp(d,travel,stations));xy=[float(np.interp(d,travel,points[:,i])) for i in (0,1)]
 angle=float(np.interp(d,travel,heads))
 ego.location=(*xy,.01265);ego.rotation_euler=(0,0,angle)
 ego.keyframe_insert(data_path='location',frame=frame);ego.keyframe_insert(data_path='rotation_euler',frame=frame)
 judge_confirmed = tv>=30.5  # Staged referee event for this explanatory animation.
 signal='green' if st<p['signal']+8 or judge_confirmed else 'red'
 if frame in (1,733):
  s['judge_confirmed']=int(judge_confirmed)
  s.keyframe_insert(data_path='["judge_confirmed"]',frame=frame)
 if signal!=previous_signal:
  for name,(mat,color) in lamps.items():
   active=(name=='Cylinder' and signal=='red') or (name=='Cylinder.002' and signal=='green')
   mat.diffuse_color=color if active else (.055,.065,.06,1)
   mat.keyframe_insert(data_path='diffuse_color',frame=frame)
   bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
   bs.inputs['Base Color'].default_value=mat.diffuse_color;bs.inputs['Base Color'].keyframe_insert(data_path='default_value',frame=frame)
   bs.inputs['Emission Color'].default_value=color;bs.inputs['Emission Strength'].default_value=3 if active else 0
   bs.inputs['Emission Strength'].keyframe_insert(data_path='default_value',frame=frame)
  previous_signal=signal
 completed=sum(st>v+5 for v in p['obstacles'])
 if phase=='stop':stage='정차구역 정차 · 심판 확인 대기'
 elif phase=='resume':stage='심판 초록불 전환 · 재출발'
 elif completed==3:stage='신호등 정차구역으로 복귀'
 elif st<p['signal']+8:stage='M3 출발 · 초록불 통과'
 else:stage=f'장애물 {completed+1} 회피'
 bpy.context.view_layer.update()
 v=world_to_camera_view(s,s.camera,ego.location+Vector((0,0,2.6)))
 obstacles=[]
 for i in (1,2,3):
  o=bpy.data.objects[f'02 obstacle{i}'];vp=world_to_camera_view(s,s.camera,o.location+Vector((0,0,2.6)))
  obstacles.append([vp.x*1400,(1-vp.y)*1000])
 metadata.append({'time':elapsed,'screen':[v.x*1400,(1-v.y)*1000],'obstacles':obstacles,'completed':completed,'phase':phase,'stage':stage,'signal':signal,'hold':hold,'judge_confirmed':judge_confirmed,'station':st,'distance':d})
for fc in ego.animation_data.action.fcurves:
 for key in fc.keyframe_points:key.interpolation='LINEAR'
for mat,_ in lamps.values():
 for owner in (mat,mat.node_tree):
  if owner.animation_data and owner.animation_data.action:
   for fc in owner.animation_data.action.fcurves:
    for key in fc.keyframe_points:key.interpolation='CONSTANT'
assert all(x['signal']=='red' and not x['judge_confirmed'] for x in metadata if x['phase']=='stop')
for fc in s.animation_data.action.fcurves:
 for key in fc.keyframe_points:key.interpolation='CONSTANT'
assert metadata[-1]['completed']==3
s.frame_set(1)
s['Mission notes']='M3 start, three road obstacles, green first pass, red on return, wait for referee confirmation, manual green restart. Dashed line crossing allowed; no post-obstacle lane return. Illustrative path, not ROS control.'
s.render.filepath=str(FRAMES/'mission_')
(OUT/'metadata.json').write_text(json.dumps({'fps':24,'frames':metadata,'clearances':p['clearances']}))
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'mission_animated.blend'))
print('MISSION_READY: continuous route, referee-controlled signal sequence',flush=True)
# Render the unchanged hold view once, then reuse it; retain all animation keys.
import shutil
s.frame_end=661
bpy.ops.render.render(animation=True)
for frame in range(662,733):
 shutil.copy2(FRAMES/'mission_0661.png',FRAMES/f'mission_{frame:04d}.png')
s.frame_start=733;s.frame_end=781
bpy.ops.render.render(animation=True)

"""Animate the parking plan, preserving the user's saved setup."""
import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender/parking_v5';FRAMES=OUT/'frames';FRAMES.mkdir(exist_ok=True)
p=json.loads((OUT/'path_plan.json').read_text());s=bpy.context.scene;ego=bpy.data.objects['01 Ego vehicle'];initial=list(ego.location)
assert max(abs(a-b) for a,b in zip(initial,p['start']))<1e-6
fixed={o.name:o.matrix_world.copy() for o in bpy.data.objects if o.type=='EMPTY' and o.name.startswith('02 obstacle')}
s.render.engine='BLENDER_WORKBENCH';s.display.shading.light='STUDIO';s.display.shading.color_type='TEXTURE';s.display.shading.show_shadows=True;s.display.shading.show_cavity=True;s.display.shading.cavity_type='BOTH';s.display.shading.show_specular_highlight=True;s.display.shading.background_type='WORLD';s.world.color=(.025,.035,.055);s.display.render_aa='FXAA'
s.view_settings.view_transform='Standard';s.view_settings.exposure=.35
s.render.resolution_x=1400;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.fps=24;s.render.image_settings.file_format='PNG'
s.camera=bpy.data.objects['Parking overview'];s.camera.data.ortho_scale=51
s.frame_start=1;s.frame_end=len(p['frames']);ego.animation_data_clear()
wheels=[o for o in ego.children_recursive if 'Wheel_Front_Left_' in o.name]
for o in wheels:o.animation_data_clear()
for i,r in enumerate(p['frames'],1):
 for wheel in wheels:
  steer=(r['steer_left'] if wheel.location.x>0 else r['steer_right']) if wheel.location.y<0 else 0
  wheel.rotation_euler=(r['roll'],0,steer)
  wheel.keyframe_insert(data_path='rotation_euler',frame=i)
 ego.location=(*r['xy'],initial[2]);ego.rotation_euler=(0,0,r['yaw']);ego.keyframe_insert(data_path='location',frame=i);ego.keyframe_insert(data_path='rotation_euler',frame=i)
 bpy.context.view_layer.update();v=world_to_camera_view(s,s.camera,ego.location+Vector((0,0,2.5)));r['screen']=[v.x*1400,(1-v.y)*1000]
for animated in [ego]+wheels:
 for fc in animated.animation_data.action.fcurves:
  for k in fc.keyframe_points:k.interpolation='LINEAR'
for name,mat in fixed.items():assert all(abs(mat[r][c]-bpy.data.objects[name].matrix_world[r][c])<1e-6 for r in range(4) for c in range(4))
# Movement plays at 2x, while the two qualifying stops remain 5.5 real seconds.
selected=[];render_ids=set();last_pose=None;last_render=None;hold_time=0
for i,r in enumerate(p['frames']):
 r['realtime']=r['gear']=='정차' or '평행주차' in r['stage'] or '출차 준비' in r['stage']
 if not r['realtime'] and i%2:continue
 pose=tuple(r['xy'])+(r['yaw'],r['steer_left'],r['steer_right'],r['roll'])
 if pose!=last_pose:last_render=i;render_ids.add(i);last_pose=pose
 hold_time=hold_time+1/24 if r['hold'] else 0
 selected.append(dict(**r,source=i,render=last_render,stop_time=hold_time))
(OUT/'metadata.json').write_text(json.dumps(dict(fps=24,frames=selected,clearances=p['clearance_checks']),ensure_ascii=False))
s.frame_set(1);s['Parking animation']='Rear-axle bicycle model; Ackermann front steering only, fixed rear-wheel steering. Reverse perpendicular parking; reverse parallel parking; back up for exit clearance before forward departure.'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'parking_animated.blend'))
import shutil
old=ROOT/'output/blender/parking'
oldmeta=json.loads((old/'metadata.json').read_text())
def posekey(r):return tuple(round(v,6) for v in r['xy'])+tuple(round(r[k],6) for k in ['yaw','steer_left','steer_right','roll'])
reuse={posekey(r):r['render'] for r in oldmeta['frames']}
for r in selected:
 src=old/'frames'/f"parking_{reuse.get(posekey(r),-1):04d}.png"
 dst=FRAMES/f"parking_{r['render']:04d}.png"
 if src.exists() and not dst.exists():shutil.copy2(src,dst)
ids=sorted(render_ids)
if '--preview' in sys.argv:ids=[selected[j]['render'] for j in [0,len(selected)//4,len(selected)//2,3*len(selected)//4,len(selected)-1]]+ [next(r['render'] for r in selected if r['hold'] and r['done']==k) for k in (0,1)]
for i in sorted(set(ids)):
 dest=FRAMES/f'parking_{i:04d}.png'
 if dest.exists():continue
 s.frame_set(i+1);s.render.filepath=str(dest);bpy.ops.render.render(write_still=True)
print('PARKING_RENDER_COMPLETE',len(ids),flush=True)

"""Create a static parking setup while preserving the four parked reference cars."""
import bpy,json,math
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/blender'
target=OUT/'nav_vla_parking.blend'
assert not target.exists(),'Parking file already exists; preserve user edits'
keep={'01 Ego vehicle','02 obstacle4','02 obstacle5','02 obstacle6','02 obstacle7'}
poses={n:bpy.data.objects[n].matrix_world.copy() for n in keep if n!='01 Ego vehicle'}
for root in [o for o in bpy.data.objects if o.type=='EMPTY']:
 if (root.name.startswith('02 obstacle') or root.name.startswith('01 Ego vehicle')) and root.name not in keep:
  for child in list(root.children_recursive):bpy.data.objects.remove(child,do_unlink=True)
  bpy.data.objects.remove(root,do_unlink=True)
for col in list(bpy.data.collections):
 if (col.name.startswith('02 obstacle') or col.name.startswith('01 Ego')) and not col.objects and not col.children:bpy.data.collections.remove(col)
p=json.loads((ROOT/'src/sant_vla_pkg/config/track_paths.json').read_text())
ego=bpy.data.objects['01 Ego vehicle'];ego.location=(*p['zones']['IN']['pose'][:2],.01265);ego.rotation_euler=(0,0,math.pi)
ego['Parking role']='IN start; facing into the gray parking area'
for i in (4,5):bpy.data.objects[f'02 obstacle{i}']['Parking role']='Perpendicular parking reference vehicle'
for i in (6,7):bpy.data.objects[f'02 obstacle{i}']['Parking role']='Parallel parking reference vehicle'
bpy.context.view_layer.update()
for name,mat in poses.items():assert all(abs(mat[r][c]-bpy.data.objects[name].matrix_world[r][c])<1e-6 for r in range(4) for c in range(4))
assert len([o for o in bpy.data.objects if o.type=='EMPTY' and (o.name.startswith('01 Ego') or o.name.startswith('02 obstacle'))])==5
s=bpy.context.scene
s['Parking sequence']='IN -> perpendicular between obstacle4/5 -> parallel between obstacle6/7 -> OUT'
s['Perpendicular target center']=[3.7239151,-2.09053,0.0]
s['Parallel target center']=[-7.797351,2.678474,0.0]
s['Parking rule']='Each successful parking stage requires at least 5 seconds stationary; stages are continuous, without manual repositioning.'
cam=bpy.data.objects['Overview'].copy();cam.data=cam.data.copy();cam.name='Parking overview';bpy.context.scene.collection.objects.link(cam)
cam.location=(59,-75,88);cam.rotation_euler=(Vector((-3,0,0))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=49;s.camera=cam
for screen in bpy.data.screens:
 for area in screen.areas:
  if area.type=='VIEW_3D':
   area.spaces.active.region_3d.view_perspective='CAMERA'
   area.spaces.active.overlay.show_extras=False
bpy.ops.object.select_all(action='DESELECT');ego.select_set(True);bpy.context.view_layer.objects.active=ego
text=bpy.data.texts.new('주차 미션 안내')
text.write('주차용 정적 장면\n\nEgo: IN 지점에서 회색 영역 안쪽(+Y)을 향함.\n수직주차 기준 차량: obstacle4, obstacle5 (기존 위치 유지).\n평행주차 기준 차량: obstacle6, obstacle7 (기존 위치 유지).\n순서: IN → 두 기준 차량 사이 수직주차 → 두 기준 차량 사이 평행주차 → OUT.\n규정 제4.8절: 각 목표 주차구획에서 5초 이상 정차, 두 단계는 연속 주행.\n실제 목표 구획은 대회 당일 추첨하며, 이 장면은 사용자 지정 배치임.\n차량 이동: 오른쪽 목록의 차량 상위 객체 선택 후 G, Shift+Z.\n아직 이동 애니메이션은 없음.\n')
s.render.resolution_x=1400;s.render.resolution_y=1100;s.render.resolution_percentage=100
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(target))
s.render.filepath=str(OUT/'parking_setup.png');bpy.ops.render.render(write_still=True)
print('VERIFIED: five vehicles; four reference poses unchanged; ego at IN',list(ego.location))

"""Replace obstacles in the user-edited scene, preserving existing root poses."""
from pathlib import Path
import math
import shutil
import bpy
from mathutils import Matrix
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/blender'
source=OUT/'nav_vla_track.blend'
backup=OUT/'nav_vla_track_before_obstacle_update.blend'
if not backup.exists(): shutil.copy2(source,backup)
ego=bpy.data.objects['01 Ego vehicle']
parts=list(ego.children)
poses={o.name:o.matrix_world.copy() for o in bpy.data.objects if o.type=='EMPTY'}
white=bpy.data.materials.new('Obstacle white paint')
white.use_nodes=True
white.diffuse_color=(0.92,0.94,0.97,1)
bs=next(n for n in white.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
bs.inputs['Base Color'].default_value=white.diffuse_color
bs.inputs['Metallic'].default_value=0.15
bs.inputs['Roughness'].default_value=0.28
for i in range(1,8):
 name=f'02 obstacle{i}'
 if i<=5:
  root=bpy.data.objects[name]
  col=root.users_collection[0]
  for old in list(root.children): bpy.data.objects.remove(old,do_unlink=True)
 else:
  col=bpy.data.collections.new(name)
  bpy.context.scene.collection.children.link(col)
  root=bpy.data.objects.new(name,None)
  col.objects.link(root)
  root.location=(-17.5, -3 if i==6 else 9, 0.01265)
  root.rotation_euler=(0,0,-math.pi/2)
 root['source_model']='prius_hybrid'
 root['note']='Ego mesh with white obstacle body; root retains saved placement'
 for part in parts:
  obj=part.copy()
  obj.data=part.data.copy()
  col.objects.link(obj)
  obj.name=name+' / '+part.name.split(' / ',1)[-1]
  obj.parent=root
  obj.matrix_parent_inverse=Matrix.Identity(4)
  # Hatchback visual has +90deg local yaw; keep its world-facing direction.
  obj.matrix_basis=Matrix.Rotation(math.pi/2,4,'Z') @ part.matrix_basis
  if part.name=='01 Ego vehicle / Hybrid':
   obj.data.materials.clear()
   obj.data.materials.append(white)
bpy.context.view_layer.update()
for name,mat in poses.items():
 assert all(abs(mat[r][c]-bpy.data.objects[name].matrix_world[r][c])<1e-5 for r in range(4) for c in range(4)),name
assert len([o for o in bpy.data.objects if o.type=='EMPTY' and o.name.startswith('02 obstacle')])==7
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(source))
scene=bpy.context.scene
scene.camera=bpy.data.objects['Overview']
scene.render.resolution_x=1600
scene.render.resolution_y=1400
scene.render.resolution_percentage=100
scene.render.filepath=str(OUT/'overview_white_obstacles.png')
bpy.ops.render.render(write_still=True)
print('VERIFIED: 7 ego-model obstacles; saved root transforms unchanged')

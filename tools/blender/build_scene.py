"""Build a packed Blender scene from the project's Gazebo visual assets."""
import ast
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import bpy
from mathutils import Matrix, Euler, Vector

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / 'src/simulation_pkg/models'
OUT = ROOT / 'output/blender'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

def transform(values):
    v = list(values)
    return Matrix.Translation(v[:3]) @ Euler(v[3:], 'XYZ').to_matrix().to_4x4()

def pose(node):
    return transform(map(float, node.findtext('pose', '0 0 0 0 0 0').split()))

def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c

def move(obj, c):
    for old in list(obj.users_collection):
        old.objects.unlink(obj)
    c.objects.link(obj)

def material(name, color):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    m.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value = (*color, 1)
    return m

def model(name, asset, placement):
    c = collection(name)
    parent = bpy.data.objects.new(name, None)
    c.objects.link(parent)
    parent.matrix_world = transform(placement)
    parent['source_model'] = asset
    root = ET.parse(MODELS / asset / 'model.sdf').getroot().find('model')
    seen = set()
    for link in root.findall('link'):
        for visual in link.findall('visual'):
            geo = visual.find('geometry')
            mesh = geo.find('mesh')
            local = pose(root) @ pose(link) @ pose(visual)
            if mesh is not None:
                path = MODELS / mesh.findtext('uri').removeprefix('model://')
                scale = tuple(map(float, mesh.findtext('scale', '1 1 1').split()))
                key = (str(path), tuple(sum((list(row) for row in local), [])), scale)
                # The Prius SDF references the same OBJ three times by submesh.
                # Import the complete OBJ once at this transform.
                if key in seen:
                    continue
                seen.add(key)
                bpy.ops.wm.obj_import(filepath=str(path), forward_axis='Y', up_axis='Z')
                objects = list(bpy.context.selected_objects)
                local = local @ Matrix.Diagonal((*scale, 1))
            elif geo.find('cylinder') is not None:
                cyl = geo.find('cylinder')
                bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=float(cyl.findtext('radius')), depth=float(cyl.findtext('length')))
                objects = [bpy.context.object]
            elif geo.find('box') is not None:
                bpy.ops.mesh.primitive_cube_add(size=1)
                objects = [bpy.context.object]
                local = local @ Matrix.Diagonal((*map(float, geo.findtext('box/size').split()), 1))
            else:
                continue
            for obj in objects:
                move(obj, c)
                obj.name = name + ' / ' + obj.name
                imported_transform = obj.matrix_world.copy()
                obj.parent = parent
                obj.matrix_basis = local @ imported_transform
                if mesh is None:
                    color = tuple(map(float, visual.findtext('material/diffuse', '0.2 0.2 0.2 1').split()))[:3]
                    m = material(name + '/' + visual.get('name'), color)
                    bs = m.node_tree.nodes.get('Principled BSDF')
                    if visual.get('name') in ('red', 'yellow', 'green'):
                        bs.inputs['Emission Color'].default_value = (*color, 1)
                        bs.inputs['Emission Strength'].default_value = 2 if visual.get('name') == 'red' else 0.05
                    obj.data.materials.append(m)
    return parent

# Read only literal pose data, without importing the ROS/Gazebo runtime module.
source = ast.parse((ROOT/'src/simulation_pkg/simulation_pkg/lib/012_deploy_lib.py').read_text())
constants = {}
for node in source.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in ('MISSION_TRAFFIC_LIGHT_POSE', 'MISSION_OBSTACLE_SPECS'):
                constants[target.id] = ast.literal_eval(node.value)
ego_fn = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == 'driving_ego')
ego_values = {n.targets[0].id: ast.literal_eval(n.value) for n in ego_fn.body if isinstance(n, ast.Assign)}
ego_pose = [ego_values[k] for k in ('random_x','random_y','z','r','p','y')]
model('01 Ego vehicle', 'prius_hybrid', ego_pose)
for name, asset, placement in constants['MISSION_OBSTACLE_SPECS']:
    model('02 ' + name, asset, placement)
model('03 Traffic light', 'traffic', constants['MISSION_TRAFFIC_LIGHT_POSE'])

c = collection('00 Track')
world = ET.parse(ROOT/'src/simulation_pkg/worlds/track.world').getroot()
ground = world.find(".//model[@name='ground']")
size = list(map(float, ground.findtext('.//visual/geometry/plane/size').split()))
bpy.ops.mesh.primitive_plane_add(size=2)
track = bpy.context.object
track.name = 'Track / original image, Gazebo dimensions'
move(track,c)
track.matrix_world = pose(ground)
track.scale = (size[0]/2, size[1]/2, 1)
m = material('Track image', (1,1,1))
tex = m.node_tree.nodes.new('ShaderNodeTexImage')
tex.image = bpy.data.images.load(str(MODELS/'race_track/materials/textures/track.png'))
bs = m.node_tree.nodes.get('Principled BSDF')
m.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
bs.inputs['Roughness'].default_value=0.95
track.data.materials.append(m)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,-0.22))
base=bpy.context.object
base.name='Track / support slab'
base.dimensions=(size[1]+0.2,size[0]+0.2,0.4)
base.data.materials.append(material('Slab edge',(0.07,0.09,0.12)))
move(base,c)

c=collection('04 Cameras and lighting')
def camera(name, location, target, ortho=None):
    bpy.ops.object.camera_add(location=location)
    obj=bpy.context.object
    obj.name=name
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    obj.data.clip_end=500
    if ortho:
        obj.data.type='ORTHO'
        obj.data.ortho_scale=ortho
    move(obj,c)
    return obj
cam=camera('Overview', (62,-75,88),(0,0,0),82)
camera('Top view',(0,0,100),(0,0,0),66)
camera('Traffic light detail',(-9,-15,7),(5.5,-23,1.6),15)
camera('Ego vehicle detail',(11,30,7),(3.7,24.6,0.7),12)
bpy.ops.object.light_add(type='SUN',location=(0,0,35))
sun=bpy.context.object
sun.rotation_euler=(0.4,-0.5,-0.3)
sun.data.energy=2
sun.data.angle=math.radians(15)
move(sun,c)
scene=bpy.context.scene
scene.camera=cam
scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.65,0.72,0.85,1)
scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value=0.7
scene.render.engine='CYCLES'
scene.cycles.samples=24
scene.cycles.use_denoising=True
scene.render.resolution_x=1600
scene.render.resolution_y=1400
scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
scene.unit_settings.system='METRIC'
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.shading.type='MATERIAL'
bpy.ops.object.select_all(action='DESELECT')
# OBJ materials include Gazebo model:// URIs and a few relative texture paths.
for im in bpy.data.images:
    if im.source != 'FILE' or Path(im.filepath).exists():
        continue
    raw = im.filepath
    if 'model:/' in raw:
        relative = raw.split('model:/', 1)[1].lstrip('/')
        candidate = MODELS / relative
    else:
        candidate = Path(raw).parent.parent / 'materials/textures' / Path(raw).name
    if not candidate.exists():
        matches = [p for p in MODELS.rglob('*') if p.is_file() and p.name.lower() == candidate.name.lower()]
        assert matches, raw
        candidate = matches[0]
    im.filepath = str(candidate)
    im.reload()
bpy.ops.file.pack_all()
missing=[im.filepath for im in bpy.data.images if im.source=='FILE' and not im.packed_file]
assert not missing, missing
scene['Scene notes']='Static visual scene; source Gazebo geometry and mission poses. Red lamp illustrated; ROS control/physics not included.'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'nav_vla_track.blend'))
scene.render.filepath=str(OUT/'overview.png')
bpy.ops.render.render(write_still=True)
scene.camera=bpy.data.objects['Traffic light detail']
scene.render.resolution_x=1200
scene.render.resolution_y=800
scene.render.filepath=str(OUT/'traffic_detail.png')
bpy.ops.render.render(write_still=True)
print('SCENE_COMPLETE', len(bpy.data.objects), 'objects; all textures packed')

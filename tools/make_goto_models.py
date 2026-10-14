#!/usr/bin/env python3
"""Build the go-to-object fleet models (2026-10-03, weekend plan P0).

Two kinds:
  * colour cones go_cone_<colour>: the stock ``cone`` primitive in five colours
    (colour-generalisation axis: green is held out of training).
  * scanned toys / props go_<name>: Gazebo Fuel models (Google Scanned Objects
    toys, OpenRobotics props) rescaled so their LONGEST side is ``size_m`` and
    re-centred with the bottom on the ground (z = 0) — the collector teleports
    every fleet member with the same z, like the ob_* obstacles.

SmolVLA sees 512x512 -> 64 tokens (~64 px per token across, 62 deg FOV), so a
1.2 m object is ~1 token at 8 m; sizes stay 0.9-1.5 m.

Usage:  python3 tools/make_goto_models.py      (needs the Fuel cache in ~/.gz/fuel)
"""
import os
import sys
import re
import shutil
import xml.etree.ElementTree as ET

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(WS, "src", "simulation_pkg", "models")
FUEL = os.path.expanduser("~/.gz/fuel/fuel.gazebosim.org")

CONES = {"red": (0.85, 0.05, 0.05), "yellow": (0.95, 0.85, 0.05),
         "green": (0.05, 0.65, 0.10), "blue": (0.05, 0.25, 0.85),
         "white": (0.92, 0.92, 0.92)}

# name -> (fuel owner/model, longest side in metres, noun the labels use, licence)
FUEL_MODELS = {
    # Dinosaurs 1.5 -> 2.4 m on 2026-10-08 (user: "looks teddy-bear sized next to
    # the car"); they are held out of every corpus, so no training data changes.
    # Fuel names lie (thumbnails checked 2026-10-03): dino_3 = T-rex,
    # dino_4 = styracosaurus, dino_5 = triceratops, the "triceratops toy" is the
    # green Android robot figure. Directory names kept for the existing data.
    "dino_trex": ("googleresearch/dino_4", 2.4, "dinosaur", "CC-BY-4.0"),
    "dino_3": ("googleresearch/dino_3", 2.4, "dinosaur", "CC-BY-4.0"),
    "dino_5": ("googleresearch/dino_5", 2.4, "dinosaur", "CC-BY-4.0"),
    "triceratops": ("googleresearch/great_dinos_triceratops_toy", 1.3, "robot", "CC-BY-4.0"),
    "dog": ("googleresearch/dog", 1.1, "dog", "CC-BY-4.0"),
    "horse": ("googleresearch/breyer_horse_of_the_year_2015", 1.4, "horse", "CC-BY-4.0"),
    "teddy": ("googleresearch/lovable_huggable_cuddly_boutique_teddy_bear_beige", 1.2, "teddy bear", "CC-BY-4.0"),
    "hydrant": ("openrobotics/fire%20hydrant", 1.0, "fire hydrant", "CC0-1.0"),
    "chair": ("openrobotics/visitorchair", 1.1, "chair", "CC-BY-4.0"),
    "trashbin": ("openrobotics/trashbin", 1.0, "trash can", "CC-BY-4.0"),
}


def latest(path):
    vs = [v for v in os.listdir(path) if v.isdigit()]
    return os.path.join(path, max(vs, key=int))


def obj_bbox(path):
    lo = [1e9] * 3
    hi = [-1e9] * 3
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("v "):
                xyz = [float(t) for t in line.split()[1:4]]
                for i in range(3):
                    lo[i] = min(lo[i], xyz[i])
                    hi[i] = max(hi[i], xyz[i])
    return lo, hi


def dae_bbox(path):
    """Positions arrays only, node transforms ignored (fine for the props used)."""
    txt = open(path, errors="replace").read()
    lo = [1e9] * 3
    hi = [-1e9] * 3
    up = "Z_UP"
    m = re.search(r"<up_axis>(\w+)</up_axis>", txt)
    if m:
        up = m.group(1)
    unit = 1.0
    m = re.search(r'<unit[^>]*meter="([0-9.eE+-]+)"', txt)
    if m:
        unit = float(m.group(1))
    for m in re.finditer(r'<float_array[^>]*id="[^"]*position[^"]*"[^>]*>([^<]+)</float_array>',
                         txt, re.I):
        v = [float(t) * unit for t in m.group(1).split()]
        for k in range(0, len(v) - 2, 3):
            p = v[k:k + 3]
            if up == "Y_UP":
                p = [p[0], -p[2], p[1]]
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


def write_config(d, name, desc):
    open(os.path.join(d, "model.config"), "w").write(
        f"""<?xml version="1.0"?>
<model>
  <name>{name}</name>
  <version>1.0</version>
  <sdf version="1.9">model.sdf</sdf>
  <description>{desc}</description>
</model>
""")


def make_cones():
    for col, (r, g, b) in CONES.items():
        name = f"go_cone_{col}"
        d = os.path.join(MODELS, name)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "model.sdf"), "w").write(f"""<?xml version="1.0"?>
<!-- go-to-object fleet (2026-10-03): {col} cone, 1.3 m, origin on the ground -->
<sdf version="1.9">
  <model name="{name}">
    <static>true</static>
    <link name="link">
      <pose>0 0 0.65 0 0 0</pose>
      <visual name="v"><geometry><cone><radius>0.45</radius><length>1.3</length></cone></geometry>
        <material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse><specular>0.2 0.2 0.2 1</specular></material></visual>
      <collision name="c"><geometry><cylinder><radius>0.45</radius><length>1.3</length></cylinder></geometry></collision>
    </link>
  </model>
</sdf>
""")
        write_config(d, name, f"{col} traffic cone, go-to-object fleet")
        print("cone", name)


SHAPES = {   # held-out primitive shapes for the point-goal practice (2026-10-12, P4):
    # name -> (sdf geometry, rgb, noun). ~1.2 m tall, origin on the ground, r ~0.5
    "ball": ("<sphere><radius>0.55</radius></sphere>", (0.95, 0.45, 0.05), "ball"),
    "cube": ("<box><size>1.0 1.0 1.0</size></box>", (0.55, 0.10, 0.75), "cube"),
    "prism": ("<polyline><point>-0.6 -0.5</point><point>0.6 -0.5</point><point>0 0.55</point>"
              "<height>1.2</height></polyline>", (0.05, 0.75, 0.80), "triangular prism"),
}


def make_shapes():
    for key, (geom, (r, g, b), noun) in SHAPES.items():
        name = f"go_shape_{key}"
        d = os.path.join(MODELS, name)
        os.makedirs(d, exist_ok=True)
        # sphere/box are centred on their geometry; polyline extrudes from z=0
        z = 0.0 if key == "prism" else (0.55 if key == "ball" else 0.5)
        open(os.path.join(d, "model.sdf"), "w").write(f"""<?xml version="1.0"?>
<!-- point-goal practice held-out shape (2026-10-12): {noun}, origin on the ground -->
<sdf version="1.9">
  <model name="{name}">
    <static>true</static>
    <link name="link">
      <pose>0 0 {z} 0 0 0</pose>
      <visual name="v"><geometry>{geom}</geometry>
        <material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse><specular>0.3 0.3 0.3 1</specular></material></visual>
      <collision name="c"><geometry>{geom}</geometry></collision>
    </link>
  </model>
</sdf>
""")
        write_config(d, name, f"{noun}, point-goal practice held-out shape")
        print("shape", name)


def make_fuel(only=None):
    for name, (src, size, noun, lic) in FUEL_MODELS.items():
        if only and name not in only:
            continue
        owner, mname = src.split("/")
        sdir = latest(os.path.join(FUEL, owner, "models", mname))
        tree = ET.parse(os.path.join(sdir, "model.sdf"))
        uri = tree.find(".//visual//mesh/uri").text.strip()
        rel = re.sub(r"^https?://.*?/files/", "", uri)       # absolute fuel URI -> local path
        mesh = os.path.join(sdir, rel)
        lo, hi = (dae_bbox if mesh.lower().endswith(".dae") else obj_bbox)(mesh)
        ext = [hi[i] - lo[i] for i in range(3)]
        s = size / max(ext)
        cx, cy = (lo[0] + hi[0]) / 2 * s, (lo[1] + hi[1]) / 2 * s
        z0 = lo[2] * s
        gname = f"go_{name}"
        d = os.path.join(MODELS, gname)
        if os.path.exists(d):
            shutil.rmtree(d)
        for sub in ("meshes", "materials"):
            if os.path.isdir(os.path.join(sdir, sub)):
                shutil.copytree(os.path.join(sdir, sub), os.path.join(d, sub))
        bx, by, bz = (e * s for e in ext)
        open(os.path.join(d, "model.sdf"), "w").write(f"""<?xml version="1.0"?>
<!-- go-to-object fleet (2026-10-03): {noun}, from Gazebo Fuel {src} ({lic}),
     scaled x{s:.4f} so the longest side is {size} m, bottom on the ground. -->
<sdf version="1.9">
  <model name="{gname}">
    <static>true</static>
    <link name="link">
      <visual name="v">
        <pose>{-cx:.4f} {-cy:.4f} {-z0:.4f} 0 0 0</pose>
        <geometry><mesh><uri>model://{gname}/{rel}</uri><scale>{s:.5f} {s:.5f} {s:.5f}</scale></mesh></geometry>
      </visual>
      <collision name="c">
        <pose>0 0 {bz / 2:.4f} 0 0 0</pose>
        <geometry><box><size>{bx:.3f} {by:.3f} {bz:.3f}</size></box></geometry>
      </collision>
    </link>
  </model>
</sdf>
""")
        write_config(d, gname, f"{noun} ({src}), go-to-object fleet")
        open(os.path.join(d, "SOURCE.md"), "w").write(
            f"# {gname}\n\n- Source: https://fuel.gazebosim.org/1.0/{src}\n- Licence: {lic}\n"
            f"- Noun used in labels: {noun}\n- Scale: x{s:.5f} (longest side {size} m), "
            f"size {bx:.2f} x {by:.2f} x {bz:.2f} m\n")
        print(f"fuel {gname:16s} {noun:12s} ext {ext[0]:.3f} {ext[1]:.3f} {ext[2]:.3f} -> "
              f"{bx:.2f} x {by:.2f} x {bz:.2f} m (x{s:.3f})")


if __name__ == "__main__":
    # no arguments: rebuild everything; names (e.g. dino_3 dino_trex dino_5): only those
    if len(sys.argv) > 1 and sys.argv[1] == "shapes":
        make_shapes()
    elif len(sys.argv) > 1:
        make_fuel(set(sys.argv[1:]))
    else:
        make_cones()
        make_fuel()

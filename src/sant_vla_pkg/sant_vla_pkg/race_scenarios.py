"""Reproduce the saved Blender race placements in Gazebo; never animate a policy."""
import argparse
import json
import math
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET

from sant_vla_pkg.gazebo_services import pose_message, request
from sant_vla_pkg.gz_pose import list_models, query_world_pose, resolve_gz_bin


def config_path(name):
    source = Path(__file__).resolve().parents[1] / "config" / name
    if source.exists():
        return source
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("sant_vla_pkg")) / "config" / name


def load_scenarios():
    return json.loads(config_path("race_scenarios.json").read_text())


def model_directory():
    source = Path(__file__).resolve().parents[3] / "src/simulation_pkg/models"
    if source.is_dir():
        return source
    from ament_index_python.packages import get_package_share_directory
    return Path(get_package_share_directory("simulation_pkg")) / "models"


def static_model(asset, entity, signal="green"):
    """Reuse actual visual/collision geometry, remove sensors and controllers."""
    root = ET.parse(model_directory() / asset / "model.sdf").getroot()
    model = root.find("model")
    model.set("name", entity)
    static = model.find("static")
    if static is None:
        static = ET.SubElement(model, "static")
    static.text = "true"
    for parent in model.iter():
        for child in list(parent):
            if child.tag in {"sensor", "plugin"}:
                parent.remove(child)
    for uri in model.iter("uri"):
        if uri.text and uri.text.startswith("model://"):
            uri.text = str(model_directory() / uri.text.removeprefix("model://"))
    if asset == "traffic":
        for visual in model.findall(".//visual"):
            name = visual.get("name", "")
            if name not in {"red", "yellow", "green"}:
                continue
            material = visual.find("material")
            if material is None:
                material = ET.SubElement(visual, "material")
            color = {"red":"1 0 0 1", "green":"0 1 0 1", "yellow":"1 0.8 0 1"}[name]
            for tag in ("ambient", "diffuse", "emissive"):
                element = material.find(tag)
                if element is None:
                    element = ET.SubElement(material, tag)
                element.text = color if name == signal else "0.025 0.03 0.025 1"
    return root


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def reset_scenario(key, registry_path, progress=lambda text: None):
    scenarios = load_scenarios()
    scenario = scenarios[key]
    registry_path = Path(registry_path)
    # Fail before mutation if assets or the world are unavailable.
    assets = {"prius_hybrid"} | {e["model"] for e in scenario["entities"]}
    for asset in assets:
        if not (model_directory()/asset/"model.sdf").is_file():
            raise FileNotFoundError(asset)
    request("/world/default/control", "gz.msgs.WorldControl", "pause: true")
    atomic_json(registry_path, [])
    try:
        progress("이전 경기 차량을 정리합니다.")
        for name in list_models(resolve_gz_bin()):
            if (name == "ego_vehicle" or re.fullmatch(r"obstacle\d+|curve_ob\d+|race_\w+", name)
                    or name in {"traffic_light", "traffic"}):
                request("/world/default/remove", "gz.msgs.Entity", f"name: {json.dumps(name)} type: MODEL")
        # Deletion is queued by Gazebo; wait until names really disappear.
        deadline = time.monotonic()+6
        while "ego_vehicle" in list_models(resolve_gz_bin()) and time.monotonic() < deadline:
            time.sleep(0.1)
        progress("선택한 경기의 차량과 장애물을 배치합니다.")
        cache = registry_path.parent / "scene_models"
        cache.mkdir(parents=True, exist_ok=True)
        entities = [{"entity":"ego_vehicle", "model":"prius_hybrid", "pose":scenario["ego_pose"], "kind":"ego"}] + scenario["entities"]
        for entity in entities:
            name = entity["entity"]
            if entity["kind"] == "ego":
                filename = model_directory()/"prius_hybrid/model.sdf"
            else:
                filename = cache/(name+".sdf")
                ET.ElementTree(static_model(entity["model"], name)).write(filename, encoding="unicode")
            req = (f"sdf_filename: {json.dumps(str(filename))} name: {json.dumps(name)} "
                   f"allow_renaming: false pose: {{{pose_message(entity['pose'])}}}")
            request("/world/default/create", "gz.msgs.EntityFactory", req)
    finally:
        request("/world/default/control", "gz.msgs.WorldControl", "pause: false")
    expected = {e["entity"] for e in entities}
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        if expected.issubset(set(list_models(resolve_gz_bin()))):
            break
        time.sleep(0.15)
    else:
        raise RuntimeError("일부 경기 차량 생성이 확인되지 않았습니다.")
    actual = query_world_pose(resolve_gz_bin(), "ego_vehicle")
    if actual is None or math.dist(actual[:2], scenario["ego_pose"][:2]) > 0.5:
        raise RuntimeError("출발 위치 확인 실패")
    lanes = json.loads(config_path("track_paths.json").read_text())
    entries = []
    for entity in scenario["entities"]:
        if entity["kind"] != "vehicle":
            continue
        x,y = entity["pose"][:2]
        lane, distance = min(((lane, min(math.hypot(px-x,py-y) for px,py in lanes[lane])) for lane in ("lane1","lane2")), key=lambda pair:pair[1])
        entries.append({**entity, "x":x, "y":y, "yaw":entity["pose"][5],
                        "lane":lane if distance < 2.2 else "parking"})
    atomic_json(registry_path, entries)
    signals = [e for e in scenario["entities"] if e["kind"] == "signal"]
    if signals:
        # Every scenario light spawns green (static_model default).
        atomic_json(registry_path.with_name("signal.json"),
                    {"entity": signals[0]["entity"], "color": "green",
                     "x": signals[0]["pose"][0], "y": signals[0]["pose"][1],
                     "time": time.time()})
    else:
        # No light in this race: drop stale state so a leftover red from a
        # previous scenario cannot hold the car at a ghost stop line.
        Path(registry_path).with_name("signal.json").unlink(missing_ok=True)
    atomic_json(registry_path.with_name("scene.json"), {"scenario":key, "time":time.time()})
    progress(scenario["label"] + " 배치 완료 · 정지 상태")
    return scenario


SIGNAL_RGBA = {"red": (1, 0, 0), "green": (0, 1, 0), "yellow": (1, 0.8, 0)}
SIGNAL_DARK = (0.025, 0.03, 0.025)


def _visual_ids(entity):
    """Visual-entity ids of a model's balls from the live scene graph.
    visual_config only accepts numeric ids, and ids change on every
    respawn, so query fresh each time (one ruby call per button press)."""
    import subprocess
    result = subprocess.run(
        [resolve_gz_bin(), "service", "-s", "/world/default/scene/info",
         "--reqtype", "gz.msgs.Empty", "--reptype", "gz.msgs.Scene",
         "--timeout", "4000", "--req", ""],
        capture_output=True, text=True, timeout=8)
    match = re.search(r'model \{\s*name: "%s".*?(?=\nmodel \{|\Z)'
                      % re.escape(entity), result.stdout, re.S)
    if not match:
        return {}
    return {m.group(1): int(m.group(2)) for m in re.finditer(
        r'visual \{\s*name: "([^"]+)"\s*id: (\d+)', match.group(0))}


def set_signal(key, registry_path, color, progress=lambda text: None):
    """Relight the scenario's traffic light in place via visual_config
    (no respawn — only the ball materials change), and record the state
    for the signal-stop supervisor. Falls back to a rebuild+respawn when
    the visuals cannot be addressed."""
    scenario = load_scenarios()[key]
    signals = [e for e in scenario["entities"] if e["kind"] == "signal"]
    if not signals:
        raise RuntimeError("이 경기에는 신호등이 없습니다.")
    for entity in signals:
        name = entity["entity"]
        ids = _visual_ids(name) if name in list_models(resolve_gz_bin()) else {}
        if all(ball in ids for ball in SIGNAL_RGBA):
            for ball in SIGNAL_RGBA:
                r, g, b = SIGNAL_RGBA[ball] if ball == color else SIGNAL_DARK
                rgba = f"{{r: {r} g: {g} b: {b} a: 1}}"
                request("/world/default/visual_config", "gz.msgs.Visual",
                        f"id: {ids[ball]} material: {{ambient: {rgba} "
                        f"diffuse: {rgba} emissive: {rgba}}}")
        else:
            # Entity missing or scene graph unreadable: rebuild + respawn.
            cache = Path(registry_path).parent / "scene_models"
            cache.mkdir(parents=True, exist_ok=True)
            filename = cache / f"{name}_{color}.sdf"
            ET.ElementTree(static_model(entity["model"], name, color)).write(
                filename, encoding="unicode")
            if name in list_models(resolve_gz_bin()):
                request("/world/default/remove", "gz.msgs.Entity",
                        f"name: {json.dumps(name)} type: MODEL")
                deadline = time.monotonic() + 6
                while (name in list_models(resolve_gz_bin())
                       and time.monotonic() < deadline):
                    time.sleep(0.1)
            req = (f"sdf_filename: {json.dumps(str(filename))} "
                   f"name: {json.dumps(name)} allow_renaming: false "
                   f"pose: {{{pose_message(entity['pose'])}}}")
            request("/world/default/create", "gz.msgs.EntityFactory", req)
        atomic_json(Path(registry_path).with_name("signal.json"),
                    {"entity": name, "color": color,
                     "x": entity["pose"][0], "y": entity["pose"][1],
                     "time": time.time()})
    progress(("🔴 빨간불" if color == "red" else "🟢 초록불") + " 점등")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=list(load_scenarios()), required=True)
    parser.add_argument("--registry", required=True)
    args = parser.parse_args()
    reset_scenario(args.scenario, args.registry, print)


if __name__ == "__main__":
    main()

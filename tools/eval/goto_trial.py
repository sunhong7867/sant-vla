#!/usr/bin/env python3
"""Closed-loop go-to-object evaluation against a RUNNING demo stack (2026-10-03).

Stack: REMOTE_CKPT=<ckpt> ./smolvla_demo.sh --no-gui (the policy drives from
/vla/instruction). This script owns the scene: it spawns the needed object
models ONCE (entity gt_<model>, parked under the plane) and teleports them
per trial — repeated gz create/remove wedged the world before (v9 notes).

Tiers (seeded layouts from sant_vla_pkg.goto_layout, same seed = same scenes):
  T1  train objects, train phrasing                     -> right object?
  T2  lane-target layouts: "go straight" vs "follow the lane" for the SAME
      target                                            -> path differs?
  T3a held-out colour (green cone) as the target among train objects
  T3b held-out object (dinosaur) as the target among train objects
  T4  description ("an extinct animal") for the dinosaur — plain, and with
      --rewrite qwen (System-2 VLM rewrites the sentence from one camera frame)
  P2  (2026-10-12 point-goal primitive, docs/experiments/goto_object/
      20261012_1850) K=3 train objects, constant sentence "Target."; the
      harness publishes the ego-relative goal "rel:<bearing>,<dist>" of the
      target centre at 10 Hz and holds the car once inside the teacher's
      standoff. Each scene twice: arm "main" (target t0) and arm "alt"
      (target t1, P2-ctrl a). --goal-mode zero pins the channel to (0,0)
      (P2-ctrl b, main arm only).
  P3a two objects 4.6-6.4 m apart; goal = midpoint pushed one virtual
      standoff (3.5 m) beyond -> the car should stop BETWEEN them.
  P3b one object; goal = 1.5 m to its left/right -> stop beside it.
  P4s/P4b/P4l  the same three geometries with HELD-OUT primitive shapes
      (ball / cube / triangular prism) and --goal-mode vlm: the harness only
      publishes the natural-language request on /goal_request; the running
      goal_from_scene_node (Qwen2.5-VL boxes -> bearing, LiDAR -> distance)
      produces /vla_goal, "Target." and the hold. Judged like P2/P3.

A trial ends when the ego has moved and then stood still for 3 s, leaves the
plane, touches a non-target object, or times out. Success = stopped within
standoff + 1.5 m of the TARGET centre without touching anything; "chosen" =
the object the ego ended nearest to (chance = 1 / number of objects).

Usage:
  python3 tools/eval/goto_trial.py --tier T1 --n 30 --seed 20261090 --out eval_out/course/goto_eval/r50_T1.jsonl
"""
import argparse
import base64
import json
import math
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "src/simulation_pkg"))
sys.path.insert(0, str(WS / "src/sant_vla_pkg"))

from sant_vla_pkg import goto_layout as G                          # noqa: E402
from sant_vla_pkg.gz_pose import WorldPoseStream, list_models, resolve_gz_bin  # noqa: E402
from sant_vla_pkg.gz_reset import SimResetter, set_model_pose      # noqa: E402

TRACK_PATHS = WS / "src/sant_vla_pkg/config/track_paths.json"
REGISTRY = WS / "eval_out/demo/obstacles.json"
OB_Z = 0.01265
TRAIN = [m for m, v in G.FLEET.items() if v[2] == "train"]
HELD = {"T3a": ["go_cone_green"], "T3b": ["go_dino_3", "go_dino_trex", "go_dino_5"],
        "T3c": ["go_triceratops"],     # the Android robot figure (character toy)
        "T4": ["go_dino_3", "go_dino_trex", "go_dino_5"]}


class Ros:
    """One long-lived node: instruction publisher + camera grabber."""

    def __init__(self):
        import rclpy
        from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                               QoSReliabilityPolicy)
        from sensor_msgs.msg import Image
        from std_msgs.msg import String
        self.rclpy, self.String = rclpy, String
        rclpy.init()
        self.node = rclpy.create_node("goto_trial")
        qos = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.pub = self.node.create_publisher(String, "/vla/instruction", qos)
        # point-goal primitive (2026-10-12): ego-relative goal + stop gate
        self.goal_pub = self.node.create_publisher(String, "/vla_goal", qos)
        self.hold_pub = self.node.create_publisher(String, "/vla/hold", 5)
        self.req_pub = self.node.create_publisher(String, "/goal_request", 5)     # P4: goal_from_scene_node
        self.status = []
        self.node.create_subscription(String, "/goal_from_scene/status", self._status, 10)
        self.img = None
        sq = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT,
                        history=QoSHistoryPolicy.KEEP_LAST,
                        durability=QoSDurabilityPolicy.VOLATILE)
        self.node.create_subscription(Image, "/camera/image_raw", self._img, sq)
        deadline = time.time() + 8.0
        while time.time() < deadline and self.pub.get_subscription_count() < 2:
            rclpy.spin_once(self.node, timeout_sec=0.1)

    def _img(self, msg):
        self.img = msg

    def say(self, text):
        self.pub.publish(self.String(data=text))
        for _ in range(3):
            self.rclpy.spin_once(self.node, timeout_sec=0.05)

    def goal(self, text):
        self.goal_pub.publish(self.String(data=text))
        self.rclpy.spin_once(self.node, timeout_sec=0.0)

    def _status(self, msg):
        self.status.append(msg.data[:200])

    def request(self, text):
        self.req_pub.publish(self.String(data=text))
        for _ in range(3):
            self.rclpy.spin_once(self.node, timeout_sec=0.05)

    def hold(self, on):
        self.hold_pub.publish(self.String(data="hold" if on else "off"))
        for _ in range(2):
            self.rclpy.spin_once(self.node, timeout_sec=0.02)

    def frame_jpg(self, path):
        self.img = None
        t0 = time.time()
        while self.img is None and time.time() - t0 < 5.0:
            self.rclpy.spin_once(self.node, timeout_sec=0.1)
        if self.img is None:
            return None
        import numpy as np
        from PIL import Image as PImage
        m = self.img
        arr = np.frombuffer(bytes(m.data), dtype=np.uint8).reshape(m.height, m.width, -1)
        if m.encoding.lower().startswith("bgr"):
            arr = arr[:, :, ::-1]
        PImage.fromarray(arr[:, :, :3]).save(path, quality=90)
        return path


SRV = "autolab_sw@115.145.211.157"


def qwen_rewrite(img_path, sentence, mode="rewrite"):
    """System 2 on the lab server (Qwen2.5-VL-3B, server/code/course/qwen_vl.py):
    one frame + the user's sentence -> 'Go to the <name>.' The laptop's Ollama
    cannot load a VL model next to the simulator (system-memory check)."""
    import subprocess
    remote = f"~/sunhong/nav-vla/data/course/rewrite_frames/{os.path.basename(img_path)}"
    subprocess.run(["ssh", SRV, "mkdir -p ~/sunhong/nav-vla/data/course/rewrite_frames"], check=True)
    subprocess.run(["scp", "-q", img_path, f"{SRV}:{remote}"], check=True)
    t0 = time.monotonic()
    out = subprocess.run(["ssh", SRV, "cd ~/sunhong/nav-vla && PYTHONUTF8=1 CUDA_VISIBLE_DEVICES=1 HF_HUB_OFFLINE=1 "
                          f"./venv/bin/python code/course/qwen_vl.py {mode} {remote} {json.dumps(sentence)} "
                          "2>/dev/null | tail -1"], capture_output=True, text=True, timeout=600)
    try:
        r = json.loads(out.stdout.strip())
        return r["to"], r["raw"], time.monotonic() - t0
    except (json.JSONDecodeError, KeyError):
        return sentence, f"ERR {out.stdout[-80:]}", time.monotonic() - t0


def spawn_once(models):
    import xml.etree.ElementTree as ET
    from sant_vla_pkg.gazebo_services import pose_message, request
    from sant_vla_pkg.race_scenarios import static_model
    gz = resolve_gz_bin()
    present = set(list_models(gz))
    cache = WS / "eval_out/demo/scene_models"
    cache.mkdir(parents=True, exist_ok=True)
    for i, m in enumerate(models):
        name = f"gt_{m}"
        if name in present:
            continue
        f = cache / f"{name}.sdf"
        ET.ElementTree(static_model(m, name)).write(f, encoding="unicode")
        request("/world/default/create", "gz.msgs.EntityFactory",
                f"sdf_filename: {json.dumps(str(f))} name: {json.dumps(name)} "
                f"allow_renaming: false pose: {{{pose_message((60.0 + 6 * i, 70.0, -30.0, 0, 0, 0))}}}")
    deadline = time.monotonic() + 20
    want = {f"gt_{m}" for m in models}
    while time.monotonic() < deadline and not want <= set(list_models(gz)):
        time.sleep(0.3)
    return gz


def place(gz, all_models, objs):
    placed = {o["model"]: o for o in objs}
    for i, m in enumerate(all_models):
        o = placed.get(m)
        if o:
            set_model_pose(gz, f"gt_{m}", o["x"], o["y"], o["yaw"], z=OB_Z)
        else:
            set_model_pose(gz, f"gt_{m}", 60.0 + 6 * i, 70.0, 0.0, z=-30.0)
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps([{"entity": f"gt_{o['model']}", "model": o["model"],
                                     "x": o["x"], "y": o["y"], "lane": None} for o in objs]))


def make_trials(tier, n, seed, paths):
    """List of trials: dict(layout, target, mode, sentence)."""
    rng = random.Random(seed)
    out = []
    guard = 0
    SMALL = [m for m in TRAIN if G.FLEET[m][1] <= 0.8]          # cones, box, barrel, toys
    SHAPES = ["go_shape_ball", "go_shape_cube", "go_shape_prism"]  # held out, P4 (make_goto_models shapes)
    if tier.startswith("P4"):
        SMALL = SHAPES
    VSTANDOFF = G.EGO_HALF_LEN + G.STOP_GAP                       # 3.5 m, virtual point (r = 0)
    want = 2 * n if tier == "P2" else n          # P2: n scenes x (main, alt)
    while len(out) < want and guard < n * 50:
        guard += 1
        if tier in ("P2", "P4s", "P4t"):
            # same generator as S3 (K=3 at 6-10 m, >= 10 deg apart, all reachable);
            # P2: the sentence never names anything — the goal channel carries the target.
            # P4s: held-out shapes, the sentence names the shape for the VLM.
            # P4t (2026-10-15): P2's trained objects, goal from the camera only (VLM box -> bearing,
            # LiDAR -> distance); gz coordinates are used for judging, never as the policy's goal.
            L = G.sample_layout(rng, paths, SHAPES if tier == "P4s" else TRAIN, n_obj=(3, 3),
                                dist=(6.0, 10.0), min_sep_deg=10.0, all_usable=True, tries=3000)
            if L is None:
                continue
            t0, t1 = rng.sample(list(L["usable"]), 2)
            arms = (("main", t0), ("alt", t1)) if tier == "P2" else (("main", t0),)
            for arm, t in arms:
                o = L["objects"][t]
                out.append({"layout": L, "target": t, "mode": "direct",
                            "sentence": f"Go to the {o['noun']}." if tier in ("P4s", "P4t") else "Target.",
                            "goal_xy": (o["x"], o["y"]), "gate": G.standoff(o["model"]),
                            "arm": arm, "set": len(out) // 2})
            continue
        if tier in ("P3a", "P3b", "P4b", "P4l"):
            base = G.sample_layout(rng, paths, SMALL, n_obj=(2, 2), dist=(8.0, 11.0), tries=400)
            if base is None:
                continue
            e = base["ego"]
            h = e["heading"]
            beta = math.radians(rng.uniform(-10.0, 10.0))
            D = rng.uniform(8.0, 11.0)
            ux, uy = math.cos(h + beta), math.sin(h + beta)       # ego -> goal direction
            nx, ny = -uy, ux                                      # its left normal
            mx, my = e["x"] + D * ux, e["y"] + D * uy
            def obj(m, x, y):
                dx, dy = x - e["x"], y - e["y"]
                b = (math.atan2(dy, dx) - h + math.pi) % (2 * math.pi) - math.pi
                return {"model": m, "noun": G.noun(m), "x": x, "y": y,
                        "yaw": rng.uniform(-math.pi, math.pi), "r": G.FLEET[m][1],
                        "dist": math.hypot(dx, dy), "bearing": b, "present": True}
            if tier in ("P3a", "P4b"):
                sep = rng.uniform(4.6, 6.4)
                m1, m2 = rng.sample(SMALL, 2)
                o1 = obj(m1, mx + 0.5 * sep * nx, my + 0.5 * sep * ny)
                o2 = obj(m2, mx - 0.5 * sep * nx, my - 0.5 * sep * ny)
                if not (G._in_plane(o1["x"], o1["y"], 1.0) and G._in_plane(o2["x"], o2["y"], 1.0)):
                    continue
                gx, gy = mx + VSTANDOFF * ux, my + VSTANDOFF * uy
                L = {"ego": e, "objects": [o1, o2], "usable": [], "lane_target": None}
                sent = (f"Go between the {o1['noun']} and the {o2['noun']}." if tier == "P4b" else "Target.")
                out.append({"layout": L, "target": None, "mode": "direct", "sentence": sent,
                            "goal_xy": (gx, gy), "gate": VSTANDOFF, "arm": "between",
                            "mid": (mx, my), "u": (ux, uy), "half_sep": sep / 2.0})
            else:
                m1 = rng.choice(SMALL)
                o1 = obj(m1, mx, my)
                if not G._in_plane(o1["x"], o1["y"], 2.0):
                    continue
                side = "left" if len(out) % 2 == 0 else "right"
                sgn = 1.0 if side == "left" else -1.0
                gx, gy = mx + 1.5 * sgn * nx, my + 1.5 * sgn * ny
                L = {"ego": e, "objects": [o1], "usable": [], "lane_target": None}
                sent = (f"Stop to the {side} of the {o1['noun']}." if tier == "P4l" else "Target.")
                out.append({"layout": L, "target": None, "mode": "direct", "sentence": sent,
                            "goal_xy": (gx, gy), "gate": VSTANDOFF, "arm": side, "side": side})
            continue
        if tier == "T2":
            L = G.sample_lane_layout(rng, paths, TRAIN)
            if L is None:
                continue
            for mode in ("direct", "lane"):
                out.append({"layout": L, "target": 0, "mode": mode,
                            "sentence": G.render(mode, L["objects"][0]["model"], rng, template=0)[0]})
            continue
        if tier in ("S2", "S3", "S4"):
            # 2026-10-05 v2 split (same generator as collect_corpus --goto-v2):
            # K objects at 6-10 m (11 m for K=4), >= 10 deg apart, all
            # reachable; the SAME start once per object, by name
            K = int(tier[1])
            L = G.sample_layout(rng, paths, TRAIN, n_obj=(K, K), dist=(6.0, 11.0 if K == 4 else 10.0),
                                min_sep_deg=10.0, all_usable=True, tries=3000)
            if L is None:
                continue
            for t in range(K):
                out.append({"layout": L, "target": t, "mode": "direct",
                            "sentence": G.render("direct", L["objects"][t]["model"], rng)[0], "set": len(out) // K})
            continue
        if tier == "SEC":
            # 2026-10-07: the three-way direction practice, same generator as
            # collect_corpus --goto-sectors. One object per camera sector
            # (left / ahead / right) in a narrow bearing band; the SAME scene
            # three times, once per direction command. The sentence names the
            # sector and never the object.
            L = G.sample_sector_layout(rng, paths, TRAIN)
            if L is None:
                continue
            for nm in ("left", "ahead", "right"):
                out.append({"layout": L, "target": L["sectors"][nm],
                            "mode": "direct", "sector": nm,
                            "sentence": G.render_sector(nm, rng)[0],
                            "set": len(out) // 3})
            continue
        if tier == "E":
            # 2026-10-04 easy split: two train objects, one each side at
            # 14-25 deg, both reachable; the SAME scene twice with "left" /
            # "right" — does the sentence alone pick the object? chance 50 %
            L = G.sample_layout(rng, paths, TRAIN, n_obj=(2, 2), dist=(6.0, 10.0))
            if L is None or len(L["usable"]) < 2:
                continue
            b = [o["bearing"] for o in L["objects"]]
            if b[0] * b[1] > 0 or min(abs(b[0]), abs(b[1])) < math.radians(14):
                continue
            for t in (0, 1):
                side = "left" if b[t] > 0 else "right"
                out.append({"layout": L, "target": t, "mode": "direct",
                            "sentence": f"Go to the object on the {side}."})
            continue
        if tier == "T1":
            L = G.sample_layout(rng, paths, TRAIN)
            if L is None:
                continue
            t = G.pick_targets(rng, L, n=1)[0]
        else:
            held = rng.choice(HELD[tier])
            L = G.sample_layout(rng, paths, TRAIN + [held])
            if L is None:
                continue
            ts = [j for j in L["usable"] if L["objects"][j]["model"] == held]
            if not ts:
                continue
            t = ts[0]
        o = L["objects"][t]
        if tier == "T4":
            sent = f"Go to {rng.choice(G.DESCRIPTIONS[o['noun']])}."
        else:
            sent = G.render("direct", o["model"], rng, template=0)[0]
        out.append({"layout": L, "target": t, "mode": "direct", "sentence": sent})
    if tier in ("S2", "S3", "S4"):
        K = int(tier[1])
        return out[:K * max(1, n // K)]
    if tier == "SEC":
        return out[:3 * max(1, n // 3)]
    if tier == "P2":
        return out[:2 * n]            # n scenes x (main, alt)
    return out[:n] if tier not in ("T2", "E") else out[:2 * (n // 2)]


BRIDGE_LOG = WS / "eval_out/demo/bridge.log"
_HB = re.compile(r"\[(\d+\.\d+)\]\s+\[vla_bridge\].*?lat=([\d.]+)ms\s+"
                 r"underrun=([\d.]+)%\s+watchdog=(\d+)")
# Stamped on every trial row. 2026-10-08: the five-row SEC comparison could not
# be reconstructed from the repository — goto_stat_eval.sh passes POLICY_GUIDE
# through the environment and logs it nowhere, and the two w=3 runs (one of them
# served 62% of its trials unamplified because of a --guide-match regex that
# missed 15 of the 24 sector templates) were indistinguishable on disk.
CFG = {}


def serving_health(t0, t1):
    """Bridge heartbeat stats inside the trial's wall-clock window.

    The 1 Hz heartbeat carries a CUMULATIVE watchdog count, so a trial's share
    is the delta across its window. 2026-10-08: the w=6 run logged 17 watchdog
    hits and a 396 ms median inference latency against a 50-60 ms budget, and
    nothing recorded which trials they landed in — vla_bridge_node's own comment
    calls a watchdog hit "fatal to the validity of an eval run if it ever fires".
    """
    try:
        txt = BRIDGE_LOG.read_text(errors="ignore")
    except OSError:
        return None
    lat, un, wd = [], [], []
    for m in _HB.finditer(txt):
        if t0 <= float(m.group(1)) <= t1:
            lat.append(float(m.group(2)))
            un.append(float(m.group(3)))
            wd.append(int(m.group(4)))
    if not wd:
        return None
    nz = sorted(v for v in lat if v > 0)
    return {"n_hb": len(wd), "watchdog_delta": wd[-1] - wd[0],
            "underrun_max": max(un),
            "lat_p90_ms": round(nz[int(len(nz) * 0.9)]) if nz else None}


def mem_avail_g():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) / 1048576
    return 99.0


def wait_for_ram(floor=1.2, max_wait_s=900):
    """The laptop also runs the user's apps (2026-10-03: 4.7 G free, swap 80 %).
    Below the floor, pause instead of pushing the machine into a freeze; after
    max_wait_s give up — the jsonl is appended per trial, so a rerun resumes."""
    t0 = time.monotonic()
    while mem_avail_g() < floor:
        if time.monotonic() - t0 > max_wait_s:
            return False
        print(f"[ram] {mem_avail_g():.1f} G < {floor} G — waiting", flush=True)
        time.sleep(30)
    return True


def lane_dev(paths, lane, xs):
    pts = paths[lane]
    return max(min(math.hypot(px - x, py - y) for px, py in pts) for x, y in xs) if xs else None


def run_trial(ros, gz, stream, all_models, tr, paths, timeout, rewrite, img_dir, idx):
    t0_wall = time.time()
    L = tr["layout"]
    objs = L["objects"]
    ros.say("")
    time.sleep(0.8)
    place(gz, all_models, objs)
    e = L["ego"]
    for _ in range(3):
        ok, msg, _p = SimResetter().reset(e["x"], e["y"],
                                          math.atan2(math.sin(e["model_yaw"]), math.cos(e["model_yaw"])))
        if ok:
            break
        print(f"[trial {idx}] reset retry: {msg}", flush=True)
    time.sleep(1.2)
    sentence, rw = tr["sentence"], None
    img = ros.frame_jpg(str(img_dir / f"trial_{idx:03d}.jpg"))
    if rewrite and img:
        new, raw, dt = qwen_rewrite(img, sentence, "rewrite_pos" if rewrite == "qwen_pos" else "rewrite")
        rw = {"from": sentence, "to": new, "raw": raw[:60], "sec": round(dt, 1)}
        sentence = new
    goal_mode = CFG.get("goal_mode", "none")
    vlm = goal_mode == "vlm"
    goal_on = goal_mode in ("rel", "zero") and tr.get("goal_xy") is not None
    gate_fired, v_at_gate, t_gate, last_pt, vel = False, None, None, None, 0.0
    if goal_on:
        ros.goal("rel:0.0,0.0" if goal_mode == "zero" else "none")
    if vlm:
        ros.status.clear()
        ros.request(sentence)          # goal_from_scene_node drives /vla_goal, "Target.", hold
    else:
        ros.say(sentence)
    t0 = time.monotonic()
    moved, still_since, path = False, None, []
    start, anchor = None, None
    result, detail = "TIMEOUT", ""
    min_d = {o["model"]: 1e9 for o in objs}
    while time.monotonic() - t0 < timeout:
        p = stream.latest
        if p is None:
            time.sleep(0.2)
            continue
        x, y, yaw = p
        now_t = time.monotonic()
        if last_pt is not None and now_t - last_pt[2] > 0.05:
            vel = math.hypot(x - last_pt[0], y - last_pt[1]) / (now_t - last_pt[2])
        last_pt = (x, y, now_t)
        if goal_on:
            gx, gy = tr["goal_xy"]
            dxg, dyg = gx - x, gy - y
            dist_g = math.hypot(dxg, dyg)
            # motion heading = gz yaw + YAW_OFFSET (-90 deg), the frame of the training labels
            bear_g = (math.atan2(dyg, dxg) - (yaw + G.YAW_OFFSET) + math.pi) % (2 * math.pi) - math.pi
            if goal_mode == "zero":
                ros.goal("rel:0.0,0.0")
            else:
                ros.goal(f"rel:{bear_g:.4f},{dist_g:.3f}")
            # stop gate = CODE: inside the teacher's standoff -> hold (the real
            # system does this from the LiDAR distance; here from the same geometry)
            if not gate_fired and dist_g < tr["gate"]:
                gate_fired, v_at_gate, t_gate = True, round(vel, 2), round(now_t - t0, 1)
                ros.hold(True)
        if start is None:
            start = (x, y)
        if not path or math.hypot(x - path[-1][0], y - path[-1][1]) > 0.1:
            path.append((round(x, 2), round(y, 2)))
        if math.hypot(x - start[0], y - start[1]) > 0.8:
            moved = True
        for o in objs:
            d = math.hypot(o["x"] - x, o["y"] - y)
            min_d[o["model"]] = min(min_d[o["model"]], d)
        hit = [o for j, o in enumerate(objs) if j != tr["target"]
               and math.hypot(o["x"] - x, o["y"] - y) < o["r"] + 1.3]
        if hit:
            result, detail = "COLLISION", hit[0]["noun"]
            break
        if abs(x) > G.X_LIM + 3 or abs(y) > G.Y_LIM + 3:
            result, detail = "OFF_PLANE", f"{x:.1f},{y:.1f}"
            break
        # standstill = within 5 cm of an anchor that is reset whenever the car moves
        if anchor is None or math.hypot(x - anchor[0], y - anchor[1]) > 0.05:
            anchor, still_since = (x, y), None
        else:
            still_since = still_since or time.monotonic()
        if moved and still_since and time.monotonic() - still_since > 3.0:
            result = "STOPPED"
            break
        time.sleep(0.1 if (goal_on or vlm) else 0.25)
    if vlm:
        ros.request("stop")            # node: hold + clear goal + "" instruction
        time.sleep(0.3)
        ros.request("none")
        ros.hold(False)
    ros.say("")
    if goal_on:
        ros.hold(False)
        ros.goal("none")
    p = stream.latest or (0, 0, 0)
    fin = {o["model"]: round(math.hypot(o["x"] - p[0], o["y"] - p[1]), 2) for o in objs}
    chosen = min(fin, key=fin.get)
    extra = {}
    if tr["target"] is None:
        # P3 virtual-point goals: judged against the geometry, not an object
        tgt = objs[0]
        ok = strict = False
        gap = None
        touched = any(fin[o["model"]] < G.EGO_COLLIDE_LEN + o["r"] + 0.1 for o in objs)
        hx, hy = math.cos(p[2] + G.YAW_OFFSET), math.sin(p[2] + G.YAW_OFFSET)
        if tr.get("mid"):
            mx, my = tr["mid"]; ux, uy = tr["u"]
            along = (p[0] - mx) * ux + (p[1] - my) * uy
            lat = -(p[0] - mx) * uy + (p[1] - my) * ux
            crossed = max(((px - mx) * ux + (py - my) * uy) for px, py in path) >= -0.5 if path else False
            ok = (result == "STOPPED" and -1.5 <= along <= 1.5
                  and abs(lat) <= tr["half_sep"] - 1.0 and not touched)
            extra = {"along": round(along, 2), "lat": round(lat, 2), "crossed": crossed,
                     "half_sep": round(tr["half_sep"], 2)}
        elif tr.get("side"):
            o = objs[0]
            lat_obj = -(o["x"] - p[0]) * hy + (o["y"] - p[1]) * hx     # +left of the ego axis
            d_obj = fin[o["model"]]
            want = (lat_obj < -0.3) if tr["side"] == "left" else (lat_obj > 0.3)
            ok = (result == "STOPPED" and want and d_obj <= 6.5 and not touched
                  and math.hypot(tr["goal_xy"][0] - p[0], tr["goal_xy"][1] - p[1]) <= tr["gate"] + 1.5)
            extra = {"side": tr["side"], "lat_obj": round(lat_obj, 2), "d_obj": d_obj}
    else:
        tgt = objs[tr["target"]]
        ok = (result == "STOPPED" and fin[tgt["model"]] <= G.standoff(tgt["model"]) + 1.5)
    # bumper contact with the target (collision front 1.904 m + footprint): still
    # a "reached it", reported separately. EGO_COLLIDE_LEN, not EGO_HALF_LEN -
    # contact is decided by the collision box, measured 2026-10-12.
    if tr["target"] is not None:
        touched = fin[tgt["model"]] < G.EGO_COLLIDE_LEN + tgt["r"] + 0.1
    # 2026-10-05 strict success: the RIGHT object (ended nearest it), stopped
    # with a bumper gap of 0.6-1.8 m, no contact. The loose `ok` above counted
    # stops beside another object (T1 73 % vs right object 33 %).
    # 2026-10-12: gap now measures to the COLLISION front (1.904 m), not the
    # 2.3 m teacher constant, so it is the real clearance. Every gap logged
    # before this date reads 0.396 m low - add it back when comparing.
    # Note the window: the teacher's demonstrated clearance is
    # EGO_HALF_LEN + STOP_GAP - EGO_COLLIDE_LEN = 1.596 m, so 0.6-1.8 is
    # asymmetric around the demonstration. Left as-is to keep the criterion
    # identical across runs; re-centring it is a separate decision.
    if tr["target"] is not None:
        gap = fin[tgt["model"]] - G.EGO_COLLIDE_LEN - tgt["r"]
        strict = (result == "STOPPED" and chosen == tgt["model"] and 0.6 <= gap <= 1.8)
    row = {"sentence": tr["sentence"], "sent_used": sentence, "rewrite": rw, "mode": tr["mode"],
           "target": tgt["noun"], "target_model": tgt["model"], "n_obj": len(objs),
           "result": result, "detail": detail, "success": ok, "touched_target": touched,
           "success_strict": strict, "gap": (round(gap, 2) if gap is not None else None), "set": tr.get("set"),
           "tier": CFG.get("tier"), "arm": tr.get("arm"), "goal_mode": goal_mode,
           "goal_xy": tr.get("goal_xy"), "gate_m": tr.get("gate"), "gate_fired": gate_fired,
           "v_at_gate": v_at_gate, "t_gate_s": t_gate,
           "fin_goal_d": (round(math.hypot(tr["goal_xy"][0] - p[0], tr["goal_xy"][1] - p[1]), 2)
                          if tr.get("goal_xy") else None),
           "fin_pose": [round(p[0], 2), round(p[1], 2), round(p[2], 3)],
           "node_status": list(ros.status) if vlm else None, **extra,
           "chosen": next(o["noun"] for o in objs if o["model"] == chosen),
           "chosen_right": chosen == tgt["model"], "final_d": fin,
           "min_d": {k: round(v, 2) for k, v in min_d.items()},
           "elapsed_s": round(time.monotonic() - t0, 1), "moved": moved,
           "cfg": CFG, "t_start": round(t0_wall, 3),
           "serving": serving_health(t0_wall, time.time()),
           "ego": L["ego"], "objects": [{k: o[k] for k in ("model", "noun", "x", "y")} for o in objs],
           "path": path[::3]}
    if tr["mode"] == "lane" or L.get("lane_target") is not None:
        row["lane_dev_max"] = round(lane_dev(paths, L["ego"]["lane"], path), 2) if L["ego"]["lane"] else None
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", required=True, choices=["T1", "T2", "T3a", "T3b", "T3c", "T4", "E", "S2", "S3", "S4", "SEC",
                                                        "P2", "P3a", "P3b", "P4s", "P4t", "P4b", "P4l"])
    ap.add_argument("--goal-mode", default="none", choices=["none", "rel", "zero", "vlm"],
                    help="rel: publish the ego-relative goal of the trial's goal point at 10 Hz on "
                         "/vla_goal and hold inside the standoff (point-goal primitive); zero: pin the "
                         "channel to (0,0) — the P2-ctrl (b) floor")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261090)
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--rewrite", default=None, choices=[None, "qwen", "qwen_pos"],
                    help="qwen: System 2 -> 'Go to the <name>.'; qwen_pos (r52+): System 2 -> "
                         "'Go to the object on the left.' (server/code/course/qwen_vl.py rewrite_pos)")
    ap.add_argument("--words", default="noun", choices=["noun", "pos"],
                    help="pos: replace each sentence by the ORACLE positional words from the layout "
                         "(relabel_goto_pos.phrase) — the policy alone, no System 2")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    CFG.update({"tier": a.tier, "n": a.n, "seed": a.seed, "words": a.words,
                "rewrite": a.rewrite, "goal_mode": a.goal_mode,
                "ckpt": os.environ.get("REMOTE_CKPT", ""),
                "policy_guide": os.environ.get("POLICY_GUIDE", "1.0"),
                "tag": os.environ.get("TAG", "")})
    paths = json.loads(TRACK_PATHS.read_text())
    trials = make_trials(a.tier, a.n, a.seed + {"T1": 0, "T2": 1, "T3a": 2, "T3b": 3, "T3c": 5, "T4": 4, "E": 6, "S2": 7, "S3": 8, "S4": 9, "SEC": 10,
                                                "P2": 11, "P3a": 12, "P3b": 13,
                                                "P4s": 14, "P4t": 11, "P4b": 15, "P4l": 16}[a.tier], paths)
    if a.tier == "P2" and a.goal_mode == "zero":
        trials = [t for t in trials if t["arm"] == "main"]       # floor: same scenes, main arm only
    if a.tier.startswith("P") and a.goal_mode == "none":
        print("P tiers need --goal-mode rel (or zero); P4 tiers need --goal-mode vlm", file=sys.stderr)
        return 2
    if a.tier.startswith("P4") != (a.goal_mode == "vlm"):
        print("P4 tiers require --goal-mode vlm and vice versa", file=sys.stderr)
        return 2
    # SEC sentences are already direction words — do not rewrite them
    if a.words == "pos" and a.tier not in ("E", "SEC"):
        sys.path.insert(0, str(WS / "server/code/course"))
        from relabel_goto_pos import phrase
        for tr in trials:
            en = phrase(tr["layout"]["objects"], tr["target"])[0]
            tr["sentence"] = (f"Follow the lane to {en}." if tr["mode"] == "lane" else f"Go to {en}.")
    all_models = sorted({o["model"] for t in trials for o in t["layout"]["objects"]})
    gz = spawn_once(all_models)
    ros = Ros()
    stream = WorldPoseStream(gz, "ego_vehicle").start()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img_dir = out.parent / (out.stem + "_frames")
    img_dir.mkdir(exist_ok=True)
    done = 0
    if out.exists():
        done = sum(1 for _ in open(out))
    with open(out, "a") as f:
        for i, tr in enumerate(trials):
            if i < done:
                continue
            if not wait_for_ram():
                print("[ram] still low after 15 min — stopping (rerun resumes)", flush=True)
                break
            row = run_trial(ros, gz, stream, all_models, tr, paths, a.timeout,
                            a.rewrite, img_dir, i)
            row["i"] = i
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            print(f"[{a.tier} {i + 1}/{len(trials)}] {row['sentence'][:40]:40s} -> {row['result']:9s} "
                  f"target {row['target']:12s} chosen {row['chosen']:12s} "
                  f"{'OK' if row['success'] else '--'}"
                  + (f" lane_dev {row.get('lane_dev_max')}" if 'lane_dev_max' in row else "")
                  + (f" rw->{row['rewrite']['to']}" if row["rewrite"] else ""), flush=True)
    place(gz, all_models, [])
    return 0


if __name__ == "__main__":
    sys.exit(main())

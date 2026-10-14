#!/usr/bin/env python3
"""One closed-loop obstacle-avoidance trial against a RUNNING demo stack.

Spawns blocker cars at the requested lane:frac spots, teleports the ego to a
start pose, publishes the cruise instruction, and watches gz ground-truth
poses until every obstacle is passed / hit / timed out. Prints a JSON verdict
plus the supervisor's "avoid:" decision log for the trial window.

Usage (stack must be up: ./smolvla_demo.sh):
    python3 tools/eval/avoidance_trial.py --obstacles lane2:0.25
    python3 tools/eval/avoidance_trial.py --obstacles lane2:0.30,lane1:0.38 \
        --start-frac 0.18 --timeout 180
    python3 tools/eval/avoidance_trial.py --cleanup   # remove trial cars only

Frac is position along the lane path (order = driving direction).
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "src/simulation_pkg"))
sys.path.insert(0, str(WS / "src/sant_vla_pkg"))

from sant_vla_pkg.gz_pose import WorldPoseStream, resolve_gz_bin   # noqa: E402
from sant_vla_pkg.gz_reset import SimResetter                      # noqa: E402

# gz body yaw sits +90 deg from the travel direction (measured 2026-08-28;
# navigator uses yaw_offset=-pi/2 for the inverse). Teleports must add it or
# the ego starts sideways and leaves the track within seconds.
BODY_YAW_OFFSET = math.pi / 2.0

TRACK_PATHS = WS / "src/sant_vla_pkg/config/track_paths.json"
REGISTRY = WS / "eval_out/demo/obstacles.json"
CHAT_LOG = WS / "eval_out/demo/chat_gui.log"
LANE_WORDS = {"lane1": "the inner lane", "lane2": "the outer lane"}
MODELS = ["hatchback_green", "hatchback_red", "hatchback_blue",
          "hatchback_yellow"]
PASS_RADIUS = 8.0        # an encounter opens under this distance...
COLLIDE_D = 2.0          # ...and counts as a hit under this one (car-vs-car legacy)
# Geometric hit test for the multi-object fleet (2026-09-23): centre distance
# alone misread "drove into the mannequin" as a clean 2.16 m stop. Obstacle
# half-extents (metres); cars keep the legacy centre-distance rule.
EGO_HALF_LEN, EGO_HALF_WID = 2.4, 0.95
# (half_along, half_across) in the lane frame; obstacles sit parallel to the lane.
OBJ_EXTENT = {"ob_box": (0.85, 0.85), "ob_barrel": (0.5, 0.5), "ob_cone": (0.6, 0.6),
              "ob_barrier": (0.3, 1.2), "ob_person": (0.3, 0.3), "cone": (0.4, 0.4)}
CAR_EXTENT = (2.2, 0.9)           # hatchback / prius as an obstacle
BODY_TO_TRAVEL = -math.pi / 2.0   # gz body yaw -> travel heading


def hit_geometric(ego, spec):
    """True when the ego body rectangle overlaps the obstacle's footprint
    (both taken parallel to the ego's travel direction). For cars this is the
    r10 head-on rule: centre gap < 4.6 m along the lane = bumper contact —
    r28 baseline "stopped" at 3.6-3.9 m centre, i.e. inside the other car."""
    model = spec["model"]
    ext = OBJ_EXTENT.get(model)
    if ext is None:
        ext = CAR_EXTENT if (model.startswith("hatchback") or model.startswith("prius")) else None
    if ext is None:
        return False
    x, y, yaw = ego
    h = yaw + BODY_TO_TRAVEL
    dx, dy = spec["x"] - x, spec["y"] - y
    along = dx * math.cos(h) + dy * math.sin(h)
    across = -dx * math.sin(h) + dy * math.cos(h)
    return abs(along) < EGO_HALF_LEN + ext[0] and abs(across) < EGO_HALF_WID + ext[1]
STUCK_S = 20.0           # standstill this long near an obstacle = stuck

# Oracle situation phrase (2026-09-30, stage 1 of the YOLO plan): the harness
# plays a PERFECT perception module — it appends the phrase a situation-
# prompted checkpoint (r40+, train_reasoning.py --situation-prompt) was
# trained on, computed from coordinates with the label rules of
# label_reasoning.obstacle_phase (OB_NEAR_M 14, passing while in the other
# lane until 2 m past, other-lane obstacles = clear). Strings must match
# reasoning_vla/reasoning_dataset.py SITUATION_*. Serve WITHOUT
# --situation-from-reasoning so the phrase is not appended twice.
SIT = {"clear": "Situation: road clear.",
       "ahead": "Situation: obstacle ahead in our lane.",
       "passing": "Situation: passing the obstacle.",
       "past": "Situation: past the obstacle."}
OB_NEAR_M = 14.0
LANE_HALF_M = 1.576      # half the 3.152 m lane spacing


class InstructionPublisher:
    """One long-lived publisher for mid-trial phrase switches (pub_instruction
    re-creates a node and waits up to 10 s for 3 readers — too slow here)."""

    def __init__(self):
        import rclpy
        from rclpy.qos import (QoSDurabilityPolicy, QoSProfile,
                               QoSReliabilityPolicy)
        from std_msgs.msg import String as StringMsg
        self._rclpy, self._msg = rclpy, StringMsg
        rclpy.init()
        self.node = rclpy.create_node("avoidance_trial_oracle")
        qos = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.pub = self.node.create_publisher(StringMsg, "/vla/instruction", qos)
        deadline = time.time() + 5.0
        while time.time() < deadline and self.pub.get_subscription_count() < 2:
            rclpy.spin_once(self.node, timeout_sec=0.1)

    def publish(self, text):
        self.pub.publish(self._msg(data=text))
        self._rclpy.spin_once(self.node, timeout_sec=0.05)

    def close(self):
        self.node.destroy_node()
        self._rclpy.shutdown()


def lane_pose(paths, lane, frac):
    pts = paths[lane]
    i = max(0, min(len(pts) - 1, int(frac * len(pts))))
    x, y = pts[i]
    nx, ny = pts[(i + 1) % len(pts)]
    return x, y, math.atan2(ny - y, nx - x)


def pub_instruction(text):
    # Short-lived `ros2 topic pub` publishers lost messages twice (T1, T8):
    # whichever subscriber has not finished discovery silently misses the
    # publish. So: rclpy publisher, wait for the bridge+GUI to match,
    # transient_local durability for the bridge's durable reader, and
    # repeat the message a few times before tearing down.
    import rclpy
    from rclpy.qos import (QoSDurabilityPolicy, QoSProfile,
                           QoSReliabilityPolicy)
    from std_msgs.msg import String as StringMsg
    rclpy.init()
    node = rclpy.create_node("avoidance_trial_pub")
    qos = QoSProfile(
        depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
        durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
    pub = node.create_publisher(StringMsg, "/vla/instruction", qos)
    # 3 readers on this topic: the bridge's dual-QoS pair + the chat GUI.
    # Waiting for only 2 let the bridge match while the GUI still missed
    # the message (T9: car drove, supervisor never engaged).
    deadline = time.time() + 10.0
    while (time.time() < deadline
           and pub.get_subscription_count() < 3):
        rclpy.spin_once(node, timeout_sec=0.1)
    matched = pub.get_subscription_count()
    # Publish exactly ONCE: a repeat 0.3 s later overrode the supervisor's
    # avoidance switch with the original sentence (T11 state corruption).
    pub.publish(StringMsg(data=text))
    rclpy.spin_once(node, timeout_sec=0.3)
    time.sleep(0.7)
    node.destroy_node()
    rclpy.shutdown()
    if matched < 2:
        print(f"warning: instruction published with only {matched} "
              f"matched subscriber(s)", flush=True)


def log_offset():
    try:
        return CHAT_LOG.stat().st_size
    except OSError:
        return 0


def avoid_log_since(offset):
    try:
        with open(CHAT_LOG, encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            return [ln.strip() for ln in f
                    if "avoid:" in ln or "장애물" in ln]
    except OSError:
        return []


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--obstacles", default="lane2:0.25",
                    help="comma list of lane:frac, e.g. lane2:0.30,lane1:0.38")
    ap.add_argument("--start-frac", type=float, default=None,
                    help="ego start along its lane (default: first obstacle "
                         "frac - 0.06)")
    ap.add_argument("--start-lane", default="lane2",
                    choices=["lane1", "lane2"])
    ap.add_argument("--speed", default="slowly")
    ap.add_argument("--timeout", type=float, default=150.0)
    ap.add_argument("--oracle-situation", action="store_true",
                    help="append the coordinate-oracle situation phrase to the "
                         "instruction and republish it on every phase change "
                         "(situation-prompted checkpoints only)")
    ap.add_argument("--models", default=None,
                    help="comma list of simulation_pkg models, one per "
                         "obstacle in order (default: hatchback colours). "
                         "Held-out object test: e.g. --models ob_person")
    ap.add_argument("--no-supervisor", action="store_true",
                    help="policy-native avoidance: do not wait for the chat "
                         "GUI's 'avoid:' log line and never republish the "
                         "sentence (a repeat overrides a live lane switch)")
    ap.add_argument("--cleanup", action="store_true",
                    help="remove trial obstacles and exit")
    args = ap.parse_args()
    models = ([m.strip() for m in args.models.split(",") if m.strip()]
              if args.models else MODELS)

    from simulation_pkg import basic

    # Clear every previously registered blocker (demo trio included) so the
    # trial owns the scene, then this trial's registry is the truth.
    old = []
    if REGISTRY.is_file():
        try:
            old = json.loads(REGISTRY.read_text())
        except json.JSONDecodeError:
            pass
    for e in old:
        basic.remove_model(e["entity"])
    for i in range(1, 7):
        basic.remove_model(f"trial_ob{i}")
    if args.cleanup:
        REGISTRY.write_text("[]")
        print("cleaned up")
        return

    paths = json.loads(TRACK_PATHS.read_text())
    specs = []
    for i, part in enumerate([p for p in args.obstacles.split(",") if p]):
        lane, frac = part.split(":")
        x, y, yaw = lane_pose(paths, lane, float(frac))
        specs.append({"entity": f"trial_ob{i+1}",
                      "model": models[i % len(models)],
                      "lane": lane, "frac": float(frac),
                      "x": x, "y": y, "yaw": yaw})

    pub_instruction("")               # silence the VLA before moving anything
    time.sleep(1.0)
    # Static spawn via race_scenarios.static_model (sensors, plugins and the
    # camera/lidar mount links stripped): prius_hybrid as an obstacle would
    # otherwise bring its own camera topics up next to the ego's (2026-09-23).
    import xml.etree.ElementTree as ET
    from sant_vla_pkg.gazebo_services import pose_message, request
    from sant_vla_pkg.race_scenarios import obstacle_body_yaw, static_model
    cache = REGISTRY.parent / "scene_models"
    cache.mkdir(parents=True, exist_ok=True)
    for s in specs:
        if s["model"] == "none":
            # empty-lane control (2026-10-01): a virtual obstacle — nothing is
            # spawned, it only marks the spot for the trace and the "passed" end
            continue
        f = cache / f"{s['entity']}.sdf"
        ET.ElementTree(static_model(s["model"], s["entity"])).write(f, encoding="unicode")
        pose = (s["x"], s["y"], 0.01265, 0.0, 0.0, obstacle_body_yaw(s["model"], s["yaw"]))
        request("/world/default/create", "gz.msgs.EntityFactory",
                f"sdf_filename: {json.dumps(str(f))} name: {json.dumps(s['entity'])} "
                f"allow_renaming: false pose: {{{pose_message(pose)}}}")
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(
        [{"entity": s["entity"], "model": s["model"], "x": s["x"],
          "y": s["y"], "lane": s["lane"]} for s in specs], indent=1))

    start_frac = (args.start_frac if args.start_frac is not None
                  else max(0.0, min(s["frac"] for s in specs) - 0.06))
    sx, sy, syaw = lane_pose(paths, args.start_lane, start_frac)
    ok, msg, _ = SimResetter().reset(sx, sy, syaw + BODY_YAW_OFFSET)
    if not ok:
        # verify tolerance trips on suspension settle; warn but drive on.
        print(f"warning: reset verify: {msg}", flush=True)
    time.sleep(1.0)

    offset = log_offset()
    sentence = f"Start driving in {LANE_WORDS[args.start_lane]}, {args.speed}."
    pub_instruction(f"{sentence} {SIT['clear']}" if args.oracle_situation else sentence)
    print(f"trial: {args.obstacles} start={args.start_lane}@{start_frac:.2f}"
          f" '{sentence}'", flush=True)
    # Verify the SUPERVISOR engaged (it logs an "avoid:" snapshot on its
    # first cruise tick); if the GUI missed the publish, resend.
    for attempt in range(0 if args.no_supervisor else 4):
        time.sleep(3.0)
        if any("avoid:" in ln for ln in avoid_log_since(offset)):
            break
        print(f"supervisor silent, republishing ({attempt+1})", flush=True)
        pub_instruction(sentence)

    gz = resolve_gz_bin()
    stream = WorldPoseStream(gz, "ego_vehicle").start()
    lane_pts = {ln: paths[ln] for ln in ("lane1", "lane2")}

    def off_track(x, y):
        return min(math.hypot(px - x, py - y)
                   for ln in lane_pts for px, py in lane_pts[ln]) > 4.0

    state = {s["entity"]: {"phase": "far", "min_d": 1e9, "lat_at_min": None} for s in specs}
    own_pts = paths[args.start_lane]
    def lateral_off(x, y):
        """signed offset from the ego's own lane polyline (+ = left of travel)."""
        i = min(range(len(own_pts)), key=lambda k: (own_pts[k][0] - x) ** 2 + (own_pts[k][1] - y) ** 2)
        px, py = own_pts[i]; nx, ny = own_pts[(i + 1) % len(own_pts)]
        h = math.atan2(ny - py, nx - px)
        return -math.sin(h) * (x - px) + math.cos(h) * (y - py)
    t0 = time.monotonic()
    # trajectory trace (2026-09-30): [wall time, dist to first obstacle,
    # signed lane offset] every loop tick — the report only kept the offset
    # at closest approach, which cannot tell a stalled swerve from a swerve
    # that went out and came back. Wall time lines up with the server's
    # situation log ("t").
    trace = []
    oracle = None
    if args.oracle_situation:
        oracle = InstructionPublisher()
        n_own = len(own_pts)
        spacing = math.hypot(own_pts[1][0] - own_pts[0][0], own_pts[1][1] - own_pts[0][1])
        def nearest_idx(x, y):
            return min(range(n_own), key=lambda k: (own_pts[k][0] - x) ** 2 + (own_pts[k][1] - y) ** 2)
        ob0 = specs[0]
        # 빈 차선 조건(model none)은 가상 지점만 있고 물체가 없다 → 항상 clear (2026-10-02 r41or 빈 차선 버그)
        ob_ours = ob0["lane"] == args.start_lane and ob0["model"] != "none"
        ob_idx = nearest_idx(ob0["x"], ob0["y"])
        phase = "clear"
    last_pose, last_move_t = None, time.monotonic()
    result, detail = "TIMEOUT", ""
    while time.monotonic() - t0 < args.timeout:
        pose = stream.latest
        if pose is None:
            time.sleep(0.3)
            continue
        x, y, _ = pose
        now = time.monotonic()
        if last_pose is None or math.hypot(x - last_pose[0],
                                           y - last_pose[1]) > 0.05:
            last_move_t = now
        last_pose = (x, y)
        lat_now = lateral_off(x, y)
        if oracle is not None:
            # label_reasoning.obstacle_phase on coordinates
            arc = ((ob_idx - nearest_idx(x, y) + n_own // 2) % n_own - n_own // 2) * spacing
            in_other = abs(lat_now) > LANE_HALF_M
            if not ob_ours:
                new_phase = "clear"
            elif in_other:
                new_phase = "passing" if arc > -2.0 else "past"
            elif 0.0 < arc <= OB_NEAR_M:
                new_phase = "ahead"
            else:
                new_phase = "clear"
            if new_phase != phase:
                phase = new_phase
                oracle.publish(f"{sentence} {SIT[phase]}")
                print(f"oracle: {phase} (arc {arc:.1f} m, lat {lat_now:+.2f})", flush=True)
        trace.append([round(time.time(), 2),
                      round(math.hypot(specs[0]["x"] - x, specs[0]["y"] - y), 2),
                      round(lat_now, 2)]
                     + ([phase] if oracle is not None else [])
                     # TRACE_FRAC=1 (startoff_probe, 2026-10-02): own-lane frac last, so a
                     # whole-lap run can be read by track position, not by distance to one anchor
                     + ([round(min(range(len(own_pts)), key=lambda k: (own_pts[k][0] - x) ** 2
                                   + (own_pts[k][1] - y) ** 2) / len(own_pts), 4)]
                        if os.environ.get("TRACE_FRAC") == "1" else []))
        near_any = False
        for s in specs:
            st = state[s["entity"]]
            d = math.hypot(s["x"] - x, s["y"] - y)
            if d < st["min_d"]:
                st["min_d"] = d
                st["lat_at_min"] = round(lateral_off(x, y), 2)   # how far it had swerved
            if d < PASS_RADIUS:
                near_any = True
                if st["phase"] == "far":
                    st["phase"] = "near"
            elif st["phase"] == "near":
                st["phase"] = "passed"
            # centre-distance rule only for obstacles without a known footprint:
            # applied to everything it stopped clean passes (2026-10-01: r41
            # passed a mannequin 1.94 m to the side, centre gap 1.96 m < 2.0)
            known = (s["model"] in OBJ_EXTENT or s["model"].startswith("hatchback")
                     or s["model"].startswith("prius"))
            if s["model"] != "none" and ((not known and d < COLLIDE_D) or hit_geometric(pose, s)):
                result, detail = "COLLISION", f"{s['entity']} d={d:.2f}"
                break
        if result == "COLLISION":
            break
        if off_track(x, y):
            result, detail = "OFF_TRACK", f"x={x:.1f} y={y:.1f}"
            break
        if near_any and now - last_move_t > STUCK_S:
            result, detail = "STUCK", "standstill near an obstacle"
            break
        if all(st["phase"] == "passed" for st in state.values()):
            result = "SUCCESS"
            break
        time.sleep(0.35)

    if oracle is not None:
        oracle.close()
    pub_instruction("")
    for s in [s for s in specs if s["model"] != "none"]:
        # a wedged gz service must not swallow the report and TRACE below
        # (2026-09-30: a passed trial was lost this way)
        try:
            basic.remove_model(s["entity"])
        except RuntimeError as e:
            print(f"warning: cleanup failed ({e}) — gz service likely wedged", flush=True)
    REGISTRY.write_text("[]")
    report = {
        "result": result, "detail": detail,
        "elapsed_s": round(time.monotonic() - t0, 1),
        "obstacles": [{"entity": s["entity"], "lane": s["lane"],
                       "frac": s["frac"],
                       "phase": state[s["entity"]]["phase"],
                       "min_d": round(state[s["entity"]]["min_d"], 2),
                       "lat_at_min": state[s["entity"]]["lat_at_min"]}
                      for s in specs],
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("TRACE " + json.dumps(trace))
    print("--- supervisor log ---")
    for ln in avoid_log_since(offset):
        print(ln)


if __name__ == "__main__":
    main()

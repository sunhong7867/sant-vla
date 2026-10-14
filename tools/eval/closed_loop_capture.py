#!/usr/bin/env python3
"""Closed-loop capture against a RUNNING demo stack (2026-09-29).

Resets a race scenario, sends one instruction, and records at 10 Hz what the
policy actually saw and said: camera frame (jpg), ground-truth ego pose, the
state vector exactly as vla_bridge builds it (v, yaw_rate, bicycle steer
proxy, standstill seconds), and the latest /vla/preview chunk (the model's
fresh prediction, before any bridge shaping). Stops the car at the end.

Offline, the frames can be fed back to the checkpoint with any state or
instruction to tell train/serve mismatch from a model that never learned the
situation (docs/experiments/log/20260929_*_closed-loop-avoid-failure.md).

    python3 tools/eval/closed_loop_capture.py --out eval_out/course/capture/r37_box_1
    python3 tools/eval/closed_loop_capture.py --scenario lecture --timeout 40 \\
        --instruction "Start driving in the outer lane, at a normal speed." --out ...
"""
import argparse
import json
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from PIL import Image as PILImage
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy, qos_profile_sensor_data)
from sensor_msgs.msg import Image
from std_msgs.msg import String

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "src/sant_vla_pkg"))
from sant_vla_pkg.gz_pose import WorldPoseStream, resolve_gz_bin   # noqa: E402
from sant_vla_pkg.race_scenarios import load_scenarios, reset_scenario  # noqa: E402

SIM_WHEEL_BASE = 2.86          # vla_bridge_node / route_oracle
YAW_OFFSET = -math.pi / 2      # gz body yaw -> travel heading
STANDSTILL_CAP = 3.5           # smolvla_demo.sh -p standstill_cap:=3.5


def lateral_end(actions):
    """Ego-frame lateral position after integrating the chunk's SE(2) deltas."""
    x = y = yaw = 0.0
    for dx, dy, dyaw in actions:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return y


class Capture(Node):
    def __init__(self):
        super().__init__("closed_loop_capture")
        self.lock = threading.Lock()
        self.img = None
        self.v = self.w = 0.0
        self.still_s, self.still_t = 0.0, None
        self.preview = None
        self.preview_t = 0.0
        self.create_subscription(Image, "/camera/image_raw", self._img, qos_profile_sensor_data)
        self.create_subscription(Odometry, "/odom", self._odom, qos_profile_sensor_data)
        self.create_subscription(String, "/vla/preview", self._prev, 5)
        self.bridge_task = None
        self.create_subscription(String, "/vla/status", self._status, 5)
        qos = QoSProfile(history=QoSHistoryPolicy.KEEP_LAST, depth=1,
                         reliability=QoSReliabilityPolicy.RELIABLE,
                         durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        self.instr_pub = self.create_publisher(String, "/vla/instruction", qos)

    def _img(self, msg):
        with self.lock:
            self.img = msg

    def _odom(self, msg):
        v, w = msg.twist.twist.linear.x, msg.twist.twist.angular.z
        now = time.monotonic()
        with self.lock:
            if abs(v) < 0.15:
                dt = now - self.still_t if self.still_t else 0.0
                self.still_s += min(dt, 0.5)
            else:
                self.still_s = 0.0
            self.still_t = now
            self.v, self.w = v, w

    def _status(self, msg):
        try:
            self.bridge_task = json.loads(msg.data).get("task")
        except (json.JSONDecodeError, AttributeError):
            pass

    def _prev(self, msg):
        try:
            acts = json.loads(msg.data).get("actions") or []
        except (json.JSONDecodeError, AttributeError):
            return
        if acts:
            with self.lock:
                self.preview = acts
                self.preview_t = time.monotonic()

    def state(self):
        with self.lock:
            v, w = self.v, self.w
            steer = math.atan2(w * SIM_WHEEL_BASE, v) if abs(v) > 1e-3 else 0.0
            return [v, w, steer, min(STANDSTILL_CAP, self.still_s)]

    def frame_rgb(self):
        with self.lock:
            m = self.img
        if m is None:
            return None
        buf = np.frombuffer(m.data, dtype=np.uint8)
        if m.encoding in ("rgb8", "bgr8"):
            arr = buf.reshape(m.height, m.step // 3, 3)[:, :m.width]
            return arr[:, :, ::-1] if m.encoding == "bgr8" else arr
        if m.encoding in ("rgba8", "bgra8"):
            arr = buf.reshape(m.height, m.step // 4, 4)[:, :m.width, :3]
            return arr[:, :, ::-1] if m.encoding == "bgra8" else arr
        raise RuntimeError(f"unsupported encoding {m.encoding}")

    def send(self, text, want_subs=2, wait_s=20.0, tries=3):
        """Publish once the bridge's subscriptions match (skill §7), then
        confirm on /vla/status that the bridge took it; resend if not.
        (2026-09-29: a publish with 0 matched subscribers was silently lost
        and a whole capture ran on the previous instruction.)"""
        t0 = time.monotonic()
        while self.instr_pub.get_subscription_count() < want_subs and time.monotonic() - t0 < wait_s:
            time.sleep(0.1)
        for _ in range(tries):
            self.instr_pub.publish(String(data=text))
            t1 = time.monotonic()
            while time.monotonic() - t1 < 3.0:
                if self.bridge_task == text:
                    return True
                time.sleep(0.1)
        print(f"[capture] WARNING bridge task is {self.bridge_task!r}, wanted {text!r}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--scenario", default="lecture")
    ap.add_argument("--instruction", default="Start driving in the outer lane, at a normal speed.")
    ap.add_argument("--timeout", type=float, default=45.0)
    ap.add_argument("--rate", type=float, default=10.0)
    a = ap.parse_args()

    scen = load_scenarios()[a.scenario]
    obs = [e for e in scen.get("entities", [])]
    out = Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)

    rclpy.init()
    node = Capture()
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()
    stream = WorldPoseStream(resolve_gz_bin(), "ego_vehicle")
    stream.start()

    node.send("")                              # stop whatever is running
    time.sleep(1.0)
    print(f"[capture] reset scenario {a.scenario}")
    reset_scenario(a.scenario, str(WS / "eval_out/demo/obstacles.json"))
    time.sleep(2.0)
    ok = node.send(a.instruction)
    print(f"[capture] instruction: {a.instruction!r} (subs {node.instr_pub.get_subscription_count()}, "
          f"bridge confirmed {ok})")
    if not ok:
        node.send("")
        sys.exit(3)

    rows, k, t_start = [], 0, time.monotonic()
    passed_t = None
    verdict = "timeout"
    with open(out / "capture.jsonl", "w") as f:
        while time.monotonic() - t_start < a.timeout:
            t = time.monotonic()
            img = node.frame_rgb()
            pose = stream.latest
            if img is None or pose is None:
                time.sleep(0.05)
                continue
            x, y, yaw = pose
            heading = math.atan2(math.sin(yaw + YAW_OFFSET), math.cos(yaw + YAW_OFFSET))
            name = f"frames/{k:05d}.jpg"
            PILImage.fromarray(np.ascontiguousarray(img)).save(out / name, quality=95)
            with node.lock:
                prev = node.preview
                prev_age = t - node.preview_t if node.preview_t else None
            dists = []
            for e in obs:
                ox, oy = e["pose"][0], e["pose"][1]
                along = (ox - x) * math.cos(heading) + (oy - y) * math.sin(heading)
                across = -(ox - x) * math.sin(heading) + (oy - y) * math.cos(heading)
                dists.append({"entity": e["entity"], "model": e["model"], "centre_m": math.hypot(ox - x, oy - y),
                              "along_m": along, "across_m": across})
            row = {"k": k, "t": round(t - t_start, 3), "frame": name, "x": x, "y": y, "heading": heading,
                   "state": node.state(), "preview_lat_end": lateral_end(prev) if prev else None,
                   "preview_age_s": prev_age, "preview": prev, "obstacles": dists}
            f.write(json.dumps(row) + "\n")
            rows.append(row)
            k += 1
            if dists:
                d0 = dists[0]
                if abs(d0["along_m"]) < 4.6 and abs(d0["across_m"]) < 1.85 and verdict == "timeout":
                    verdict = "contact"
                    passed_t = passed_t or time.monotonic()
                if d0["along_m"] < -6.0 and verdict == "timeout":
                    verdict = "passed"
                    passed_t = passed_t or time.monotonic()
            if passed_t and time.monotonic() - passed_t > 2.0:
                break
            time.sleep(max(0.0, 1.0 / a.rate - (time.monotonic() - t)))
    node.send("")
    print(f"[capture] {verdict}: {k} frames -> {out}")
    (out / "meta.json").write_text(json.dumps({
        "scenario": a.scenario, "instruction": a.instruction, "verdict": verdict,
        "frames": k, "entities": obs, "created": time.strftime("%F %T")}, indent=2))
    stream.stop()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()

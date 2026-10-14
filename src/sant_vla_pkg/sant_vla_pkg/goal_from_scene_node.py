#!/usr/bin/env python3
"""Goal-from-scene node (2026-10-12, point-goal primitive).

The policy (g5d line) learned ONE thing: "steer toward the goal vector
[goal_bearing, goal_dist] in the state channel and stop at the standoff". It
never sees an object name. This node turns a spoken request into that vector
from what the camera (and LiDAR) see — no global pose, no map:

    request on `request_topic`  ("go to the dinosaur", "go between the circle
    and the square", "stop to the left of the triangle", ...)
      -> Qwen2.5-VL (ollama /api/chat, the GUI's transport) boxes the referred
         object(s) in the CURRENT frame and names the relation
      -> box centre column -> bearing = atan((W/2 - u) / f), f = (W/2)/tan(hfov/2)
         (same formula as server/code/course/qwen_vl.py side())
      -> distance: LiDAR min range within +-lidar_window_deg of that bearing
         (+ object radius -> centre distance, the teacher's label) or, without
         a scan, flat-ground monocular from the box bottom row
      -> relation:  single    goal = object centre, standoff = half_len + gap + r
                    between   goal = midpoint of the two objects pushed one
                              virtual standoff (half_len + gap) further away,
                              so the learned stop lands BETWEEN them
                    left_of / right_of  goal = object +- side_offset_m along
                              the left normal of the ego->object ray
      -> publishes "rel:<bearing_rad>,<dist_m>" on `goal_topic` at publish_hz
         (vla_bridge_node _goal_cb, 2026-10-12) and "Target." on
         /vla/instruction; inside the standoff it publishes "hold" on
         /vla/hold (the stop is CODE, docs/experiments/goto_object/
         20261012_1850_point-goal-primitive-prereg.md).

Between VLM refreshes (period_s) the last vector is re-published unchanged; it
goes stale as the car moves, which is why period_s should stay near 1 s.

Honest framing for the course: the NEW behaviour ("between", "left of",
unseen shapes, "an extinct animal") is composed here, by the VLM and this
geometry; the VLA reuses the one primitive it learned.

Run (sim, with smolvla_demo.sh up):
  ros2 run sant_vla_pkg goal_from_scene_node --ros-args -p use_sim_time:=true \
      -p ollama_host:=http://127.0.0.1:11501 -p scan_topic:=/scan
  ros2 topic pub --once /goal_request std_msgs/msg/String "{data: 'go between the red cone and the box'}"
"""
import base64
import json
import math
import re
import threading
import time
import urllib.error
import urllib.request

import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy)
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import String

# teacher constants (sant_vla_pkg.goto_layout): origin -> nose, bumper gap
EGO_HALF_LEN = 2.3
STOP_GAP = 1.2

PROMPT = (
    'Instruction for a small car: "{req}". Look at the camera image. '
    'Output ONLY JSON: {{"relation": R, "objects": [{{"label": "name", '
    '"bbox_2d": [x1, y1, x2, y2]}}, ...]}}. R is one of "single" (drive to one '
    'object), "between" (stop between two objects), "left_of", "right_of" '
    '(stop beside one object on that side). List the referred object(s) in the '
    'order the instruction names them. If the instruction describes an object '
    'indirectly (e.g. "an extinct animal"), pick the visible object that fits. '
    'If NO visible object matches the instruction, output '
    '{{"relation": "none", "objects": []}} and nothing else.')
# ollama's Qwen2.5-VL returns bbox_2d in the 0..1000 normalised space (checked
# 2026-10-12 against a frame with known geometry: three bearings within 1.6 deg
# once scaled by w/1000, h/1000; read as pixels they were 8-18 deg off).

# 2026-10-13 clarification ("되묻기"): when the direct prompt keeps saying "none", list every
# visible object (21 frames: 20 found, but distant animals only as "animal"), let the VLM pick the
# most likely one, and ASK the user before driving. Close range did not help recognition (rear/front
# horse 0/4 at 5 m), so the car never drives on an unconfirmed guess.
LIST_PROMPT = (
    'List every standalone object in this road scene (things placed on or beside the road: cones, '
    'animals, furniture, boxes, bins, people, vehicles, toys). Ignore road paint, grass, flowers and sky. '
    'Small and distant objects count too. Output ONLY JSON: [{"label": "short name", "bbox_2d": [x1, y1, x2, y2]}, ...] '
    'or [] if there is none.')
PICK_PROMPT = (
    'Instruction for a small car: "{req}". The objects visible in the camera image are:\n{cands}\n'
    'Distant objects look small and blurry, so their names above may be generic or slightly wrong; '
    'use the image and the positions to decide. Which numbered object does the instruction refer to? '
    'Output ONLY JSON: {{"pick": N}} or {{"pick": null}} if none of them can be it.')
KO_LABEL = (("dinosaur", "공룡"), ("teddy", "곰 인형"), ("cone", "꼬깔"), ("chair", "의자"), ("trash", "쓰레기통"),
            ("bin", "쓰레기통"), ("box", "상자"), ("dog", "강아지"), ("horse", "말"), ("person", "사람"),
            ("human", "사람"), ("car", "차"), ("vehicle", "차"), ("ball", "공"), ("cube", "정육면체"),
            ("barrel", "드럼통"), ("barrier", "바리케이드"), ("hydrant", "소화전"), ("monster", "괴물 모양"),
            ("creature", "동물"), ("statue", "조형물"), ("animal", "동물"))
YES = re.compile(r"^\s*(응+|어+|네|넹|예|맞아|맞아요|맞음|맞습니다|그래|그래요|그거|그거야|ㅇㅇ+|좋아|가자|가줘|고고|ok|okay|yes|y)"
                 r"(?=$|[\s.!~,요])", re.I)


def _ko_label(label):
    low = str(label).lower()
    for en, ko in KO_LABEL:
        if en in low:
            return ko
    return f"'{label}'"


def _where(bearing, dist):
    deg = math.degrees(bearing)
    side = "정면" if abs(deg) < 5.0 else ("왼쪽 앞" if deg > 0 else "오른쪽 앞")
    return f"{side} 약 {dist:.0f} m"


KO_REL = ((re.compile(r"사이|between"), "between"),
          (re.compile(r"왼쪽|왼편|left"), "left_of"),
          (re.compile(r"오른쪽|오른편|right"), "right_of"))


def _rel_from_text(req):
    for rx, rel in KO_REL:
        if rx.search(req):
            return rel
    return "single"


def _boxes(txt):
    out = []
    for m in re.finditer(r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*"
                         r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\]}]", txt):   # 10-13: qwen once closed a bbox with "}"
        out.append([float(v) for v in m.groups()])
    return out


class GoalFromScene(Node):
    def __init__(self):
        super().__init__("goal_from_scene")
        dp = self.declare_parameter
        self.request_topic = dp("request_topic", "/goal_request").value
        self.image_topic = dp("image_topic", "/camera/image_raw").value
        self.scan_topic = dp("scan_topic", "/scan").value
        self.goal_topic = dp("goal_topic", "/vla_goal").value
        self.ollama_host = dp("ollama_host", "http://127.0.0.1:11501").value
        self.model = dp("model", "qwen2.5vl:7b").value
        self.hfov_deg = float(dp("hfov_deg", 62.2).value)      # /camera/image_raw (model.sdf:1317)
        self.period_s = float(dp("period_s", 1.0).value)        # VLM refresh
        self.publish_hz = float(dp("publish_hz", 10.0).value)
        self.lidar_window_deg = float(dp("lidar_window_deg", 4.0).value)
        # sim ego gpu_lidar (2026-10-13, measured against a cone at a known pose): sensor 0 deg =
        # vehicle right, forward = 270 deg, and a bearing to the LEFT RAISES the scan angle (cone
        # 47 deg left of the bumper read at 313 deg). With the old implicit 0 deg = forward the window
        # sat on the car's side and read ~0.5 m, so the stop gate fired at once. The lidar sits on the
        # front bumper (prius_hybrid lidar_link y -1.9) and the policy camera 0.32 m behind the origin,
        # so rays are matched by the bearing their hit point has FROM THE CAMERA (parallax up close).
        self.lidar_forward_deg = float(dp("lidar_forward_deg", 270.0).value)
        self.lidar_left_sign = float(dp("lidar_left_sign", 1.0).value)
        self.lidar_ahead_m = float(dp("lidar_ahead_m", 1.9).value)
        self.cam_ahead_m = float(dp("cam_ahead_m", -0.32).value)
        self.obj_radius_m = float(dp("obj_radius_m", 0.5).value)  # surface -> centre
        self.side_offset_m = float(dp("side_offset_m", 1.5).value)
        # bumper-side stop gap (2026-10-13 user: "stops too far"). The policy learned to slow
        # down for the teacher gap STOP_GAP, so the published distance is lengthened by
        # (STOP_GAP - stop_gap_m): the policy brakes as it always did, the gate holds closer.
        # Clearance to the object surface ~ EGO_HALF_LEN + stop_gap_m - 1.904 (collision nose).
        self.stop_gap_m = float(dp("stop_gap_m", STOP_GAP).value)
        # monocular fallback beyond the 12 m LiDAR: ground row of the box bottom. Fitted 2026-10-13 on
        # a red cone at 8-35 m straight ahead (box bottom y2 = y0 + k/d, within 1 px at 12-35 m). The old
        # flat-ground model assumed the horizon at the image centre; the real horizon sits ~92 px higher,
        # so every object past ~12 m read a constant 12.0 m.
        self.mono_horizon_frac = float(dp("mono_horizon_frac", 148.0 / 480.0).value)
        self.mono_k_frac = float(dp("mono_k_frac", 842.0 / 480.0).value)
        self.lidar_range_m = float(dp("lidar_range_m", 12.0).value)
        # the point-goal policy was trained on goals 5-12.5 m away (goto_layout dist); farther goals
        # are published at this distance so it keeps driving at the trained approach speed
        self.policy_max_dist_m = float(dp("policy_max_dist_m", 12.5).value)
        # 2026-10-13 far objects: Qwen's answer on a small/distant object (animals from behind, 18-25 m)
        # flips between a box and "none" from sample to sample, and at temperature 0.1 a parked car sends
        # the same frame every second and gets the same "none" forever. After a miss the node re-asks
        # at retry_temp; a box found that way is used only once a second sample agrees within
        # confirm_deg (bench 27 cases: hits 17 -> 22-23, no wrong object; scratch far_bench2.py).
        self.retry_temp = float(dp("retry_temp", 0.5).value)
        self.confirm_deg = float(dp("confirm_deg", 3.5).value)
        self.nomatch_after = int(dp("nomatch_after", 6).value)
        self.publish_instruction = bool(dp("publish_instruction", True).value)
        self.instruction_text = dp("instruction_text", "Target.").value
        self.vlm_timeout_s = float(dp("vlm_timeout_s", 20.0).value)
        self.vlm_coords = dp("vlm_coords", "norm1000").value       # norm1000 | pixel
        # 2026-10-13 L5: perceiver "smolvla" finds the named object with the frozen SmolVLA VLM + a small
        # trained location head (smolvla_perceiver.py) — no Qwen. Trained names only; others -> ask.
        self.perceiver = dp("perceiver", "qwen").value
        self._sv = None
        if self.perceiver == "smolvla":
            try:
                from sant_vla_pkg.smolvla_perceiver import SmolVLAPerceiver
            except ImportError:
                from smolvla_perceiver import SmolVLAPerceiver
            l5 = dp("l5_dir", "/home/sh/ROS2_project/sant-vla/eval_out/course/l5").value
            # head_name_all.pt also learned horse / blue cone (demo); head_name.pt is the L5 held-out result
            head = dp("l5_head", "head_name_all.pt").value
            import os
            base = dp("smolvla_base", "").value or next(
                (q for q in ("/home/sh/ROS2_project/ros2_vla/models/smolvla_base/model.safetensors",
                             # 10-13 22:31 ros2_vla was rebuilt without models/; same weights (outputs identical)
                             "/home/sh/ROS2_project/ros2_vla_0829/models/smolvla_base/model.safetensors")
                 if os.path.exists(q)), None)
            self._sv = SmolVLAPerceiver(base, f"{l5}/{head}", f"{l5}/names.npz")
            import sant_vla_pkg.smolvla_perceiver as svp
            self._trained = svp.TRAINED_ALL if "_all" in head else svp.TRAINED
            self.period_s = float(dp("smolvla_period_s", 0.5).value)

        qos_d = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.RELIABLE,
                           durability=QoSDurabilityPolicy.TRANSIENT_LOCAL)
        qos_img = QoSProfile(depth=1, reliability=QoSReliabilityPolicy.BEST_EFFORT,
                             history=QoSHistoryPolicy.KEEP_LAST,
                             durability=QoSDurabilityPolicy.VOLATILE)
        self.goal_pub = self.create_publisher(String, self.goal_topic, qos_d)
        self.hold_pub = self.create_publisher(String, "/vla/hold", 5)
        self.instr_pub = self.create_publisher(String, "/vla/instruction", qos_d)
        self.status_pub = self.create_publisher(String, "/goal_from_scene/status", 5)
        # 2026-10-13: the point-goal policy has no trained reasoning head (ce 0), so the GUI's
        # "model reasoning" tab shows what THIS node observed and decided, observe -> decide.
        self.reason_pub = self.create_publisher(String, "/vla/reasoning", 5)
        self.action_pub = self.create_publisher(String, "/goal_from_scene/action", 5)   # English, for the scene commentary
        self._last_reason = 0.0
        self.create_subscription(String, self.request_topic, self._req_cb, 5)
        self.create_subscription(Image, self.image_topic, self._img_cb, qos_img)
        self.create_subscription(LaserScan, self.scan_topic, self._scan_cb, qos_img)
        # 2026-10-13 live test: a horse picked at 21 m was lost by the VLM after two answers and the
        # goal froze at "7 deg, 16 m" — the policy drove on past it. The ego motion since the
        # observation (integrated /odom twist: forward speed + yaw rate, no global pose) now moves the
        # last seen point back into the current ego frame, so the goal shrinks and the gate fires
        # even when nothing re-detects the object.
        self.create_subscription(Odometry, dp("odom_topic", "/odom").value, self._odom_cb, 20)
        self._ego = (0.0, 0.0, 0.0)  # dead-reckoned (x, y, yaw) since start
        self._odom_t = None

        self._lock = threading.Lock()
        self._img = None
        self._scan = None
        self._req = None            # active request text
        self._goal = None           # (bearing_rad, dist_m, standoff_m)
        # 2026-10-13: LiDAR tracking between VLM answers. The VLM takes ~2 s per answer and the
        # goal used to stay frozen meanwhile, so the gate saw 5.9 m then 3.0 m and the car hit
        # the object once the stop gap was shortened. Now the VLM only PICKS the object(s); every
        # scan re-finds them near their last point and the goal + gate follow at scan rate.
        self._track = None          # (rel, [object centres (x fwd, y left)], last_seen_monotonic, ego at that time)
        self.track_radius_m = float(dp("track_radius_m", 1.2).value)
        self.track_lost_s = float(dp("track_lost_s", 1.0).value)
        self._ask = None            # pending clarification question (candidate dict)
        self._asked = False         # one clarification per request
        self._pinned = False        # goal confirmed by the user: no VLM re-picks
        self._misses = 0            # consecutive "none" answers for the current request
        self._pending = []          # bearings of unconfirmed retry hits
        self._hold = False
        self._last_vlm = 0.0
        self._busy = False
        self.create_timer(1.0 / self.publish_hz, self._tick)
        self.get_logger().info(f"goal_from_scene: request {self.request_topic}, image {self.image_topic}, "
                               f"scan {self.scan_topic}, "
                               + (f"perceiver SmolVLA (L5 head), " if self._sv is not None else f"VLM {self.model} @ {self.ollama_host}, ")
                               + f"hfov {self.hfov_deg} deg")

    # ---------------- inputs ----------------
    def _img_cb(self, msg):
        self._img = msg

    def _odom_cb(self, msg):
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self._odom_t is not None:
            dt = min(max(t - self._odom_t, 0.0), 0.2)
            x, y, yaw = self._ego
            v, w = msg.twist.twist.linear.x, msg.twist.twist.angular.z
            self._ego = (x + v * math.cos(yaw) * dt, y + v * math.sin(yaw) * dt, yaw + w * dt)
        self._odom_t = t

    @staticmethod
    def _propagate(pts, e0, e1):
        """Ego-frame points seen at ego pose e0 -> ego frame at pose e1."""
        out = []
        for px, py in pts:
            wx = e0[0] + px * math.cos(e0[2]) - py * math.sin(e0[2])
            wy = e0[1] + px * math.sin(e0[2]) + py * math.cos(e0[2])
            dx, dy = wx - e1[0], wy - e1[1]
            out.append((dx * math.cos(e1[2]) + dy * math.sin(e1[2]), -dx * math.sin(e1[2]) + dy * math.cos(e1[2])))
        return out

    def _scan_cb(self, msg):
        self._scan = msg
        with self._lock:
            tr = self._track
            if tr is None or self._req is None:
                return
            rel, pts, seen, e_obs = tr
            ego = self._ego
            pred = self._propagate(pts, e_obs, ego)
            new = [self._track_point(msg, p) for p in pred]
            if any(p is None for p in new):
                # not on the LiDAR (beyond 12 m, or lost): drive on the dead-reckoned point; the
                # track stays "lost" so the VLM keeps re-asking
                self._goal = self._goal_from(rel, pred)
                return
            self._track = (rel, new, time.monotonic(), ego)
            self._goal = self._goal_from(rel, new)

    def _req_cb(self, msg):
        req = msg.data.strip()
        with self._lock:
            if not req or req.lower() in ("none", "stop", "정지", "clear"):
                self._req, self._goal, self._track = None, None, None
                self._ask, self._pinned = None, False
                self._set_hold(req.lower() in ("stop", "정지"))
                self.goal_pub.publish(String(data="none"))
                if self.publish_instruction and req.lower() in ("stop", "정지"):
                    self.instr_pub.publish(String(data=""))
                self._status("cleared")
                return
            if req.startswith("answer:"):
                self._answer(req[7:].strip())
                return
            if req == "look:":
                # "뭐가 보여?" in SmolVLA mode: answered by the same head, not by a chat VLM
                threading.Thread(target=self._look, args=(self._img, self._scan), daemon=True).start()
                return
            self._req, self._goal, self._last_vlm, self._track = req, None, 0.0, None
            self._misses, self._pending = 0, []
            self._ask, self._asked, self._pinned, self._why = None, False, False, ""
            self._set_hold(False)
            self._status(f"request: {req}")

    def _answer(self, text):
        """User reply to an ASK: question (caller holds the lock)."""
        ask = self._ask
        if ask is None or self._req is None:
            self._status("SEEN: 지금은 확인을 기다리는 질문이 없습니다.")
            return
        num = re.match(r"^\s*(\d+)", text)
        if num and 1 <= int(num.group(1)) <= len(ask["cands"]):
            ask = dict(ask, **ask["cands"][int(num.group(1)) - 1])
        elif not YES.match(text) or ask.get("pt") is None:
            ask = None
        self._ask = None
        if ask is not None:
            pt = ask["pt"]
            self._track = ("single", [pt], time.monotonic(), ask["ego"])
            self._goal = self._goal_from("single", self._propagate([pt], ask["ego"], self._ego))
            self._pinned = True     # user-confirmed: no more VLM re-picks, LiDAR/odometry keep the point
            if self.publish_instruction:
                self.instr_pub.publish(String(data=self.instruction_text))
            self._status(f"confirmed: {ask['label']} ({ask['where']}) — 사용자가 확인한 물체로 이동")
        else:
            self._req, self._goal, self._track = None, None, None
            self.goal_pub.publish(String(data="none"))
            self._status("SEEN: 알겠습니다, 출발하지 않습니다. 다른 물체로 가려면 다시 말해 주세요.")

    # ---------------- loop ----------------
    def _reason(self, req, goal, tracking):
        if self._ask is not None:
            a = self._ask
            cand = f"후보 {a['label']} ({a['where']})" if a.get("pt") is not None else f"보이는 물체 {len(a['cands'])}개"
            text = (f"관찰: '{req}'에 확실히 맞는 물체 없음 · {cand}\n"
                    "판단: 추측으로 출발하지 않고 사용자 확인을 기다린다")
            self.reason_pub.publish(String(data=json.dumps({"text": f"'{req}'\n{text}"}, ensure_ascii=False)))
            self.action_pub.publish(String(data=f'waiting: asked the user which visible object they meant '
                                                f'("{req}"); not moving until they answer'))
            return
        if goal is None:
            text = (f"관찰: 화면에서 '{req}' 대상을 찾는 중 ({'SmolVLA' if self._sv is not None else 'Qwen-VL'})\n"
                    "판단: 대상을 찾기 전에는 출발하지 않는다")
        else:
            b, d, standoff = goal
            deg = math.degrees(b)
            side = "정면" if abs(deg) < 2.0 else (f"왼쪽 {deg:.0f}°" if deg > 0 else f"오른쪽 {-deg:.0f}°")
            rel = self._track[0] if self._track else "single"
            where = {"between": "두 물체 사이 지점", "left_of": "물체 왼쪽 지점",
                     "right_of": "물체 오른쪽 지점"}.get(rel, "목표 물체")
            how = ("라이다 추적" if tracking else
                   "사용자가 고른 물체 · 주행 거리로 위치 갱신" if self._pinned else
                   (f"라이다 범위 {self.lidar_range_m:.0f} m 밖 → 거리 모름, {self.policy_max_dist_m:.1f} m 로 두고 접근"
                    if self._sv is not None else
                    f"라이다 범위 {self.lidar_range_m:.0f} m 밖 → 카메라로 거리 추정") if d > self.lidar_range_m else
                   f"라이다 놓침 → {'SmolVLA' if self._sv is not None else 'Qwen-VL'} 재탐색")
            if self._hold:
                text = (f"관찰: {where} {side} · {d:.1f} m ({how})\n"
                        f"판단: 정지 거리 {standoff:.1f} m 안에 들어와 멈춘다")
            else:
                text = (f"관찰: {where} {side} · {d:.1f} m ({how})\n"
                        f"판단: 그쪽으로 조향하며 접근한다 · 정지까지 {max(0.0, d - standoff):.1f} m")
        self.reason_pub.publish(String(data=json.dumps({"text": f"'{req}'\n{text}"}, ensure_ascii=False)))
        if goal is None:
            act = f'looking for the object the user asked for ("{req}") before moving'
        else:
            b, d, standoff = goal
            deg = math.degrees(b)
            side = "straight ahead" if abs(deg) < 2.0 else f"{abs(deg):.0f} deg to the {'left' if deg > 0 else 'right'}"
            act = (f'stopped in front of the requested object ("{req}"), {d:.1f} m away' if self._hold else
                   f'driving to the requested object ("{req}"), {side}, {d:.1f} m away, '
                   f'will stop in {max(0.0, d - standoff):.1f} m')
        self.action_pub.publish(String(data=act))

    def _tick(self):
        with self._lock:
            req, goal = self._req, self._goal
        if req is None:
            return
        now_r = time.monotonic()
        if now_r - self._last_reason >= 1.0:
            self._last_reason = now_r
            with self._lock:
                tracking = self._track is not None and now_r - self._track[2] < self.track_lost_s
            self._reason(req, goal, tracking)
        if goal is not None:
            b, d, standoff = goal
            shown = min(d, self.policy_max_dist_m) + (STOP_GAP - self.stop_gap_m)   # what the policy hears (see stop_gap_m)
            self.goal_pub.publish(String(data=f"rel:{b:.4f},{shown:.3f}"))
            if d < standoff and not self._hold:
                self._set_hold(True)
                self._status(f"gate: dist {d:.2f} < standoff {standoff:.2f} -> hold")
            elif abs(b) > math.radians(100.0) and d < 3.0 * standoff and not self._hold:
                # the dead-reckoned target slid behind the car (missed it): stop instead of circling
                self._set_hold(True)
                self._status(f"gate: target passed (bearing {math.degrees(b):.0f} deg, {d:.2f} m) -> hold")
        now = time.monotonic()
        with self._lock:
            tracking = self._track is not None and now - self._track[2] < self.track_lost_s
        if (not tracking and not self._busy and self._ask is None and not self._pinned
                and now - self._last_vlm >= self.period_s and self._img is not None):
            self._busy = True
            threading.Thread(target=self._refresh, args=(req, self._img, self._scan, self._ego), daemon=True).start()

    def _set_hold(self, on):
        if on != self._hold:
            self._hold = on
        self.hold_pub.publish(String(data="hold" if on else "off"))

    def _status(self, text):
        self.get_logger().info(text)
        self.status_pub.publish(String(data=text))

    # ---------------- perception -> goal ----------------
    def _refresh(self, req, img, scan, ego):
        try:
            res = self._compute(req, img, scan)
            if res is None and self._clarify_due():
                self._clarify(req, img, scan, ego)
                return
            with self._lock:
                if self._req != req:
                    return
                if res is not None:
                    first = self._goal is None
                    rel, pts = res
                    # the answer is ~1-2 s old by now: keep the ego pose of the frame that was asked
                    self._track = (rel, pts, time.monotonic(), ego)
                    self._goal = self._goal_from(rel, self._propagate(pts, ego, self._ego))
                    if first and self.publish_instruction:
                        self.instr_pub.publish(String(data=self.instruction_text))
        except Exception as e:                      # noqa: BLE001 — keep publishing the last goal
            self._status(f"refresh failed: {e!r}")
        finally:
            self._last_vlm = time.monotonic()
            self._busy = False

    def _compute(self, req, img, scan):
        if self._sv is not None:
            return self._compute_smolvla(req, img, scan)
        w, h = img.width, img.height
        retry = self._misses > 0
        reply = self._ask_vlm(req, img, self.retry_temp if retry else 0.1)
        rel, boxes = self._parse(reply, req, w, h)
        if rel == "none" or not boxes:
            self._misses += 1
            if self._misses < self.nomatch_after:
                self._status(f"VLM: 대상이 작거나 멀 수 있어 다시 보는 중 ({self._misses}/{self.nomatch_after})")
            elif self._clarify_due():
                self._status("VLM: 확실한 물체가 없어 보이는 물체를 전부 살피는 중")
            else:
                self._status(f"VLM: no matching object ({reply.strip()[:100]!r}) — not moving")
            return None
        f = (w / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)
        if retry:
            u = (boxes[0][0] + boxes[0][2]) / 2.0
            b0 = math.degrees(math.atan((w / 2.0 - u) / f))
            if not any(abs(b0 - q) <= self.confirm_deg for q in self._pending):
                self._pending.append(b0)
                self._status(f"VLM: 후보 발견 ({b0:+.1f} deg), 한 번 더 보고 확정")
                return None
        self._misses, self._pending = 0, []
        pts = [self._box_to_point(b, w, h, f, scan) for b in boxes]
        if rel == "between" and len(pts) < 2:
            rel = "single"
        g = self._goal_from(rel, pts)
        self._status(f"{rel}: boxes {[[round(v) for v in bb] for bb in boxes]} -> "
                     f"goal bearing {math.degrees(g[0]):.1f} deg, dist {g[1]:.2f} m, standoff {g[2]:.2f}")
        return rel, pts

    def _clarify_due(self):
        return (self._misses >= self.nomatch_after and not self._asked and self._goal is None
                and self._req is not None
                and (self._sv is not None or _rel_from_text(self._req) == "single"))   # SmolVLA mode: just says so

    def _clarify(self, req, img, scan, ego):
        self._asked = True
        if self._sv is not None:
            return self._clarify_smolvla(req, img, scan, ego)
        w, h = img.width, img.height
        reply = self._vlm(LIST_PROMPT, img, 0.1, 400)
        try:
            objs = json.loads(reply[reply.index("["):reply.rindex("]") + 1])
        except ValueError:
            objs = []
        objs = [o for o in objs if isinstance(o, dict) and len(o.get("bbox_2d") or []) == 4][:8]
        if not objs:
            self._status("SEEN: 말씀하신 물체를 찾지 못했고, 화면에 다른 물체도 보이지 않습니다. 출발하지 않습니다.")
            return
        f = (w / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)
        cands = []
        for o in objs:
            b = [float(v) for v in o["bbox_2d"]]
            if self.vlm_coords == "norm1000" or max(b) > max(w, h) * 1.05:
                b = [b[0] * w / 1000.0, b[1] * h / 1000.0, b[2] * w / 1000.0, b[3] * h / 1000.0]
            pt = self._box_to_point(b, w, h, f, scan)
            label = str(o.get("label", "object"))
            cands.append({"label_en": label, "label": _ko_label(label), "pt": pt,
                          "where": _where(math.atan2(pt[1], pt[0]), math.hypot(*pt))})
        listing = "\n".join(f'{i + 1}. "{c["label_en"]}" at bbox_2d {objs[i]["bbox_2d"]}' for i, c in enumerate(cands))
        m = re.search(r'"pick"\s*:\s*(\d+)', self._vlm(PICK_PROMPT.format(req=req, cands=listing), img, 0.1, 40))
        numbered = " ".join(f"{i + 1}) {c['label']}({c['where']})" for i, c in enumerate(cands))
        with self._lock:
            if self._req != req:
                return
            if not m or not 1 <= int(m.group(1)) <= len(cands):
                # nothing fits: let the user choose by number instead of guessing
                self._ask = {"pt": None, "cands": cands, "ego": ego}
                self._status(f"ASK: '{req}'에 맞는 물체를 찾지 못했어요. 지금 보이는 것: {numbered}. "
                             "이 중에 있으면 번호로, 없으면 '아니'라고 답해 주세요.")
                return
            c = cands[int(m.group(1)) - 1]
            self._ask = dict(c, cands=cands, ego=ego)
            alt = f" 다른 것이면 번호로 골라 주세요: {numbered}." if len(cands) > 1 else ""
            self._status(f"ASK: '{req}'에 맞는 물체를 확실히 찾지 못했어요. {c['where']}에 "
                         f"{c['label']}(으)로 보이는 것이 있는데, 이걸로 갈까요? (응 / 아니){alt}")

    # ---------------- SmolVLA-only perception (L5) ----------------
    @staticmethod
    def _rgb(img):
        import numpy as np
        arr = np.frombuffer(bytes(img.data), dtype=np.uint8).reshape(img.height, img.width, -1)
        if img.encoding.lower().startswith("bgr"):
            arr = arr[:, :, ::-1]
        return np.ascontiguousarray(arr[:, :, :3])

    def _x_to_point(self, x, w, scan):
        f = (w / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)
        bearing = math.atan((w / 2.0 - x) / f)
        if scan is not None:
            hit = self._lidar_point(scan, bearing)
            if hit is not None:
                return hit[0] + self.obj_radius_m * math.cos(bearing), hit[1] + self.obj_radius_m * math.sin(bearing)
        # beyond the LiDAR the head gives no range: aim at the trained far end and let the scan take over
        d = self.policy_max_dist_m
        return d * math.cos(bearing), d * math.sin(bearing)

    def _compute_smolvla(self, req, img, scan):
        from sant_vla_pkg.smolvla_perceiver import EN2KO, names_in
        TRAINED = self._trained
        refs = names_in(req)
        rel = _rel_from_text(req)
        if not refs:
            self._misses = self.nomatch_after
            self._why = "요청에서 알아볼 수 있는 물체 이름을 찾지 못함"
            self._status(f"SmolVLA: '{req}'에서 아는 물체 이름을 찾지 못했어요")
            return None
        unknown = [w for (w, c) in refs if not any(n in TRAINED for n in c)]
        if unknown:
            # an untrained name never becomes visible to the head (L5 B: 0.1 %) — say so at once
            self._misses = self.nomatch_after
            self._why = f"대상 '{unknown[0]}'은(는) 알아보도록 배우지 않은 물체"
            self._status(f"SmolVLA: '{unknown[0]}'은(는) 학습하지 않은 이름")
            return None
        if rel == "between" and len(refs) < 2:
            # 10-13: "강이지와 드럼통 사이의 물체로" matched only 드럼통 and the car drove to the drum
            self._misses = self.nomatch_after
            self._why = (f"'사이' 요청인데 물체 이름을 하나('{refs[0][0]}')만 알아들음, 두 물체가 필요함")
            self._status(f"SmolVLA: between needs two known names, got {[w for w, _ in refs]}")
            return None
        tok = self._sv.tokens(self._rgb(img))
        found = []
        for word, cands in refs[:2 if rel == "between" else 1]:
            res = self._sv.find(tok, cands, img.width)
            if not res:
                found.append(None)
                continue
            name, (pn, x) = min(res.items(), key=lambda kv: kv[1][0])
            found.append((word, name, pn, x))
        if any(f is None or f[2] >= 0.5 for f in found):
            self._misses += 1
            why = "화면에서 찾지 못함 (" + ", ".join(f"{f[0]} 안 보임 {f[2]:.2f}" for f in found if f) + ")"
            self._why = f"대상 '{found[0][0] if found and found[0] else refs[0][0]}'은(는) 알아볼 수 있는 물체지만 지금 화면에서 찾지 못함"
            self._status(f"SmolVLA: {why} ({self._misses}/{self.nomatch_after})")
            return None
        self._misses = 0
        pts = [self._x_to_point(f[3], img.width, scan) for f in found]
        if rel == "between" and len(pts) < 2:
            rel = "single"
        g = self._goal_from(rel, pts)
        self._status("SmolVLA " + rel + ": " + ", ".join(f"{EN2KO.get(f[1], f[1])} x={f[3]:.0f}px 보임 {1 - f[2]:.2f}" for f in found)
                     + f" -> goal bearing {math.degrees(g[0]):.1f} deg, dist {g[1]:.2f} m, standoff {g[2]:.2f}")
        return rel, pts

    def _look(self, img, scan):
        from sant_vla_pkg.smolvla_perceiver import EN2KO
        if self._sv is None or img is None:
            self._status("LOOK: 지금은 SmolVLA 로 화면을 볼 수 없습니다(카메라 없음 또는 Qwen 모드).")
            return
        res = self._sv.find(self._sv.tokens(self._rgb(img)), list(self._trained), img.width)
        seen = []
        for p, x, n in sorted(((p, x, n) for n, (p, x) in res.items() if p < 0.5), key=lambda t: t[1]):
            if any(abs(x - q) < 30 for q, _ in seen):        # one object answering to two names
                continue
            pt = self._x_to_point(x, img.width, scan)
            where = _where(math.atan2(pt[1], pt[0]), math.hypot(*pt))
            if abs(math.hypot(*pt) - self.policy_max_dist_m) < 1e-3:      # no LiDAR return: range unknown
                where = where.rsplit(" 약 ", 1)[0] + f" {self.lidar_range_m:.0f} m 넘게"
            seen.append((x, f"{EN2KO.get(n, n)}({where}, 확신 {1 - p:.2f})"))
        # facts only; the GUI words the reply (SmolVLA-only chat, 10-13 user: "talk like a person")
        self._status("LOOK: " + ("; ".join(t for _, t in seen) if seen else "알아본 물체 없음"))

    def _clarify_smolvla(self, req, img, scan, ego):
        from sant_vla_pkg.smolvla_perceiver import EN2KO
        # 2026-10-13 user: a numbered "which one?" list names objects only from the head's 10 trained
        # nouns — on the real track the objects are not those props, so the list would pretend to know
        # them. SmolVLA mode therefore only says it did not find the object and does not move.
        with self._lock:
            if self._req != req:
                return
            # drop the request: re-checking an untrained name every 0.5 s can never succeed
            self._req, self._goal, self._track = None, None, None
            self.goal_pub.publish(String(data="none"))
            why = getattr(self, "_why", "") or "화면에서 찾지 못함"
            self._status(f"SEEN: '{req}' → {why} → 출발하지 않음")

    def _goal_from(self, rel, pts):
        if rel == "between" and len(pts) >= 2:
            (x1, y1), (x2, y2) = pts[0], pts[1]
            mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            n = math.hypot(mx, my) or 1e-6
            push = EGO_HALF_LEN + self.stop_gap_m
            gx, gy = mx + push * mx / n, my + push * my / n
            standoff = push
        elif rel in ("left_of", "right_of"):
            ox, oy = pts[0]
            n = math.hypot(ox, oy) or 1e-6
            lx, ly = -oy / n, ox / n                      # left normal of the ego->object ray
            sgn = 1.0 if rel == "left_of" else -1.0
            gx, gy = ox + sgn * self.side_offset_m * lx, oy + sgn * self.side_offset_m * ly
            standoff = EGO_HALF_LEN + self.stop_gap_m
        else:
            gx, gy = pts[0]
            standoff = EGO_HALF_LEN + self.stop_gap_m + self.obj_radius_m
        return (math.atan2(gy, gx), math.hypot(gx, gy), standoff)

    def _track_point(self, scan, p):
        """Re-find an object near its last centre p in a new scan; returns the new centre."""
        fwd = math.radians(self.lidar_forward_deg)
        pts = []
        a = scan.angle_min
        for r in scan.ranges:
            if scan.range_min < r < scan.range_max:
                t = self.lidar_left_sign * (a - fwd)
                if r * math.cos(t) > 0.3:                    # ahead of the sensor only (no self-hits)
                    pts.append((self.lidar_ahead_m + r * math.cos(t), r * math.sin(t)))
            a += scan.angle_increment
        near = [q for q in pts if math.hypot(q[0] - p[0], q[1] - p[1]) <= self.track_radius_m]
        if not near:
            return None
        seed = min(near, key=lambda q: math.hypot(q[0] - p[0], q[1] - p[1]))
        blob = [q for q in near if math.hypot(q[0] - seed[0], q[1] - seed[1]) <= 0.8]
        sx, sy = min(blob, key=lambda q: math.hypot(q[0] - self.cam_ahead_m, q[1]))   # nearest surface
        cb = math.atan2(sy, sx - self.cam_ahead_m)
        return sx + self.obj_radius_m * math.cos(cb), sy + self.obj_radius_m * math.sin(cb)

    def _box_to_point(self, box, w, h, f, scan):
        """box -> (x forward, y left) in metres, ego frame."""
        u = (box[0] + box[2]) / 2.0
        bearing = math.atan((w / 2.0 - u) / f)              # left positive
        if scan is not None:
            hit = self._lidar_point(scan, bearing)
            if hit is not None:
                # nearest surface point -> object centre: push obj_radius further along the camera ray
                return hit[0] + self.obj_radius_m * math.cos(bearing), hit[1] + self.obj_radius_m * math.sin(bearing)
        # no LiDAR return (beyond its 12 m range): ground row of the box bottom, see mono_horizon_frac
        dv = box[3] - self.mono_horizon_frac * h
        dist = self.mono_k_frac * h / dv if dv > 2.0 else 40.0
        dist = max(2.0, min(40.0, dist))
        return dist * math.cos(bearing), dist * math.sin(bearing)

    def _lidar_point(self, scan, bearing):
        """Nearest LiDAR hit (ego frame: x forward from the origin, y left) whose bearing seen from
        the camera is within lidar_window_deg of the box bearing."""
        win = math.radians(self.lidar_window_deg)
        fwd = math.radians(self.lidar_forward_deg)
        best = None
        a = scan.angle_min
        for r in scan.ranges:
            if scan.range_min < r < scan.range_max:
                t = self.lidar_left_sign * (a - fwd)            # ray angle in the ego frame, left +
                px, py = self.lidar_ahead_m + r * math.cos(t), r * math.sin(t)
                cb = math.atan2(py, px - self.cam_ahead_m)
                # only returns AHEAD of the bumper sensor: rays sideways/backwards hit the car's own
                # body at 0.1-0.5 m, and from the camera those points sit near bearing 0, so a target
                # straight ahead read ~2.3 m and the stop gate fired at once (GUI test 10-13 11:54)
                if r * math.cos(t) > 0.3 and abs(((cb - bearing) + math.pi) % (2 * math.pi) - math.pi) <= win:
                    if best is None or r < best[0]:
                        best = (r, px, py)
            a += scan.angle_increment
        return None if best is None else (best[1], best[2])

    def _parse(self, reply, req, w, h):
        rel = None
        try:
            j = json.loads(reply[reply.index("{"):reply.rindex("}") + 1])
            rel = str(j.get("relation", "")).lower() or None
            boxes = [o["bbox_2d"] for o in j.get("objects", []) if "bbox_2d" in o]
        except (ValueError, KeyError, TypeError, AttributeError):
            boxes = _boxes(reply)
        if rel == "none":
            return "none", []
        if rel not in ("single", "between", "left_of", "right_of"):
            rel = _rel_from_text(req)
        elif rel != "single" and _rel_from_text(req) == "single":
            # 2026-10-13: a retry sample answered "말로 가줘" with left_of; a relation needs its word
            rel = "single"
        coords = getattr(self, "vlm_coords", "norm1000") if self is not None else "norm1000"
        if boxes and (coords == "norm1000" or max(max(b) for b in boxes) > max(w, h) * 1.05):
            boxes = [[b[0] * w / 1000.0, b[1] * h / 1000.0, b[2] * w / 1000.0, b[3] * h / 1000.0] for b in boxes]
        return rel, boxes

    def _ask_vlm(self, req, img, temp=0.1):
        return self._vlm(PROMPT.format(req=req, w=img.width, h=img.height), img, temp, 200)

    def _vlm(self, prompt, img, temp, num_predict):
        data = self._jpeg_b64(img)
        payload = {"model": self.model, "stream": False,
                   "options": {"temperature": temp, "num_predict": num_predict},
                   "messages": [{"role": "user", "content": prompt, "images": [data]}]}
        request = urllib.request.Request(f"{self.ollama_host}/api/chat",
                                         data=json.dumps(payload).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.vlm_timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
        return (body.get("message") or {}).get("content", "")

    @staticmethod
    def _jpeg_b64(img):
        import io
        import numpy as np
        from PIL import Image as PImage
        arr = np.frombuffer(bytes(img.data), dtype=np.uint8).reshape(img.height, img.width, -1)
        if img.encoding.lower().startswith("bgr"):
            arr = arr[:, :, ::-1]
        buf = io.BytesIO()
        PImage.fromarray(arr[:, :, :3]).save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    rclpy.init()
    node = GoalFromScene()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

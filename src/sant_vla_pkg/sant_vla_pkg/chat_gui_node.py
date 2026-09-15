"""Simplified qwen3:4b chat GUI for lane-aware nav-vla driving.

The GUI accepts natural-language commands and publishes one of:
  - /nav_goal JSON for lane-following zone navigation
  - /direct_nav_goal plain zone names for direct shortest-path navigation
  - /lane_mode_command for lane-only changes
  - /motion_control_command for start/stop
  - /speed_command for a user-facing 0..250 raw speed limit

Run with navigator_node:
    ros2 run sant_vla_pkg navigator_node
    ros2 run sant_vla_pkg chat_gui_node
"""

import json
import math
import os
import queue
import re
import base64
import binascii
import csv
import datetime as dt
import io
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from collections import deque
from tkinter import scrolledtext
from tkinter import ttk

import numpy as np
import rclpy
import yaml
from interfaces_pkg.msg import DetectionArray
from interfaces_pkg.msg import LaneInfo
from interfaces_pkg.msg import PathPlanningResult
from sant_vla_pkg.gz_pose import WorldPoseStream
from sant_vla_pkg.gz_pose import resolve_gz_bin
from sant_vla_pkg.speed_control import DEFAULT_SPEED_RAW
from sant_vla_pkg.speed_control import parse_speed_raw
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import QoSDurabilityPolicy
from rclpy.qos import QoSHistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import QoSReliabilityPolicy
from std_msgs.msg import Bool
from std_msgs.msg import Float32
from std_msgs.msg import Int32
from std_msgs.msg import String
from sensor_msgs.msg import Image

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

try:
    from sant_vla_pkg.action_policy_model import ActionPolicyPredictor
except ImportError:
    ActionPolicyPredictor = None

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


MODEL = "qwen3:4b"
VOICE_SAMPLE_RATE = 16000
WHISPER_MODEL = os.environ.get("SANT_VLA_WHISPER_MODEL", os.environ.get("NAV_VLA_WHISPER_MODEL", "base"))
DEFAULT_MAP_PATH = os.path.expanduser(
    "~/ROS2_project/sant-vla/src/sant_vla_pkg/config/zone_map.yaml"
)
DEFAULT_ACTION_POLICY_CKPT = os.path.expanduser(
    "~/ROS2_project/sant-vla/src/sant_vla_pkg/train/checkpoints/action_policy.pt"
)
DEFAULT_ALPAMAYO_LOG_DIR = os.path.expanduser(
    "~/ROS2_project/sant-vla/src/sant_vla_pkg/logs/alpamayo"
)
SCENE_LOG_ROOT = os.path.expanduser(
    "~/ROS2_project/sant-vla/src/sant_vla_pkg/logs/scene_reasoning"
)
ALPAMAYO_MODEL_ID = "nvidia/Alpamayo-1.5-10B"
ALPAMAYO_REPO_URL = "https://github.com/NVlabs/alpamayo1.5"
ALPAMAYO_HF_URL = "https://huggingface.co/nvidia/Alpamayo-1.5-10B"
ZONE_ALIASES = {
    "t1": "T1/M1",
    "m1": "T1/M1",
    "t1m1": "T1/M1",
    "t1/m1": "T1/M1",
    "m1t1": "T1/M1",
    "m1/t1": "T1/M1",
    "crosswalk": "crosswalk_stop",
    "crosswalkstop": "crosswalk_stop",
    "crosswalk_stop": "crosswalk_stop",
    "횡단보도": "crosswalk_stop",
}
DIRECT_ONLY_ZONES = {
    "IN",
    "OUT(통과직전)",
    "OUT(통과직후)",
    "Slot1",
    "Slot2",
    "Slot3",
    "Slot4",
}
TRACK_CRUISE_ZONES = ("M2", "T2", "M3", "T3", "T4", "Start")
# Canonical corpus-v3y vocabulary for the SmolVLA backend. The policy only
# responds reliably to the exact sentence forms it was trained on, so parsed
# steps are re-rendered with these slot words before publishing.
# lane1 says "left", not "inner": r16 measured a surface-form-specific
# action failure — "Cruise in the inner lane" veers OUTWARD off the ring
# (reproduced from an on-lane1 start), while "the left lane" tracks lane1
# normally (2026-09-15). Both are trained forms; only "inner" is broken.
# NOTE "left" assumes the corpus-default CCW direction; a CW demo must
# switch back to geometric wording.
VLA_LANE_WORDS = {"lane1": "the left lane", "lane2": "the outer lane"}
LANE_KR = {"lane1": "1차선(안쪽)", "lane2": "2차선(바깥쪽)"}
VLA_ZONE_WORDS = {
    "Start": "the start line",
    "T1/M1": "checkpoint T1",
    "T2": "checkpoint T2",
    "M2": "checkpoint M2",
    "M3": "checkpoint M3",
    "T3": "checkpoint T3",
    "T4": "checkpoint T4",
}
# Coordinate-supervised zone stops (smolvla mode): when the navigator reports the
# remaining distance below this threshold, the cruise sentence is re-sent with
# the slow speed word so the VLA approaches the stop point gently.
VLA_PRESLOW_DIST = 8.0
VLA_STATUS_DIST_RE = re.compile(r"\bdist=([0-9]*\.?[0-9]+)")
VLA_STATUS_REASON_RE = re.compile(r"\breason=(\S+)")
# Words that mean "come to a halt". Used to tell a standalone stop apart from a
# positional "stop at <zone>" (drive there, then stop).
STOP_WORD_RE = re.compile(r"stop|halt|pause|정지|멈춰|멈추|세워|세우", re.IGNORECASE)
# Words that tie an action to REACHING a zone (waypoint / position trigger), e.g.
# "at M3", "M3에서", "M3까지 가서", "start 선 지나서", "after M3".
POSITION_TRIGGER_RE = re.compile(r"\bat\b|\bafter\b|에서|지나|까지|도착|reach", re.IGNORECASE)
# Lane-change intent and explicit lane numbers, for reconstructing waypoint plans.
CHANGE_LANE_RE = re.compile(
    r"change\s*to\s*lane|change\s*lane|chane\s*lane|switch\s*lane|lane\s*change|차선\s*변경|차선변경|차로\s*변경", re.IGNORECASE
)
LANE1_RE = re.compile(r"lane\s*1|1\s*차선|first lane|inner lane|left lane", re.IGNORECASE)
LANE2_RE = re.compile(r"lane\s*2|2\s*차선|second lane|outer lane|right lane", re.IGNORECASE)
DIRECT_DRIVE_RE = re.compile(r"direct|shortest|차선\s*무시|최단", re.IGNORECASE)
DRIVE_TO_RE = re.compile(r"\b(go|drive|move|navigate)\b|가|이동|주행", re.IGNORECASE)
STANDALONE_DRIVE_RE = re.compile(
    r"^\s*(go|drive|start|resume|continue|출발|주행|가|계속\s*가)\s*$",
    re.IGNORECASE,
)
SEQUENCE_SPLIT_RE = re.compile(r"\bthen\b|\band\s+then\b|,|그리고|그다음|다음", re.IGNORECASE)
# Explicit phrases that name the Start line as a target. Bare "start" is left out
# on purpose: it collides with the start verb ("start driving").
START_LINE_PHRASES = (
    "start line",
    "start 선",
    "출발선",
    "출발 선",
    "출발지점",
    "출발 지점",
    "스타트 라인",
)
# Ascii zone names that are also common English words, so a bare-word match would
# fire on unrelated text. Matched only through longer explicit phrases instead.
AMBIGUOUS_BARE_ZONES = {"start", "in", "out"}

SYSTEM_TEMPLATE = """You are a ROS 2 driving-command interpreter for a small track car.
The user may write Korean or English.

Return one compact JSON object with an ordered "steps" list. Each step is one
action. A single-intent command has one step; a multi-intent command has one
step per intent, in the order the user stated them. Do not include explanations
outside JSON.

Available actions:
- drive_to_zone: drive along a lane until one listed zone is reached.
- drive_direct: ignore lanes and drive directly to one listed zone.
- change_lane: change to lane1 or lane2, without selecting a zone.
- keep_lane: keep/follow lane1 or lane2, without selecting a zone.
- stop: stop/pause/cancel driving.
- start: start/resume driving.
- set_speed: set the driving speed limit in raw motor units from 0 through 250.
- none: unrelated, unsafe, or impossible request.

Available lanes:
- lane1: 1차선, lane 1, first lane, inner lane, left lane
- lane2: 2차선, lane 2, second lane, outer lane, right lane
- default: use this when the user did not explicitly specify lane1 or lane2

Zones (name : roles):
{zones}

Guidelines:
- If the user is asking a question about whether something is possible, such as
  "가능한가?", "can I", "is it possible", or "할 수 있어?", action=none.
- Position-triggered actions, where the trigger is REACHING a listed zone (words
  like "at <zone>", "<zone>에서", "<zone> 지나서", "after <zone>", "<zone>까지 가서"),
  ARE supported by sequencing through that zone as a waypoint. See the waypoint
  rule below. Time-based or sensor-based triggers ("after 5 seconds", "5초 뒤",
  "when you see an obstacle", "장애물 보이면") are NOT supported: action=none.
- If the user says change lane without specifying lane1/lane2, use the opposite
  of the current lane from the context. If current_lane=lane2, return lane=lane1.
  If current_lane=lane1, return lane=lane2.
- Do NOT change lanes just because the user says "lane", "through lane",
  "차선따라", or "차선으로". If the user asks to go to a zone by lane but does
  not explicitly say lane1/lane2/1차선/2차선, use lane=default so the current
  lane is kept.
- Treat "start line", "start 선", and "출발선" as the Start zone when the user says
  stop at, go to, or drive to that line.
- For commands like "1차선 따라 T2까지 가", one step: drive_to_zone, zone=T2, lane=lane1.
- For commands like "stop at M3", "M3에서 멈춰", "M3까지 가서 정지",
  "go to M3 and stop", or "stop at crosswalk", one step: drive_to_zone with that zone.
- Do not infer a lane from a zone name, target name, or the word "line".
- Do not infer a lane from the word "lane" alone.
- "line", "기준선", "재위치선", and "stop line" mean a target zone/line, not lane1.
- For commands like "go M2 line", one step: drive_to_zone, zone=M2, lane=default.
- For commands like "차선 무시하고 M3로 가", "최단거리로 M3", or "direct to M3",
  one step: drive_direct, zone=M3, lane=default.
- IN, OUT(통과직전), OUT(통과직후), and Slot1~Slot4 are inside the track/parking
  area, not lane-follow targets. For these zones, use drive_direct unless the
  user is only asking a question.
- For commands like "2차선으로 변경", one step: change_lane, lane=lane2, zone=null.
- Treat T1, M1, and T1/M1 as the same zone. Return zone=T1/M1 for all three.
- Treat crosswalk and 횡단보도 as crosswalk_stop. Return zone=crosswalk_stop.
- For standalone "정지", "stop", or "cancel" without a target zone, one step: stop.
- For standalone "출발", "start", "resume", or "continue" without a target zone,
  one step: start.
- "속도 100", "speed 100", or "속도를 100으로" means set_speed with speed=100.
- "천천히" means speed=70, "보통 속도" means speed=150, and "빠르게" means
  speed=200. Relative requests are resolved by the deterministic parser.
- Use only exact zone names from the list.
- If no zone matches for a drive_to_zone request, use action=none for that step.

Merging vs. sequencing:
- MERGE a lane choice with a single destination that is driven in that lane into
  ONE drive_to_zone step, but ONLY when the lane change is not tied to a location.
  "change lane and go to T4" or "change lane and stop at T4" -> one step:
  drive_to_zone, zone=T4, lane=the opposite of current_lane. "start drive and stop
  at T4 on lane1" -> one step: drive_to_zone, zone=T4, lane=lane1.
- WAYPOINT: when the lane change (or other action) is tied to a listed zone AND a
  further destination is given, sequence through the zone. Drive to the waypoint
  zone in the CURRENT lane (lane=default), then drive to the destination in the
  new lane. "M2에서 차선 변경하고 T4까지 가" or "change lane at M2 then go to T4" ->
  two steps: [drive_to_zone zone=M2 lane=default, drive_to_zone zone=T4
  lane=opposite]. The lane switch happens when the car reaches M2, not at the
  start, and M2 is not skipped.
- SEQUENCE when the user states actions to perform in order. Trigger words:
  "first", "then", "after", "next", "and then", "먼저", "그다음", "그리고", "-고
  나서", or two different destinations. Emit one step per intent, in order.
  "Go to start line first, then change lane" -> two steps:
  [drive_to_zone zone=Start lane=default, change_lane lane=opposite].
  "Drive to M2 then to T3" -> [drive_to_zone M2, drive_to_zone T3].
- change_lane already starts motion. So combine start/stop with change-lane into
  ONE step: "start driving and change lane" or "change lane and start driving"
  -> change_lane, lane=opposite. "change lane and stop" or "stop and change lane"
  -> stop (stopping overrides the lane change).

Schema (return exactly this shape):
{{
  "steps": [
    {{
      "action": "drive_to_zone" | "drive_direct" | "change_lane" | "keep_lane" | "stop" | "start" | "set_speed" | "none",
      "zone": <one listed zone name or null>,
      "lane": "lane1" | "lane2" | "default",
      "speed": <integer 0 through 250 or null>
    }}
  ],
  "reason": <short Korean or English reason>
}}"""


class ChatGuiNode(Node):
    def __init__(self):
        super().__init__("sant_vla_chat_gui_node")
        self.control_backend = str(
            self.declare_parameter("control_backend", "qwen").value
        ).strip().lower()
        if self.control_backend not in {"qwen", "smolvla"}:
            raise ValueError(
                "control_backend must be 'qwen' or 'smolvla', got "
                f"{self.control_backend!r}"
            )
        self.map_path = self.declare_parameter("map_path", DEFAULT_MAP_PATH).value
        self.host = self.declare_parameter(
            "ollama_host", "http://localhost:11434"
        ).value.rstrip("/")
        # One model serves both parsing and scene commentary when the demo
        # points ollama_host at the lab-server tunnel (2026-08-28: two local
        # qwen models consolidated into the server's qwen2.5vl:7b).
        self.parser_model = str(
            self.declare_parameter("parser_model", MODEL).value)
        self.timeout = float(self.declare_parameter("timeout", 30.0).value)
        self.parser_backend = str(
            self.declare_parameter("parser_backend", "llm").value
        ).strip().lower()
        # Preload the ollama parser while the sim is still coming up, so the
        # VRAM load spike never coincides with the first driving command
        # (GPU contention with the policy server — see keep_alive note below).
        if self.parser_backend == "llm":
            threading.Thread(target=self._warm_parser, daemon=True).start()
        self.action_policy_ckpt = self.declare_parameter(
            "action_policy_ckpt", DEFAULT_ACTION_POLICY_CKPT
        ).value
        self.nav_goal_topic = self.declare_parameter("nav_goal_topic", "/nav_goal").value
        self.direct_nav_goal_topic = self.declare_parameter(
            "direct_nav_goal_topic", "/direct_nav_goal"
        ).value
        lane_command_topic = self.declare_parameter(
            "lane_command_topic", "/lane_mode_command"
        ).value
        motion_control_topic = self.declare_parameter(
            "motion_control_topic", "/motion_control_command"
        ).value
        speed_command_topic = self.declare_parameter(
            "speed_command_topic", "/speed_command"
        ).value
        self.vla_instruction_topic = self.declare_parameter(
            "vla_instruction_topic", "/vla/instruction"
        ).value
        self.vla_status_topic = self.declare_parameter(
            "vla_status_topic", "/vla/status"
        ).value
        status_topic = self.declare_parameter("status_topic", "/nav_status").value
        lane_state_topic = self.declare_parameter(
            "lane_state_topic", "/lane_mode_state"
        ).value
        detection_topic = self.declare_parameter("detection_topic", "/detections").value
        lane_info_topic = self.declare_parameter(
            "lane_info_topic", "/yolov8_lane_info"
        ).value
        path_topic = self.declare_parameter(
            "path_topic", "/path_planning_result"
        ).value
        odom_topic = self.declare_parameter("odom_topic", "/odom").value
        self.alpamayo_image_topic = self.declare_parameter(
            "alpamayo_image_topic", "/camera/image_raw"
        ).value
        self.alpamayo_image_max_width = int(
            self.declare_parameter("alpamayo_image_max_width", 384).value
        )
        self.alpamayo_image_quality = int(
            self.declare_parameter("alpamayo_image_quality", 75).value
        )
        self.alpamayo_frame_count = int(
            self.declare_parameter("alpamayo_frame_count", 4).value
        )
        self.vla_judgment_backend = str(
            self.declare_parameter("vla_judgment_backend", "local").value
        ).strip().lower()
        self.alpamayo_endpoint = str(
            self.declare_parameter("alpamayo_endpoint", "").value
        ).strip()
        self.alpamayo_model_id = str(
            self.declare_parameter("alpamayo_model_id", ALPAMAYO_MODEL_ID).value
        ).strip()
        self.alpamayo_period = float(
            self.declare_parameter("alpamayo_period", 2.0).value
        )
        self.alpamayo_timeout = float(
            self.declare_parameter("alpamayo_timeout", 3.0).value
        )
        self.alpamayo_log_dir = str(
            self.declare_parameter("alpamayo_log_dir", DEFAULT_ALPAMAYO_LOG_DIR).value
        ).strip()

        self.zones = self._load_zones()
        self.zone_names = list(self.zones)
        self._zone_text_patterns = self._build_zone_text_patterns()
        self.system_prompt = SYSTEM_TEMPLATE.format(zones=self._zone_lines())
        self.policy_goal_mode = (
            "policy" in str(self.nav_goal_topic)
            or "policy" in str(self.direct_nav_goal_topic)
            or "policy" in str(status_topic)
        )
        self.current_lane = "lane2"
        self.current_speed_raw = int(
            self.declare_parameter("initial_speed_raw", DEFAULT_SPEED_RAW).value
        )
        self.current_speed_raw = max(0, min(250, self.current_speed_raw))
        # SmolVLA adapter state: the lane/speed/mode last rendered into a
        # canonical trained sentence. Fast tier (raw 150) is the default.
        self._vla_lane = "lane2"
        # Default cruise tier for bare "start drive": NORMAL (raw 110), not
        # fast. The zero-lane-touch serving config was validated with normal
        # sentences; a fast sentence makes the policy plan fast-style (looser)
        # lines even when the bridge caps executed speed, and the demo
        # visibly touches lanes (2026-08-21).
        self._vla_speed_raw = 110
        self._vla_mode = "idle"
        self._vla_zone = None
        # Coordinate-supervised zone watch (smolvla mode only): the VLA cruises
        # the lane while navigator_node watches gz ground-truth pose and reports
        # arrival on /nav_status. Guarded by its own lock because /nav_status
        # callbacks run on the ROS executor thread while commands come from the
        # GUI/worker threads.
        self._vla_watch_lock = threading.Lock()
        self._vla_watch_zone = None
        # "Go to Z, THEN change lane/speed": the trailing steps wait here and
        # fire on the navigator's arrival signal instead of collapsing into
        # an immediate last-step dispatch (user 2026-09-14).
        self._vla_staged_steps = None
        self._staged_fire = None
        self._vla_direct_zone = None
        self._vla_direct_dist = None
        self.scene_lang = str(self.declare_parameter("scene_lang", "ko").value)
        # LLM-phrased commentary is OPT-IN on this laptop. Measured 2026-08-28:
        # qwen3:4b every second = ~1 CPU core + resident RAM/VRAM (fed the
        # desktop freeze); qwen3:0.6b is fast warm (0.4 s) but echoes the
        # prompt instead of narrating. Empty = dynamic template lines only.
        # Set e.g. scene_model:=qwen3:4b (or a lab-server ollama via
        # ollama_host) to turn LLM phrasing on.
        self.scene_model = str(self.declare_parameter("scene_model", "").value)
        # Where the commentary model serves. Empty = the parser's ollama_host.
        # The demo points this at an ssh tunnel to the lab server's ollama
        # (3090) running a VISION model — the commentary then reasons from the
        # actual camera frame, not from telemetry alone.
        self.scene_host = str(
            self.declare_parameter("scene_host", "").value) or None
        self._scene_log_dir = None
        self._scene_log_seq = 0
        self._vla_watch_preslow = False
        # Serving-layer obstacle avoidance: best_cap.pt was trained with
        # lane-qualified vehicle classes (lane1_car / lane2_car), so YOLO
        # itself reports which lane a blocking car occupies. When the commanded
        # lane's *_car grows past avoid_trigger_px, this node flips _vla_lane
        # and re-renders the cruise sentence — the actual swerve is the
        # policy's own trained lane-change behaviour (ring-lane counterfactual
        # groups in the corpus), not a scripted path. Runs only while the VLA
        # is driving (cruise/zone); the direct (beeline) mode is navigator
        # territory and is left alone.
        self.avoid_enable = bool(self.declare_parameter("avoid_enable", True).value)
        # Trigger when the blocker's bbox is this tall in pixels (640x480
        # frames; ~48 px ≈ a hatchback at roughly 10-15 m — tune on track).
        self.avoid_trigger_px = float(
            self.declare_parameter("avoid_trigger_px", 48.0).value)
        # Return to the home lane after the path has been clear this long...
        self.avoid_clear_s = float(self.declare_parameter("avoid_clear_s", 4.0).value)
        # ...but never sooner than this after the swerve (the blocker leaves
        # the camera FOV while alongside, which would re-trigger too early).
        self.avoid_min_hold_s = float(
            self.declare_parameter("avoid_min_hold_s", 8.0).value)
        self.avoid_cooldown_s = float(
            self.declare_parameter("avoid_cooldown_s", 6.0).value)
        # Primary trigger is the LIDAR detector (/lidar_obstacle_info from
        # lidar_obstacle_detector_node): geometric, works on any obstacle
        # shape. Measured 2026-08-28 16:37: best_cap AND stock COCO yolov8n
        # both fail on the sim's low-poly hatchback exactly when it is
        # front-on and close (the crash approach) — vision stays only as a
        # secondary trigger for when the lidar node is not running.
        # After a lane switch, triggers are suspended for avoid_commit_s:
        # the old obstacle is still inside the forward lidar sector until
        # the swerve actually happens, and reacting to it would bounce the
        # instruction straight back (the old stack's commit_delay).
        self.avoid_commit_s = float(
            self.declare_parameter("avoid_commit_s", 4.0).value)
        # What senses the blockage. "vision" (default): the scene VLM's
        # structured blocking judgment + best_cap *_car — the camera-only
        # story the demo wants. "lidar": the geometric detector only.
        # "any": everything. Benchmarked 2026-08-28 on logged crash frames
        # (qwen2.5vl:7b, temp 0.1, shape-aware prompt): blocked 5/5, clear
        # 5/5, 0.13 s eval on the lab 3090 — but it only turns True at
        # ~8 m, which is why the avoidance sentence also slows the car.
        self.avoid_source = str(
            self.declare_parameter("avoid_source", "vision").value)
        self.avoid_vlm_period = float(
            self.declare_parameter("avoid_vlm_period", 0.6).value)
        self._avoid_home_lane = None       # set while the avoidance detour is active
        self._avoid_started_t = 0.0
        self._avoid_clear_since = None
        self._avoid_last_switch_t = 0.0
        self._lidar_obstacle = False
        self._lidar_obstacle_time = None
        self._lidar_obstacle_dist = None
        self._vlm_blocked = False
        self._vlm_blocked_time = None
        self._vlm_distance = "none"
        self._avoid_stopped = False
        self._avoid_block_reason = "clear"
        self._avoid_lock = threading.RLock()
        # Lane attribution is CODE, not VLM: benchmarked 2026-08-28, the 7B
        # VLM cannot tell same-lane from adjacent-lane (every crash/other
        # frame judged "same") nor even image left/right reliably. So the
        # VLM only answers "is an obstacle visible on the road", and the
        # supervisor resolves WHICH lane from the spawn registry (written by
        # the demo's obstacle spawner) + the ego's gz ground-truth pose —
        # the same infrastructure the navigator's zone watch already uses.
        self.avoid_obstacle_file = str(self.declare_parameter(
            "avoid_obstacle_file", os.path.expanduser(
                "~/ROS2_project/sant-vla/eval_out/demo/obstacles.json")).value)
        self.avoid_range_m = float(
            self.declare_parameter("avoid_range_m", 18.0).value)
        # Coordinate backstop: trigger regardless of the VLM once a
        # registered obstacle in the commanded lane is this close ahead.
        # The 7B VLM has measured hard blind spots (18:10 — a hatchback
        # filling the left third of the frame on a curve judged "no
        # obstacle" under every prompt tried), so vision cannot be the only
        # tripwire.
        self.avoid_coord_trigger_m = float(
            self.declare_parameter("avoid_coord_trigger_m", 17.0).value)
        # Mid-detour, a blocker in the commanded lane only forces a stop
        # once it is this close; farther out the detour keeps rolling — the
        # staggered T7 run stopped with 10 m of clear road left because the
        # 17 m sensing range doubled as the stop line.
        self.avoid_stop_m = float(
            self.declare_parameter("avoid_stop_m", 7.0).value)
        # After passing a blocker: return to the original lane (true) or
        # keep cruising in the detour lane until the next blocker (false —
        # mission style, user 2026-09-10: staggered obstacles make weaving
        # back pointless).
        self.avoid_return_home = bool(
            self.declare_parameter("avoid_return_home", False).value)
        # Traffic-signal stop: the dashboard's 🔴/🟢 buttons write
        # signal.json next to the obstacle registry; on red the car holds
        # at a stop line `signal_stop_before_m` short of the light and
        # releases on green. Discrete stop/go is code by design — the
        # action expert cannot learn the rare stop (r8–r11 finding).
        # 7.6: the painted stop line sits 5.6 m before the pole along lane2
        # (Blender plan_mission marker (0.559,-24.573)); the planned stance
        # is nose 0.55 m before the line, i.e. CENTER ~8.5 m before the
        # pole. The hold engages trigger+brake ~0.9 m past this setpoint
        # (measured), so command 7.6 to land at 8.5.
        self.signal_stop_before_m = float(
            self.declare_parameter("signal_stop_before_m", 7.6).value)
        self.signal_stop_trigger_m = float(
            self.declare_parameter("signal_stop_trigger_m", 1.5).value)
        self._signal_stopped = False
        self._signal_state = None
        self._signal_mtime = None
        self._gz_bin = resolve_gz_bin()
        # Persistent gz pose stream, started lazily on the first sighting.
        # A per-sighting `gz model -p` CLI call spawns a ruby process each
        # time (~150 ms) — with the 0.6 s VLM cadence that visibly stuttered
        # the sim on this laptop (user report 2026-08-28 18:0x).
        self._ego_pose_stream = None
        self._avoid_obstacles = []
        self._avoid_obstacles_mtime = None
        self._obstacle_ahead_lane = None    # "lane1"/"lane2"/"none"/"unknown"
        self._obstacle_ahead_s = None       # longitudinal offset of nearest
        self._obstacle_lane_s = {}          # per-lane nearest offset ahead
        self._obstacle_lanes_ahead = set()  # all lanes with an obstacle ahead
        self._obstacle_ahead_time = None
        # The blocked comparison uses the lane the car is PHYSICALLY in
        # (nearest lane path to the gz pose), not the commanded lane: the
        # 17:36 crash drove down lane1 while the command said lane2, and the
        # commanded-lane comparison dismissed the lane1 obstacle as "not my
        # lane". Falls back to the commanded lane when the pose is off-lane.
        self._ego_actual_lane = None
        self._ego_prev = None               # (x, y, t) for standstill detect
        self._ego_standstill_since = None
        self._avoid_kicks = 0
        self._track_lanes = None
        try:
            with open(os.path.expanduser(
                    "~/ROS2_project/sant-vla/src/sant_vla_pkg/config/"
                    "track_paths.json"), encoding="utf-8") as f:
                paths = json.load(f)
            self._track_lanes = {k: paths[k] for k in ("lane1", "lane2")}
            # Cumulative arclength per lane, for along-the-road distances.
            self._lane_cumlen = {}
            for lane, pts in self._track_lanes.items():
                cum = [0.0]
                for i in range(1, len(pts)):
                    cum.append(cum[-1] + math.hypot(
                        pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]))
                loop = cum[-1] + math.hypot(
                    pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
                self._lane_cumlen[lane] = (cum, loop)
        except Exception as exc:                                # noqa: BLE001
            self.get_logger().warning(f"track_paths unavailable: {exc}")
        self._avoid_log_last = None
        self.last_user_text = "-"
        self.last_action_text = "-"
        self.last_nav_status = "-"
        self.last_drive_step = None
        self.last_arrived_zone = None
        self.latest_detections = []
        self.latest_detection_time = None
        self.latest_lane_info = None
        self.latest_lane_info_time = None
        self.latest_path_info = None
        self.latest_path_time = None
        self.latest_pose = None
        self.latest_pose_time = None
        self.latest_alpamayo_image = None
        self.latest_alpamayo_image_time = None
        self.alpamayo_image_buffer = deque(maxlen=max(1, self.alpamayo_frame_count))
        self.alpamayo_busy = False
        self.alpamayo_last_call = 0.0
        self.alpamayo_last_text = ""
        self.alpamayo_last_error = ""
        self.alpamayo_last_stamp = None
        self.alpamayo_log_jsonl = ""
        self.alpamayo_log_csv = ""
        self._init_alpamayo_logs()
        self.action_policy = None
        if self.parser_backend == "action_policy":
            if ActionPolicyPredictor is None:
                raise RuntimeError("ActionPolicyPredictor import failed")
            self.action_policy = ActionPolicyPredictor(self.action_policy_ckpt)

        transient_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,
            history=QoSHistoryPolicy.KEEP_LAST,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
            depth=1,
        )
        self.nav_goal_pub = self.create_publisher(String, self.nav_goal_topic, 10)
        self.direct_goal_pub = self.create_publisher(String, self.direct_nav_goal_topic, 10)
        self.lane_pub = self.create_publisher(String, lane_command_topic, transient_qos)
        self.motion_pub = self.create_publisher(String, motion_control_topic, transient_qos)
        self.speed_pub = self.create_publisher(Int32, speed_command_topic, transient_qos)
        self.vla_instruction_pub = self.create_publisher(
            String, self.vla_instruction_topic, transient_qos
        )
        # Independent from navigator/reset holds; releasing one supervisor
        # must never release another supervisor's stop.
        self.avoid_hold_pub = self.create_publisher(
            String, "/vla/avoidance_hold", transient_qos)
        self.avoid_hold_pub.publish(String(data="0"))
        self.status_q = queue.Queue()
        self.event_q = queue.Queue()
        self.last_parsed = None
        self.last_dispatch = "-"
        self._plan_lock = threading.Lock()
        self.pending_steps = []
        self._waiting = None
        self.create_subscription(String, status_topic, lambda msg: self._handle_status(msg.data), 10)
        if self.control_backend == "smolvla":
            self.create_subscription(
                String,
                self.vla_status_topic,
                lambda msg: self.status_q.put(msg.data),
                10,
            )
            # Live Korean narration from scripts/vla_narrator.py (telemetry
            # observer, smolvla demo only). Routed through event_q like every
            # other event so the Tk thread is the only one touching widgets.
            self.create_subscription(
                String,
                "/vla/narration",
                lambda msg: self.event_q.put(("narration", msg.data)),
                5,
            )
            # Raw plan chunks for the causal scene commentary: the policy's
            # ACTUAL planned speed profile and turn direction, so "curve seen →
            # slowing down" is read off the model's output, never scripted.
            self._plan_stats = None
            self.create_subscription(
                String, "/vla/plan", self._plan_stats_cb, 5)
            # Track instructions published OUTSIDE this GUI (vla_drive.sh, a
            # test publisher): without this the scene commentary stays silent
            # because _vla_mode never leaves "idle" for external commands.
            self.create_subscription(
                String, self.vla_instruction_topic,
                self._external_instr_cb, 10)
        self.create_subscription(String, lane_state_topic, self._lane_state_cb, transient_qos)
        self.create_subscription(DetectionArray, detection_topic, self._detections_cb, 10)
        self.create_subscription(Bool, "/lidar_obstacle_info", self._lidar_obstacle_cb, 10)
        self.create_subscription(Float32, "/lidar_obstacle_distance",
                                 self._lidar_obstacle_dist_cb, 10)
        self.create_subscription(LaneInfo, lane_info_topic, self._lane_info_cb, 10)
        self.create_subscription(PathPlanningResult, path_topic, self._path_cb, 10)
        self.create_subscription(Odometry, odom_topic, self._odom_cb, 10)
        self.create_subscription(Image, self.alpamayo_image_topic, self._alpamayo_image_cb, 10)

        parser_desc = (
            f"action_policy={self.action_policy_ckpt}"
            if self.parser_backend == "action_policy"
            else f"model={self.parser_model}"
        )
        self.get_logger().info(
            f"chat gui ready: control={self.control_backend}, "
            f"backend={self.parser_backend}, {parser_desc}, "
            f"vla_judgment={self.vla_judgment_backend}, zones={len(self.zone_names)}"
        )

    def dispatch_smolvla_instruction(self, text, parsed_result=None):
        """Translate chat text into a canonical trained sentence for SmolVLA.

        The existing qwen/deterministic parse step (parse_command) interprets
        the text into steps; the steps update the VLA adapter state and are
        re-rendered as a corpus-v3y sentence before publishing. Raw text is
        only published as a fallback when parsing fails.
        """
        instruction = str(text).strip()
        self.last_user_text = instruction or "-"
        # Any new command (including the STOP shortcut) supersedes an active
        # coordinate watch: cancel the navigator goal first.
        self._cancel_vla_zone_watch()
        if not instruction:
            # Empty text is the stop shortcut: clear the bridge queue.
            self._vla_mode = "idle"
            self._vla_zone = None
            self.last_parsed = {"steps": [], "reason": "smolvla stop/queue clear"}
            self.vla_instruction_pub.publish(String(data=""))
            self._set_avoid_stopped(False)
            self.last_dispatch = f"{self.vla_instruction_topic} ''"
            self.last_action_text = "SmolVLA stopped and its action queue was cleared."
            return self.last_action_text

        plan, _latency, error = (
            parsed_result if parsed_result is not None
            else self.parse_command(instruction)
        )
        steps = []
        if plan is not None:
            steps = [
                step for step in plan.get("steps", [])
                if step.get("action") != "none"
            ]
        if error or not steps:
            reason = error or "no usable step"
            self.last_parsed = {
                "steps": [],
                "reason": f"smolvla raw fallback ({reason})",
            }
            self.vla_instruction_pub.publish(String(data=instruction))
            self._set_avoid_stopped(False)
            self.last_dispatch = f"{self.vla_instruction_topic} {instruction!r}"
            self.last_action_text = (
                f"Parse failed ({reason}); raw text was sent to SmolVLA "
                f"instead: {instruction!r}"
            )
            return self.last_action_text

        self.last_parsed = {
            "steps": [dict(step) for step in steps],
            "reason": str(plan.get("reason") or ""),
        }

        # Staged execution — "go to Z, then change lane / set speed": drive
        # the leg now, fire the remaining steps on the navigator's arrival
        # signal, and do NOT stop at Z (the zone is a waypoint here, not a
        # destination). Without this the loop below collapsed to the LAST
        # step: the lane changed immediately and Z was never honoured.
        if (len(steps) > 1 and steps[0].get("action") == "drive_to_zone"
                and steps[0].get("zone") in VLA_ZONE_WORDS
                and not self._is_direct_only_zone(steps[0].get("zone"))
                and all(s.get("action") in {"change_lane", "keep_lane",
                                            "set_speed", "start"}
                        for s in steps[1:])):
            leg = dict(steps[0])
            rest = [dict(s) for s in steps[1:]]
            if any(s["action"] in {"change_lane", "keep_lane"}
                   for s in rest):
                # "at Z change to L" = stay on the CURRENT lane until Z;
                # the parser tends to stamp the target lane on the leg too.
                leg["lane"] = None
            sentence, _leg_note = self._apply_vla_step(leg)
            with self._vla_watch_lock:
                self._vla_staged_steps = rest
            zone = leg.get("zone")
            staged_note = (f"〔예약〕 {zone} 도착 시 나머지 단계"
                           "(차선/속도 변경)를 적용하고 정차 없이 계속 "
                           "주행합니다.")
            parts = [f"Understood: {self._steps_summary(steps)}."]
            if sentence:
                self.vla_instruction_pub.publish(String(data=sentence))
                self.last_dispatch = (
                    f"{self.vla_instruction_topic} {sentence!r} "
                    f"(staged until {zone})")
                parts.append(f'→ VLA: "{sentence}"')
            parts.append(staged_note)
            self.last_action_text = " ".join(parts)
            return self.last_action_text

        sentence = None
        rendered_count = 0
        notes = []
        for step in steps:
            step_sentence, note = self._apply_vla_step(step)
            if note:
                notes.append(note)
            if step_sentence is not None:
                sentence = step_sentence
                rendered_count += 1
        if rendered_count > 1:
            notes.append(
                "SmolVLA has no step sequencing, so only the final sentence was sent."
            )

        parts = [f"Understood: {self._steps_summary(steps)}."]
        if sentence is None:
            self.last_dispatch = "none"
            parts.extend(notes or ["Nothing was sent to SmolVLA."])
            self.last_action_text = " ".join(parts)
            return self.last_action_text

        self.vla_instruction_pub.publish(String(data=sentence))
        self.last_dispatch = f"{self.vla_instruction_topic} {sentence!r}"
        if sentence:
            parts.append(f'→ VLA: "{sentence}"')
        else:
            parts.append("SmolVLA stopped and its action queue was cleared.")
        parts.extend(notes)
        self.last_action_text = " ".join(parts)
        return self.last_action_text

    def _apply_vla_step(self, step):
        """Apply one parsed step to the SmolVLA adapter state.

        Returns (sentence, note). sentence is the canonical instruction to
        publish ("" clears the bridge queue, None publishes nothing); note is
        an optional extra line for the GUI reply.
        """
        action = step["action"]
        lane = step.get("lane")
        zone = step.get("zone")

        # Any explicit user command supersedes an in-flight avoidance detour:
        # forget the detour WITHOUT restoring the old home lane, because the
        # user is redefining the target lane right now.
        self._avoid_home_lane = None
        self._avoid_clear_since = None
        self._set_avoid_stopped(False)
        self._avoid_kicks = 0

        if action == "set_speed":
            speed = max(0, min(250, int(step.get("speed") or 0)))
            self._vla_speed_raw = speed
            self.current_speed_raw = speed
            # In zone mode the VLA is driving a cruise sentence (the navigator
            # supervises the stop), so both modes re-render the cruise form.
            if self._vla_mode in {"cruise", "zone"}:
                return self._vla_cruise_sentence(), None
            return None, (
                f"Speed tier set to '{self._vla_speed_word(speed)}'; it will "
                "apply to the next driving command."
            )

        if action in {"change_lane", "keep_lane"}:
            self._cancel_vla_zone_watch()
            if lane in {"lane1", "lane2"}:
                self._vla_lane = lane
            elif action == "change_lane":
                self._vla_lane = self._opposite_lane(self._vla_lane)
            # No lane-state feedback runs in smolvla mode, so keep the parser
            # context lane in sync with the adapter lane.
            self.current_lane = self._vla_lane
            self._vla_mode = "cruise"
            self._vla_zone = None
            return self._vla_cruise_sentence(), None

        if action == "start":
            self._cancel_vla_zone_watch()
            self._vla_mode = "cruise"
            self._vla_zone = None
            return self._vla_cruise_sentence(), None

        if action == "stop":
            self._cancel_vla_zone_watch()
            self._vla_mode = "idle"
            self._vla_zone = None
            return "", None

        if action in {"drive_to_zone", "drive_direct"}:
            # Shortest-path legs are delegated to the coordinate navigator: the
            # VLA cannot ground zone identity from the visually uniform track
            # (v8/v8g/v8h probes, docs/ver/20260824_1138). The VLA is silenced
            # ("" clears the bridge queue) and navigator_node drives via its
            # direct-mode Twist output; arrival comes back on /nav_status.
            if action == "drive_direct" or self._is_direct_only_zone(zone):
                if zone not in self.zone_names:
                    return None, (
                        f"Zone {zone} is not in the navigator map; nothing was sent."
                    )
                self._vla_mode = "direct"
                self._vla_zone = zone
                with self._vla_watch_lock:
                    self._vla_direct_zone = zone
                self.direct_goal_pub.publish(String(data=zone))
                return "", (
                    f"최단거리 구간은 좌표 내비게이터가 담당합니다 — VLA 정지 후 "
                    f"navigator가 {zone}까지 직행 (도착 시 자동 정차)."
                )
            if zone not in VLA_ZONE_WORDS:
                return None, (
                    f"Zone {zone} is not a trained SmolVLA target; nothing was sent."
                )
            notes = []
            if lane in {"lane1", "lane2"}:
                self._vla_lane = lane
                self.current_lane = lane
            # Coordinate-supervised stop: the camera-only policy cannot localize
            # zones on the visually uniform track, so the VLA just cruises the
            # lane while navigator_node watches the coordinates and this node
            # stops the VLA on the "arrived:" status.
            self._vla_mode = "zone"
            self._vla_zone = zone
            self._start_vla_zone_watch(zone)
            notes.append(f"+ navigator가 {zone} 좌표 감시(도착 시 정차)")
            return self._vla_cruise_sentence(), " ".join(notes)

        return None, None

    def _start_vla_zone_watch(self, zone):
        """Send the zone goal to navigator_node so it watches gz ground-truth
        pose for arrival. Its motor-side commands are inert in the VLA demo
        stack (perception/motion_planner are not running), so it acts purely as
        a coordinate arrival supervisor.
        """
        with self._vla_watch_lock:
            self._vla_watch_zone = zone
            self._vla_watch_preslow = False
        payload = {"zone": zone, "lane": self._vla_lane}
        self.nav_goal_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))

    def _cancel_vla_zone_watch(self):
        """Cancel an active coordinate watch or direct leg (no-op when idle)."""
        with self._vla_watch_lock:
            active = self._vla_watch_zone is not None
            direct_active = self._vla_direct_zone is not None
            self._vla_watch_zone = None
            self._vla_watch_preslow = False
            self._vla_direct_zone = None
            self._vla_direct_dist = None
            self._vla_staged_steps = None
        if active:
            self.nav_goal_pub.publish(String(data="stop"))
        if direct_active:
            self.direct_goal_pub.publish(String(data="stop"))

    def _handle_vla_watch_status(self, text):
        """React to /nav_status while a coordinate zone watch is active.

        Runs on the ROS executor thread; chat lines therefore go through
        event_q, which the Tk thread drains (never touch Tk directly here).
        """
        with self._vla_watch_lock:
            direct_zone = self._vla_direct_zone
            if direct_zone is not None:
                if text.startswith("direct moving:"):
                    match = VLA_STATUS_DIST_RE.search(text)
                    if match:
                        self._vla_direct_dist = float(match.group(1))
                    return
                if text.startswith("direct arrived:"):
                    parts = text.split(None, 2)
                    if len(parts) >= 3 and self._zone_match(parts[2], direct_zone):
                        self._vla_direct_zone = None
                        self._vla_direct_dist = None
                        self._vla_mode = "idle"
                        self._vla_zone = None
                        self.event_q.put((
                            "assistant",
                            f"도착: {direct_zone} — 좌표 내비게이터 직행 완료, 정차.",
                        ))
                    return
            zone = self._vla_watch_zone
            if zone is None:
                return
            if text.startswith("moving:") and not self._vla_watch_preslow:
                if self._vla_staged_steps is not None:
                    return          # waypoint pass-through: no pre-slow
                match = VLA_STATUS_DIST_RE.search(text)
                if match is None:
                    return
                dist = float(match.group(1))
                if dist >= VLA_PRESLOW_DIST:
                    return
                # Pre-slow stage: re-render the cruise sentence with the slow
                # speed word. _vla_speed_raw is left untouched so the user's
                # tier applies again to later commands.
                self._vla_watch_preslow = True
                sentence = self._vla_cruise_sentence(speed_word="slowly")
                self.vla_instruction_pub.publish(String(data=sentence))
                self.last_dispatch = f"{self.vla_instruction_topic} {sentence!r}"
                self.event_q.put((
                    "assistant",
                    f"{zone} 접근(dist={dist:.1f}m) — 감속 주행으로 전환. "
                    f'→ VLA: "{sentence}"',
                ))
                return
            if text.startswith("arrived:"):
                parts = text.split(None, 2)
                if len(parts) < 2 or not self._zone_match(parts[1], zone):
                    return
                self._vla_watch_zone = None
                self._vla_watch_preslow = False
                staged = self._vla_staged_steps
                self._vla_staged_steps = None
                if staged:
                    # Waypoint reached: fire the queued steps OUTSIDE this
                    # lock (change_lane re-enters _vla_watch_lock via
                    # _cancel_vla_zone_watch) and keep driving — no stop.
                    self.nav_goal_pub.publish(String(data="stop"))
                    self._staged_fire = (zone, staged)
                else:
                    self._vla_mode = "idle"
                    self._vla_zone = None
                    self.vla_instruction_pub.publish(String(data=""))
                    self.nav_goal_pub.publish(String(data="stop"))
                    self.last_dispatch = (
                        f"{self.vla_instruction_topic} '' (arrived {zone})")
                    message = (f"도착: {zone} — 좌표 감독으로 정차 "
                               "(VLA 주행 + navigator 감시)")
                    reason_match = VLA_STATUS_REASON_RE.search(text)
                    if reason_match:
                        message += f" [reason={reason_match.group(1)}]"
                    self.event_q.put(("assistant", message))
                    return
            if text.startswith("error:"):
                self._vla_watch_zone = None
                self._vla_watch_preslow = False
                self._vla_mode = "idle"
                self._vla_zone = None
                self.vla_instruction_pub.publish(String(data=""))
                self.last_dispatch = f"{self.vla_instruction_topic} '' (navigator error)"
                self.event_q.put((
                    "assistant",
                    f"navigator 오류로 좌표 감시를 중단하고 정지했습니다: {text}",
                ))
        # Staged waypoint follow-up, applied outside _vla_watch_lock.
        fire = self._staged_fire
        if fire is None:
            return
        self._staged_fire = None
        fired_zone, staged = fire
        sentence = None
        for step in staged:
            step_sentence, _note = self._apply_vla_step(step)
            if step_sentence is not None:
                sentence = step_sentence
        if sentence:
            self.vla_instruction_pub.publish(String(data=sentence))
            self.last_dispatch = (
                f"{self.vla_instruction_topic} {sentence!r} "
                f"(staged after {fired_zone})")
        self.event_q.put((
            "assistant",
            f"📍 {fired_zone} 도착 — 예약된 단계 실행, 정차 없이 계속 "
            f"주행합니다." + (f' → VLA: "{sentence}"' if sentence else ""),
        ))

    def _vla_cruise_sentence(self, speed_word=None):
        word = speed_word or self._vla_speed_word(self._vla_speed_raw)
        return f"Start driving in {VLA_LANE_WORDS[self._vla_lane]}, {word}."

    @staticmethod
    def _vla_speed_word(speed_raw):
        if speed_raw <= 90:
            return "slowly"
        if speed_raw <= 130:
            return "at a normal speed"
        return "at a fast speed"

    def _init_alpamayo_logs(self):
        # Only the Alpamayo judgment backend produces these records. In local
        # mode we skip log/CSV/image creation entirely.
        if self.vla_judgment_backend != "alpamayo":
            return
        if not self.alpamayo_log_dir:
            return
        os.makedirs(self.alpamayo_log_dir, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.alpamayo_log_jsonl = os.path.join(
            self.alpamayo_log_dir,
            f"alpamayo_judgments_{stamp}.jsonl",
        )
        self.alpamayo_log_csv = os.path.join(
            self.alpamayo_log_dir,
            f"alpamayo_judgments_{stamp}.csv",
        )
        self.alpamayo_image_dir = os.path.join(self.alpamayo_log_dir, "images", stamp)
        os.makedirs(self.alpamayo_image_dir, exist_ok=True)
        with open(self.alpamayo_log_csv, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self._alpamayo_log_fields())
            writer.writeheader()

    @staticmethod
    def _alpamayo_log_fields():
        return [
            "time",
            "model",
            "source",
            "command",
            "steps",
            "current_lane",
            "nav_status",
            "dispatch",
            "pose",
            "image_count",
            "image_files",
            "reasoning",
            "endpoint",
        ]

    def _lane_state_cb(self, msg):
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        lane = str(payload.get("current_lane") or "").strip().lower()
        if lane in {"lane1", "lane2"}:
            self.current_lane = lane

    def _external_instr_cb(self, msg):
        """Keep _vla_mode in sync with the instruction actually driving the
        bridge, including our own publishes (idempotent) and external ones."""
        text = msg.data.strip()
        with self._vla_watch_lock:
            direct_active = self._vla_direct_zone is not None
        # An instruction we did not send ourselves supersedes an in-flight
        # avoidance detour, exactly like a GUI command (T11: an external
        # republish of the original sentence left cmd==home and wedged the
        # state machine).
        if (self._avoid_home_lane is not None
                and (not text or text not in self.last_dispatch)):
            self._avoid_home_lane = None
            self._avoid_clear_since = None
            self._set_avoid_stopped(False)
        # Keep the adapter lane in sync with the sentence actually driving the bridge (external publishers included), so the avoidance supervisor compares against the real commanded lane.
        low = text.lower()
        if "inner lane" in low:
            self._vla_lane = "lane1"
        elif "outer lane" in low:
            self._vla_lane = "lane2"
        # Speed tier too, or an avoidance re-render silently changes the externally commanded pace (observed: "slowly" became "at a normal speed" on return-home).
        if "slowly" in low:
            self._vla_speed_raw = 70
        elif "normal speed" in low:
            self._vla_speed_raw = 110
        elif "fast" in low:
            self._vla_speed_raw = 150
        if text and self._vla_mode == "idle":
            self._vla_mode = "cruise"
        elif not text and not direct_active and self._vla_mode in {"cruise", "zone"}:
            self._vla_mode = "idle"
            self._vla_zone = None
            self._cancel_vla_zone_watch()

    def _plan_stats_cb(self, msg):
        try:
            actions = json.loads(msg.data).get("actions") or []
        except (json.JSONDecodeError, TypeError):
            return
        if len(actions) < 10:
            return
        v_front = sum(abs(a[0]) for a in actions[:5]) / 5.0 * 10.0
        v_end = sum(abs(a[0]) for a in actions[-5:]) / 5.0 * 10.0
        yaw_sum = sum(a[2] for a in actions)
        self._plan_stats = (time.monotonic(), v_front, v_end, yaw_sum)

    def scene_facts(self):
        """Live facts for the scene commentary: what the camera pipeline sees
        and what the policy's own action chunk actually plans. Returns None
        while idle. The percept calls a segment a curve when EITHER the lane
        gradient bends OR the policy is steering through it — the S-curve
        apex looks vertical to the camera (slope≈0) while the chunk clearly
        turns, which is exactly the case the slope-only judgment misread."""
        with self._vla_watch_lock:
            direct_zone = self._vla_direct_zone
            direct_dist = self._vla_direct_dist
        if direct_zone is not None:
            return {"kind": "direct", "zone": direct_zone, "dist": direct_dist}
        if self._vla_mode == "idle":
            return None
        dets = self._fresh(self.latest_detections, self.latest_detection_time, [])
        lane = self._fresh(self.latest_lane_info, self.latest_lane_info_time)
        pose = self._fresh(self.latest_pose, self.latest_pose_time)
        plan = self._plan_stats
        if plan is None or time.monotonic() - plan[0] > 4.0:
            return {"kind": "waiting"}
        _, v_front, v_end, yaw_sum = plan
        v_now = abs(float(pose.get("speed") or 0.0)) if pose else v_front
        # lane1/lane2 are lane markings; lane1_car/lane2_car ARE obstacles.
        others = [d for d in dets
                  if str(d["class"]) not in {"lane1", "lane2"}]
        # The VLM blocking judge and the lidar both see obstacles that
        # best_cap misses (front-on low-poly cars, primitive shapes):
        # surface either as a generic obstacle for the commentary.
        now_m = time.monotonic()
        vlm_sees = (self._vlm_blocked and self._vlm_blocked_time is not None
                    and now_m - self._vlm_blocked_time < 3.0)
        lidar_sees = (self._lidar_obstacle
                      and self._lidar_obstacle_time is not None
                      and now_m - self._lidar_obstacle_time < 1.5)
        if not others and (vlm_sees or lidar_sees):
            others = [{"class": "obstacle"}]
        # slope: dominant lane gradient in DEGREES from vertical
        # (lane_info_extractor: dominant_gradient, theta_limit=70).
        slope = abs(float(lane.get("slope") or 0.0)) if lane else None
        turning = abs(yaw_sum) >= 0.35
        if others:
            kind = "obstacle"
        elif (slope is not None and slope >= 8.0) or turning:
            kind = "curve"
        elif slope is not None:
            kind = "straight"
        else:
            kind = "blind"
        return {
            "kind": kind,
            "obstacle": others[0]["class"] if others else None,
            "slope_deg": round(slope, 1) if slope is not None else None,
            "v_now": round(v_now, 2),
            "v_plan_end": round(v_end, 2),
            "dv": round(v_end - v_now, 2),
            "turn": ("left" if yaw_sum > 0.35
                     else "right" if yaw_sum < -0.35 else None),
            "goal_zone": self._vla_zone if self._vla_mode == "zone" else None,
        }

    def scene_template_line(self, facts):
        """Deterministic fallback line when the LLM is slow or down."""
        ko = self.scene_lang != "en"
        k = facts["kind"]
        if k == "direct":
            d = facts.get("dist")
            if ko:
                return (f"🧭 좌표 기반으로 {facts['zone']}까지 직행 중"
                        + (f", 남은 거리 {d:.1f} m" if d is not None else ""))
            return (f"🧭 beeline to {facts['zone']} on coordinates"
                    + (f", {d:.1f} m to go" if d is not None else ""))
        if k == "waiting":
            return "👀 계획 수신 대기 중" if ko else "👀 waiting for the first plan"
        v, ve, dv, turn = (facts["v_now"], facts["v_plan_end"],
                           facts["dv"], facts["turn"])
        ob_kr = {"lane1_car": "1차선 전방 차량", "lane2_car": "2차선 전방 차량",
                 "obstacle": "장애물",
                 "traffic_light": "신호등"}.get(facts.get("obstacle"),
                                              facts.get("obstacle"))
        ob_en = {"lane1_car": "a car in lane 1", "lane2_car": "a car in lane 2",
                 "obstacle": "an obstacle",
                 "traffic_light": "a traffic light"}.get(facts.get("obstacle"),
                                                         facts.get("obstacle"))
        if ko:
            head = {"obstacle": f"전방에 {ob_kr} 보임",
                    "curve": "곡선 구간", "straight": "직선 구간",
                    "blind": "차선 인식 없음"}[k]
            act = (f"감속 ({v:.1f}→{ve:.1f} m/s)" if dv < -0.15
                   else f"가속 (→{ve:.1f} m/s)" if dv > 0.15
                   else f"{v:.1f} m/s 유지")
            tail = {"left": ", 왼쪽 조향", "right": ", 오른쪽 조향"}.get(turn, "")
        else:
            head = {"obstacle": f"{ob_en} ahead",
                    "curve": "curve section", "straight": "straight section",
                    "blind": "no lane fix"}[k]
            act = (f"slowing {v:.1f}→{ve:.1f} m/s" if dv < -0.15
                   else f"speeding up to {ve:.1f} m/s" if dv > 0.15
                   else f"holding {v:.1f} m/s")
            tail = {"left": ", steering left", "right": ", steering right"}.get(turn, "")
        return f"👀 {head} — {act}{tail}"

    def scene_llm_line(self, facts, history):
        """One short human-sounding commentary sentence from the local LLM,
        grounded ONLY in the live facts. Returns None on any failure so the
        caller can fall back to the template. The facts are pre-rendered in
        the target language (the template line minus its emoji): a small model
        given English JSON keys was measured to echo them verbatim instead of
        following a translate instruction."""
        ko = self.scene_lang != "en"
        facts_line = self.scene_template_line(facts).lstrip("👀🧭💭 ").strip()
        # The actual forward camera frame (≤2 s old): with it the model
        # explains WHY from what it sees; without it, from telemetry alone.
        frame = self._fresh(self.latest_alpamayo_image,
                            self.latest_alpamayo_image_time)
        images = [frame["data"]] if frame else None
        # Prompt shape matters more than language here (measured on
        # qwen2.5vl:7b with a road-blocking cube in frame): the long
        # "explain WHY the car does the action below" framing anchored the
        # model on justifying the action and it dropped visible obstacles in
        # both ko and en; quoting the previous line ("최근 말과 다르게: …")
        # made it copy that line verbatim. A short prompt with a mandatory
        # "objects" inventory field answered 3/3 with the obstacle and 0
        # false positives on clear frames — so dedup stays in the caller,
        # not in the prompt.
        if ko:
            see = ("사진은 차량 전방 카메라 실시간 화면이다. "
                   if images else "실측 상황만 근거로 하라. ")
            prompt = (
                "너는 자율주행차가 스스로 판단을 중계하는 내레이터다. "
                f"{see}objects: 도로 위나 도로변에 실제로 보이는 물체·장애물을 "
                "짧게 나열하라(없으면 '없음'). line: 그 물체와 도로 모양을 "
                "근거로 차의 현재 행동 이유를 자연스러운 한국어 1~2문장"
                "(35단어 이내)으로 설명하라. 물체가 있으면 line에서 꼭 "
                "언급하라. 사진에 없는 것은 지어내지 말라. 이모지 금지, "
                "영어 금지, 행동 문구를 그대로 베끼지 말 것.\n"
                f"현재 행동: {facts_line}"
            )
        else:
            see = ("The photo is the live forward camera. "
                   if images else "Use only the measured situation. ")
            prompt = (
                "You narrate an autonomous car's own reasoning. "
                f"{see}objects: briefly list objects/obstacles actually "
                "visible on or beside the road ('none' if none). line: 1-2 "
                "natural English sentences (max 30 words) explaining WHY "
                "the car is doing the action below, grounded in those "
                "objects and the road shape; always mention a listed "
                "object. Don't invent what is not in the photo, no emoji, "
                "don't copy the action wording.\n"
                f"CURRENT ACTION: {facts_line}"
            )
        payload = {
            "model": self.scene_model, "stream": False, "think": False,
            # Free-text generation leaks qwen3's chain-of-thought into the
            # content (measured); a format schema suppresses it and returns
            # exactly one clean line quickly. "objects" comes first so the
            # model inventories the scene before composing the line.
            "format": {"type": "object",
                       "properties": {"objects": {"type": "string"},
                                      "line": {"type": "string"}},
                       "required": ["objects", "line"]},
            "messages": [{"role": "user", "content": prompt,
                          **({"images": images} if images else {})}],
            "options": {"temperature": 0.9, "num_predict": 200},
            "keep_alive": "30m",
        }
        request = urllib.request.Request(
            f"{self.scene_host or self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        t_req = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=8.0) as response:
                body = json.loads(response.read().decode("utf-8"))
            content = str((body.get("message") or {}).get("content") or "")
            parsed = json.loads(content)
            raw_line = str(parsed.get("line") or "").strip()
            objects = str(parsed.get("objects") or "").strip()
        except Exception:                                       # noqa: BLE001
            return None
        latency_ms = (time.monotonic() - t_req) * 1000.0
        # Validate before showing: strip stray symbols the model may echo,
        # enforce the selected language (Hangul required in ko mode), and
        # reject degenerate output — otherwise fall back to the template.
        line = re.sub(r"^[^0-9A-Za-z가-힣]+", "", raw_line).strip()
        # The model was seen chaining near-duplicates with " / " and drifting
        # into hanja: keep only the first "/"-segment, cap at two sentences
        # and ~120 chars, and reject any CJK-ideograph output in ko mode.
        line = line.split(" / ")[0].split(" /", 1)[0].strip()
        line = " ".join(re.split(r"(?<=[.!?다])\s+", line)[:2]).strip()
        line = line.split("최근 말")[0].strip()[:120].strip()
        if len(line) < 5 or "xxx" in line.lower():
            line = ""
        elif re.search(r"[一-鿿぀-ヿ]", line):
            line = ""      # hanja/kana leakage
        else:
            has_hangul = re.search(r"[가-힣]", line) is not None
            if (ko and not has_hangul) or (not ko and has_hangul):
                line = ""
        # Keep the model's scene inventory visible in the log for auditing
        # what it actually saw, without changing the shown line.
        self._scene_log(facts, images,
                        (f"[objects: {objects}] {raw_line}"
                         if objects else raw_line),
                        line, latency_ms)
        return f"💭 {line}" if line else None

    def _scene_log(self, facts, images, raw_line, shown_line, latency_ms):
        """Persist (camera frame, reasoning) pairs for offline inspection:
        logs/scene_reasoning/session_*/frames/NNNNNN.jpg + log.csv. Requested
        2026-08-28 to verify what the vision model actually saw (e.g. an
        obstacle box present in gz but never mentioned in the commentary)."""
        try:
            if self._scene_log_dir is None:
                stamp = time.strftime("%Y%m%d_%H%M%S")
                self._scene_log_dir = os.path.join(
                    SCENE_LOG_ROOT, f"session_{stamp}")
                os.makedirs(os.path.join(self._scene_log_dir, "frames"),
                            exist_ok=True)
                with open(os.path.join(self._scene_log_dir, "log.csv"),
                          "w", newline="", encoding="utf-8-sig") as f:
                    csv.writer(f).writerow(
                        ["seq", "wall_time", "frame_file", "kind", "facts",
                         "raw_line", "shown_line", "rejected", "latency_ms",
                         "model", "lang"])
            self._scene_log_seq += 1
            frame_file = ""
            if images:
                frame_file = f"frames/{self._scene_log_seq:06d}.jpg"
                with open(os.path.join(self._scene_log_dir, frame_file),
                          "wb") as f:
                    f.write(base64.b64decode(images[0]))
            with open(os.path.join(self._scene_log_dir, "log.csv"),
                      "a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow(
                    [self._scene_log_seq,
                     time.strftime("%Y-%m-%d %H:%M:%S"), frame_file,
                     facts.get("kind"), json.dumps(facts, ensure_ascii=False),
                     raw_line, shown_line,
                     "" if shown_line else "REJECTED", f"{latency_ms:.0f}",
                     self.scene_model, self.scene_lang])
        except Exception as exc:                                 # noqa: BLE001
            self.get_logger().warn(f"scene log write failed: {exc}")

    def start_scene_worker(self):
        """Commentary producer thread: ~1 line/s, LLM-phrased when the local
        model answers in time, template otherwise. Lines go through event_q so
        only the Tk thread touches widgets."""
        def loop():
            history = []
            last_key, last_llm_t = None, 0.0
            while rclpy.ok():
                t0 = time.monotonic()
                facts = self.scene_facts()
                if facts is None:
                    time.sleep(1.0)
                    continue
                # Generate only when the situation actually changed, plus a
                # heartbeat every few seconds — a per-second unconditional
                # generation measured as a full CPU core and fed the laptop's
                # RAM/swap freeze.
                key = (facts.get("kind"), facts.get("turn"),
                       facts.get("goal_zone"), facts.get("zone"),
                       (facts.get("dv") or 0) > 0.15,
                       (facts.get("dv") or 0) < -0.15)
                if key != last_key or t0 - last_llm_t >= 4.0:
                    line = (self.scene_llm_line(facts, history[-3:])
                            if self.scene_model else None)
                    if line is None:
                        line = self.scene_template_line(facts)
                    last_key, last_llm_t = key, time.monotonic()
                    if not history or line != history[-1]:
                        history.append(line)
                        del history[:-6]
                        self.event_q.put(("scene", line))
                time.sleep(max(0.1, 1.0 - (time.monotonic() - t0)))
        threading.Thread(target=loop, daemon=True).start()
        self._start_avoid_vlm_watcher()

    def _start_avoid_vlm_watcher(self):
        """Camera-only blocking judge: every avoid_vlm_period the live frame
        goes to the scene VLM with a tiny structured yes/no query, and the
        verdict feeds _avoid_check. Needs a vision scene_model (the demo's
        qwen2.5vl on the lab 3090; ~0.13 s eval, ~1 s round trip). Runs in
        its own thread so a slow/dead tunnel never blocks the GUI."""
        if not self.scene_model or self.avoid_source == "lidar":
            return
        # Warm the gz pose stream now: lazily starting it on the first
        # sighting left the first blocked-verdict without coordinates.
        if self._ego_pose_stream is None:
            self._ego_pose_stream = WorldPoseStream(
                self._gz_bin, "ego_vehicle").start()

        def loop():
            while True:
                t0 = time.monotonic()
                try:
                    if (self.avoid_enable
                            and self._vla_mode in {"cruise", "zone"}):
                        frame = self._fresh(self.latest_alpamayo_image,
                                            self.latest_alpamayo_image_time,
                                            max_age=1.0)
                        if frame:
                            verdict = self._vlm_blocking_query(frame["data"])
                            if verdict is not None:
                                (self._vlm_blocked,
                                 self._vlm_distance) = verdict
                                self._vlm_blocked_time = time.monotonic()
                                # Every cycle, not only on sightings: the
                                # return-home decision needs fresh "which
                                # lanes are blocked ahead" precisely when
                                # nothing is sighted any more. Cheap now —
                                # a pose-stream read, no subprocess.
                                self._avoid_check()
                except Exception as exc:                        # noqa: BLE001
                    self.get_logger().warning(f"vlm blocking watcher: {exc}")
                time.sleep(max(0.2, self.avoid_vlm_period
                               - (time.monotonic() - t0)))
        threading.Thread(target=loop, daemon=True).start()

    # Benchmarked wording (2026-08-28, sessions 162124/163726 frames):
    # enumerating the primitive shapes is what makes the cube/cone/cylinder
    # count as obstacles — "any object or vehicle" alone missed them. This
    # question deliberately stops at "is one visible": every attempt to get
    # lane identity out of the 7B model (same/other lane, image left/right)
    # collapsed to a single answer on real frames, so WHICH lane comes from
    # coordinates instead (_update_obstacle_ahead).
    VLM_BLOCKING_PROMPT = (
        "Forward camera of a car on a simulated track. Look for ANY object "
        "on the road surface — a vehicle, box, cone, cylinder, sphere or "
        "other obstacle — at ANY distance, even small/far ones. "
        "obstacle_on_road: is one visible on the road? "
        "distance: how far it looks.")

    def _vlm_blocking_query(self, image_b64):
        """One structured sighting judgment. Returns (seen, distance) or
        None; seen = some obstacle is visible on the road."""
        payload = {
            "model": self.scene_model, "stream": False, "think": False,
            "format": {"type": "object",
                       "properties": {
                           "obstacle_on_road": {"type": "boolean"},
                           "distance": {"type": "string",
                                        "enum": ["near", "mid", "far",
                                                 "none"]}},
                       "required": ["obstacle_on_road", "distance"]},
            "messages": [{"role": "user",
                          "content": self.VLM_BLOCKING_PROMPT,
                          "images": [image_b64]}],
            "options": {"temperature": 0.1, "num_predict": 80},
            "keep_alive": "30m",
        }
        request = urllib.request.Request(
            f"{self.scene_host or self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=4.0) as response:
                body = json.loads(response.read().decode("utf-8"))
            parsed = json.loads(
                str((body.get("message") or {}).get("content") or ""))
            return (bool(parsed.get("obstacle_on_road")),
                    str(parsed.get("distance") or "none"))
        except Exception:                                       # noqa: BLE001
            return None

    def _load_avoid_obstacles(self):
        """(Re)load the spawn registry when its mtime changes."""
        try:
            mtime = os.path.getmtime(self.avoid_obstacle_file)
        except OSError:
            self._avoid_obstacles = []
            self._avoid_obstacles_mtime = None
            return
        if mtime == self._avoid_obstacles_mtime:
            return
        try:
            with open(self.avoid_obstacle_file, encoding="utf-8") as f:
                entries = json.load(f)
            self._avoid_obstacles = [
                {"entity": str(e.get("entity") or "?"),
                 "x": float(e["x"]), "y": float(e["y"]),
                 "lane": str(e.get("lane") or "unknown")}
                for e in entries]
            self._avoid_obstacles_mtime = mtime
        except Exception as exc:                                # noqa: BLE001
            self.get_logger().warning(f"obstacle registry: {exc}")

    def _update_obstacle_ahead(self):
        """Cache which lane holds the nearest registered obstacle ahead,
        from gz ground-truth ego pose + the spawn registry. "unknown" when
        either side is unavailable — _path_blocked then falls back to the
        VLM's distance alone."""
        self._load_avoid_obstacles()
        now = time.monotonic()
        # Invalidate the whole snapshot together. A dead pose stream must not
        # make old lane distances look like a fresh clear road.
        self._obstacle_ahead_lane = "unknown"
        self._obstacle_ahead_s = None
        self._obstacle_lanes_ahead = set()
        self._obstacle_lane_s = {}
        self._obstacle_ahead_time = None
        self._ego_actual_lane = None
        if not self._avoid_obstacles:
            return
        if self._ego_pose_stream is None:
            self._ego_pose_stream = WorldPoseStream(
                self._gz_bin, "ego_vehicle").start()
        pose = self._ego_pose_stream.latest
        if pose is None or now - self._ego_pose_stream.received_at > 1.5:
            return
        x, y, yaw = pose
        # Standstill tracking for the mid-detour kick.
        if self._ego_prev is None or math.hypot(
                x - self._ego_prev[0], y - self._ego_prev[1]) > 0.15:
            self._ego_prev = (x, y, now)
            self._ego_standstill_since = None
        elif self._ego_standstill_since is None:
            self._ego_standstill_since = now
        # gz body yaw is +90 deg from the travel direction (measured; same
        # convention as navigator's yaw_offset=-pi/2).
        motion_yaw = yaw - math.pi / 2.0
        hx, hy = math.cos(motion_yaw), math.sin(motion_yaw)
        self._ego_actual_lane = self._nearest_lane(x, y)
        best = None
        lanes_ahead = set()
        lane_s = {}
        for ob in self._avoid_obstacles:
            # ALONG-THE-LANE distance (see _arc_ahead) — an obstacle
            # alongside (s≈0) still blocks its lane; clear only once it is
            # 2 m behind. Falls back to Euclidean longitudinal offset when
            # track data is missing.
            if ob["lane"] in ("lane1", "lane2"):
                s = self._arc_ahead(ob["lane"], x, y, hx, hy,
                                    ob["x"], ob["y"])
            else:
                s = None
            if s is None:
                dx, dy = ob["x"] - x, ob["y"] - y
                s = dx * hx + dy * hy
            if s < -2.0 or s > self.avoid_range_m:
                continue
            lanes_ahead.add(ob["lane"])
            if ob["lane"] not in lane_s or s < lane_s[ob["lane"]]:
                lane_s[ob["lane"]] = s
            if best is None or s < best[0]:
                best = (s, ob["lane"])
        self._obstacle_ahead_lane = best[1] if best else "none"
        self._obstacle_ahead_s = best[0] if best else None
        self._obstacle_lanes_ahead = lanes_ahead
        self._obstacle_lane_s = lane_s
        self._obstacle_ahead_time = now

    def _arc_ahead(self, lane, ex, ey, hx, hy, ox, oy):
        """Signed ALONG-THE-LANE distance from the ego to an obstacle on
        `lane` (positive = ahead in the travel direction, negative =
        behind), or None without track data.

        Euclidean longitudinal distance was wrong on this compact ring: on
        a curve, a car parked on the OPPOSITE straight measures "15 m
        ahead" across the infield while being half a lap away by road
        (user-observed 20:21 — phantom lane change at the curve).
        """
        if not self._track_lanes:
            return None
        pts = self._track_lanes[lane]
        n = len(pts)
        ei = min(range(n), key=lambda k: (pts[k][0] - ex) ** 2
                 + (pts[k][1] - ey) ** 2)
        oi = min(range(n), key=lambda k: (pts[k][0] - ox) ** 2
                 + (pts[k][1] - oy) ** 2)
        tx = pts[(ei + 1) % n][0] - pts[ei][0]
        ty = pts[(ei + 1) % n][1] - pts[ei][1]
        sign = 1.0 if (tx * hx + ty * hy) >= 0.0 else -1.0
        cum, loop = self._lane_cumlen[lane]
        fwd = ((cum[oi] - cum[ei]) * sign) % loop
        return fwd if fwd <= loop / 2.0 else fwd - loop

    def _nearest_lane(self, x, y, max_off=2.2):
        """The lane path physically nearest to (x, y), or None off-lane."""
        if not self._track_lanes:
            return None
        best = (None, max_off)
        for lane, pts in self._track_lanes.items():
            d = min(math.hypot(px - x, py - y) for px, py in pts)
            if d < best[1]:
                best = (lane, d)
        return best[0]

    def _detections_cb(self, msg):
        detections = []
        for det in msg.detections[:12]:
            bbox = det.bbox
            detections.append({
                "class": str(det.class_name or f"class_{det.class_id}"),
                "score": float(det.score),
                "cx": float(bbox.center.position.x),
                "cy": float(bbox.center.position.y),
                "w": float(bbox.size.x),
                "h": float(bbox.size.y),
            })
        detections.sort(key=lambda item: item["score"], reverse=True)
        self.latest_detections = detections
        self.latest_detection_time = time.monotonic()
        try:
            self._avoid_check(detections)
        except Exception as exc:                                # noqa: BLE001
            self.get_logger().warning(f"avoid check failed: {exc}")

    def _lidar_obstacle_cb(self, msg):
        self._lidar_obstacle = bool(msg.data)
        self._lidar_obstacle_time = time.monotonic()
        try:
            self._avoid_check()
        except Exception as exc:                                # noqa: BLE001
            self.get_logger().warning(f"avoid check failed: {exc}")

    def _lidar_obstacle_dist_cb(self, msg):
        self._lidar_obstacle_dist = float(msg.data)

    def _path_blocked(self):
        """True when something is in the driving path RIGHT NOW, judged by
        the sensors avoid_source selects.

        vision (default): VLM/YOLO sightings share the registry's lane check
        when fresh simulation coordinates exist. YOLO's lane label alone
        can confuse an adjacent car on a curve with one in our lane.
        lidar/any retain the explicitly enabled front-sector stop trigger.
        """
        now = time.monotonic()
        self._avoid_block_reason = "clear"
        coords_ok = self._avoid_coords_fresh(now)
        my_lane = self._judgment_lane(coords_ok)
        lane_s = self._obstacle_lane_s.get(my_lane) if coords_ok else None
        use_vision = self.avoid_source in {"vision", "any"}
        use_lidar = self.avoid_source in {"lidar", "any"}
        if use_vision:
            vlm_sees = (self._vlm_blocked_time is not None
                        and now - self._vlm_blocked_time
                        < max(3.0, 3 * self.avoid_vlm_period)
                        and self._vlm_blocked)
            # Check this lane's distance, not the globally nearest obstacle:
            # a closer adjacent car must not hide a second car in our lane.
            if lane_s is not None and lane_s <= self.avoid_coord_trigger_m:
                self._avoid_block_reason = f"coordinates:{my_lane}"
                return True
            if vlm_sees and (lane_s is not None or (
                    not coords_ok and not self._avoid_obstacles
                    and self._vlm_distance == "near")):
                self._avoid_block_reason = f"vlm:{my_lane}"
                return True
            dets = self._fresh(self.latest_detections,
                               self.latest_detection_time, [])
            blocker = f"{my_lane}_car"
            if (not coords_ok or lane_s is not None) and any(d["class"] == blocker
                   and d["h"] >= self.avoid_trigger_px for d in dets):
                self._avoid_block_reason = f"yolo:{blocker}"
                return True
        if use_lidar:
            if (self._lidar_obstacle_time is not None
                    and now - self._lidar_obstacle_time < 1.5
                    and self._lidar_obstacle):
                self._avoid_block_reason = "lidar:front_sector"
                return True
        return False

    def _avoid_coords_fresh(self, now):
        return (self._obstacle_ahead_time is not None
                and now - self._obstacle_ahead_time < 3.0
                and self._obstacle_ahead_lane in {"lane1", "lane2", "none"})

    def _set_avoid_stopped(self, stopped):
        if stopped != self._avoid_stopped:
            self._avoid_stopped = stopped
            self._publish_hold()

    def _set_signal_stopped(self, stopped):
        if stopped != self._signal_stopped:
            self._signal_stopped = stopped
            self._publish_hold()

    def _publish_hold(self):
        # One hold wire, two supervisors (avoidance + traffic signal):
        # release only when neither wants the car held.
        held = self._avoid_stopped or self._signal_stopped
        self.avoid_hold_pub.publish(String(data="1" if held else "0"))

    def _signal_check(self):
        """Red-light stop supervisor. Returns True while the signal holds
        the car (callers then skip the avoidance logic for this tick).

        State comes from signal.json (written by the dashboard buttons and
        scenario reset), geometry from the same lane-arc primitives as the
        avoidance supervisor: the stop line sits `signal_stop_before_m`
        short of the light along the car's physical lane."""
        path = os.path.join(os.path.dirname(self.avoid_obstacle_file),
                            "signal.json")
        try:
            mtime = os.path.getmtime(path)
            if mtime != self._signal_mtime:
                with open(path, encoding="utf-8") as f:
                    self._signal_state = json.load(f)
                self._signal_mtime = mtime
        except (OSError, ValueError):
            self._signal_state = None
            self._signal_mtime = None
        state = self._signal_state
        if not state or state.get("color") != "red":
            if self._signal_stopped:
                self._set_signal_stopped(False)
                self.event_q.put((
                    "assistant", "🟢 초록불 — 출발합니다."))
            return False
        if self._ego_pose_stream is None:
            self._ego_pose_stream = WorldPoseStream(
                self._gz_bin, "ego_vehicle").start()
        pose = self._ego_pose_stream.latest
        if pose is None or (time.monotonic()
                            - self._ego_pose_stream.received_at > 1.5):
            # No fresh truth: keep whatever hold we already have.
            return self._signal_stopped
        x, y, yaw = pose
        motion_yaw = yaw - math.pi / 2.0     # gz body yaw convention
        hx, hy = math.cos(motion_yaw), math.sin(motion_yaw)
        lane = self._nearest_lane(x, y) or self._vla_lane
        arc = self._arc_ahead(lane, x, y, hx, hy, state["x"], state["y"])
        if arc is None:
            return self._signal_stopped
        fwd_line = arc - self.signal_stop_before_m
        if self._signal_stopped:
            return True                      # engaged: hold until green
        # Engage only in the stop window; a car already past the light
        # (fwd_line well negative) keeps driving — too late to stop.
        if -1.0 < fwd_line <= self.signal_stop_trigger_m:
            self._set_signal_stopped(True)
            self.event_q.put((
                "assistant",
                f"🔴 빨간불 — 정지선(신호등 {self.signal_stop_before_m:.0f} m "
                "앞)에 정차합니다. 초록불이 켜지면 출발합니다."))
            return True
        return False

    def _judgment_lane(self, coords_fresh):
        """The lane obstacles are judged against.

        Cruising: the lane the car is PHYSICALLY in (command and reality
        diverged in the 17:36 crash). Mid-detour: the COMMANDED target lane
        — the body is still crossing out of the old lane, and judging by it
        re-blocks on the very obstacle being avoided (T4 curve stall: ego
        still in lane2 while swerving to lane1, froze 3.6 m short).
        """
        if self._avoid_home_lane is not None:
            return self._vla_lane
        return (coords_fresh and self._ego_actual_lane) or self._vla_lane

    def _avoid_check(self, detections=None):
        # ROS detection callbacks and the VLM worker may arrive together.
        with self._avoid_lock:
            self._avoid_check_locked()

    def _avoid_check_locked(self):
        """Obstacle-avoidance supervisor (lidar callbacks + YOLO frames).

        CRUISE -> (path blocked) -> flip lane, republish cruise sentence ->
        AVOID; for avoid_commit_s the triggers are suspended while the policy
        performs the swerve; a NEW block after that returns home immediately
        (staggered obstacles); otherwise home comes back after min_hold +
        clear time. The policy does the actual steering; this only swaps the
        instruction sentence.
        """
        if not self.avoid_enable:
            self._set_avoid_stopped(False)
            return
        if self._vla_mode not in {"cruise", "zone"}:
            # Not VLA-driving (idle / navigator beeline): drop any half-done
            # detour so the next command starts from the user's lane.
            if self._avoid_home_lane is not None:
                self._vla_lane = self._avoid_home_lane
                self.current_lane = self._vla_lane
                self._avoid_home_lane = None
            self._avoid_clear_since = None
            self._set_avoid_stopped(False)
            self._set_signal_stopped(False)
            return
        # Traffic light first: while red holds the car at the stop line,
        # the avoidance logic stays quiet (the car is not "blocked" — it
        # is waiting, and messages about the road ahead would be noise).
        if self._signal_check():
            return
        now = time.monotonic()
        # Read the live pose independently of the scene VLM/network cadence.
        self._update_obstacle_ahead()
        in_commit = (now - self._avoid_last_switch_t
                     < max(self.avoid_commit_s, self.avoid_cooldown_s))
        self._avoid_block_reason = "commit"
        blocked = False if in_commit else self._path_blocked()
        # State-change log so every run leaves an audit trail in
        # chat_gui.log (the 17:36 crash was undiagnosable without one).
        snap = (blocked, in_commit, self._vlm_blocked, self._vlm_distance,
                self._obstacle_ahead_lane,
                tuple(sorted(self._obstacle_lanes_ahead)),
                self._ego_actual_lane, self._vla_lane,
                self._avoid_home_lane, self._avoid_stopped,
                self._avoid_block_reason)
        if snap != self._avoid_log_last:
            self._avoid_log_last = snap
            self.get_logger().info(
                f"avoid: blocked={blocked} commit={in_commit} "
                f"vlm={self._vlm_blocked}/{self._vlm_distance} "
                f"ob_lane={self._obstacle_ahead_lane} "
                f"lanes_ahead={sorted(self._obstacle_lanes_ahead)} "
                f"ego_lane={self._ego_actual_lane} cmd={self._vla_lane} "
                f"home={self._avoid_home_lane} stopped={self._avoid_stopped} "
                f"source={self._avoid_block_reason} lane_s={self._obstacle_lane_s}")
        if in_commit:
            return
        if self._avoid_home_lane is None:
            if not blocked:
                return
            # Steer away from the lane the OBSTACLE is in (normally the
            # commanded lane, but reality wins when they diverge).
            ob_lane = self._judgment_lane(self._avoid_coords_fresh(now))
            self._avoid_home_lane = ob_lane
            self._avoid_kicks = 0
            self._avoid_started_t = now
            self._avoid_clear_since = None
            self._avoid_last_switch_t = now
            # The VLM only flags a blockage at ~8-12 m (measured), so the
            # avoidance sentence also drops to the slow tier — the swerve
            # needs the extra seconds.
            self._avoid_switch_lane(self._opposite_lane(ob_lane), slow=True)
            near = {"near": "가까움", "mid": "중간", "far": "멂"}.get(
                self._vlm_distance)
            near_txt = f" (거리: {near})" if near else ""
            self.event_q.put((
                "assistant",
                f"⚠️ {LANE_KR.get(self._avoid_home_lane, '주행')} 전방 "
                f"장애물 감지{near_txt} — 감속하며 "
                f"{LANE_KR.get(self._vla_lane, self._vla_lane)}으로 "
                f"회피합니다.",
            ))
            return
        # Detour active and the detour lane itself is blocked (with the
        # coordinate check this is now a REAL blocker, e.g. the staggered
        # red car in lane1 while dodging the blue one in lane2). If the
        # coordinates say the HOME lane is clear again, weave back and drive
        # past — this is what un-sticks the 18:2x run that stopped 15 m
        # short of the red car forever. Without a coordinate fix we cannot
        # tell the original obstacle from a new one (the 16:5x crash), so
        # then it stays the safe way: stop until the view clears.
        if blocked:
            self._avoid_clear_since = None
            coords_fresh = self._avoid_coords_fresh(now)
            home = self._avoid_home_lane
            if coords_fresh and home not in self._obstacle_lanes_ahead:
                self._avoid_home_lane = None
                self._set_avoid_stopped(False)
                self._avoid_last_switch_t = now
                self._avoid_switch_lane(home, slow=True)
                self.event_q.put((
                    "assistant",
                    f"⚠️ 회피 차선 전방에 장애물, "
                    f"{LANE_KR.get(home, home)}은 비어 있음 — "
                    f"{LANE_KR.get(home, home)}으로 복귀해 통과합니다.",
                ))
                return
            # Both lanes report blockers, but the commanded-lane one only
            # forces a stop once close; farther out the detour keeps rolling
            # (T7 stopped with 10 m of clear road because the 17 m sensing
            # range doubled as the stop line) — usually the home lane clears
            # meanwhile and the weave continues without stopping.
            if coords_fresh and not self._avoid_stopped:
                s_cmd = self._obstacle_lane_s.get(self._vla_lane)
                if s_cmd is not None and s_cmd > self.avoid_stop_m:
                    return
            if not self._avoid_stopped:
                # Keep the instruction and detour alive. Publishing "" here
                # echoed through _external_instr_cb as a USER stop, changed
                # cruise to idle, and made the promised auto-resume impossible.
                self._set_avoid_stopped(True)
                self.event_q.put((
                    "assistant",
                    f"⛔ 회피 차선 {LANE_KR.get(self._vla_lane, self._vla_lane)} "
                    "전방 장애물 감지 — 일단 정지하고 시야가 "
                    "트이면 재출발합니다.",
                ))
            return
        if self._avoid_stopped:
            # View is clear again: resume the detour in the current lane.
            self._set_avoid_stopped(False)
            self._avoid_last_switch_t = now     # fresh commit window
            self._avoid_switch_lane(self._vla_lane, slow=True)
            self.event_q.put((
                "assistant",
                "▶️ 전방이 트여 회피 주행을 재개합니다.",
            ))
            return
        # Policy freeze kick: on a curve with cars visible in both lanes the
        # policy sometimes brakes to a dead stop instead of executing the
        # commanded lane change (T15). If we are mid-detour, not stopped by
        # us, path not blocked, yet stationary for 4 s — re-issue the
        # sentence: the queue flush re-anchors the policy on a fresh chunk.
        # At most twice per detour to avoid a republish loop.
        if (self._ego_standstill_since is not None
                and now - self._ego_standstill_since > 4.0
                and self._avoid_kicks < 2):
            self._avoid_kicks += 1
            self._ego_standstill_since = None
            self._avoid_last_switch_t = now
            self._avoid_switch_lane(self._vla_lane, slow=True)
            self.event_q.put((
                "assistant",
                f"🔄 회피 중 정체 — 지시 재전송({self._avoid_kicks}/2): "
                f"{LANE_KR.get(self._vla_lane, self._vla_lane)} 유지.",
            ))
            return
        if self._avoid_clear_since is None:
            self._avoid_clear_since = now
        # Return when the coordinates say the home lane is clear ahead — a
        # time-only rule returned while the blocker was still alongside
        # (measured 18:05: VLM loses the obstacle the moment the nose points
        # away, so "unseen for N s" does not mean "passed").
        coords_fresh = self._avoid_coords_fresh(now)
        if coords_fresh:
            home_clear = (self._avoid_home_lane
                          not in self._obstacle_lanes_ahead)
            if not home_clear or now - self._avoid_started_t < 3.0:
                return
        elif (now - self._avoid_started_t < self.avoid_min_hold_s
                or now - self._avoid_clear_since < self.avoid_clear_s):
            return
        home = self._avoid_home_lane
        self._avoid_home_lane = None
        self._avoid_clear_since = None
        self._avoid_last_switch_t = now
        if self.avoid_return_home:
            self._avoid_switch_lane(home)
            self.event_q.put((
                "assistant",
                f"✅ 장애물 통과 — {LANE_KR.get(home, home)}으로 복귀합니다.",
            ))
        else:
            # Mission style (user 2026-09-10): stay in the detour lane and
            # keep cruising — the next blocker triggers the next switch.
            # The detour sentence is already the commanded instruction, so
            # ending the detour is just dropping the home marker; restoring
            # the normal tier is the only cleanup (the swerve ran slow).
            self._avoid_switch_lane(self._vla_lane)
            self.event_q.put((
                "assistant",
                f"✅ 장애물 통과 — {LANE_KR.get(self._vla_lane, self._vla_lane)}"
                "으로 계속 주행합니다.",
            ))

    def _avoid_switch_lane(self, lane, slow=False):
        """Flip the commanded lane and re-render the active cruise sentence.

        Keeps the zone watch untouched (navigator watches coordinates, not the
        lane) and preserves the pre-slow speed word if the watch already
        switched to it. slow=True forces the slow tier for the swerve itself;
        the return trip re-renders with the user's tier.
        """
        self._vla_lane = lane
        self.current_lane = lane
        with self._vla_watch_lock:
            preslow = self._vla_watch_preslow
        sentence = self._vla_cruise_sentence(
            speed_word="slowly" if (slow or preslow) else None)
        self.vla_instruction_pub.publish(String(data=sentence))
        self.last_dispatch = f"{self.vla_instruction_topic} {sentence!r}"

    def _lane_info_cb(self, msg):
        points = [
            (int(point.target_x), int(point.target_y))
            for point in msg.target_points[:5]
        ]
        self.latest_lane_info = {
            "slope": float(msg.slope),
            "points": points,
            "point_count": len(msg.target_points),
            "is_lane_changing": bool(msg.is_lane_changing),
        }
        self.latest_lane_info_time = time.monotonic()

    def _path_cb(self, msg):
        first = None
        last = None
        if msg.x_points and msg.y_points:
            first = (float(msg.x_points[0]), float(msg.y_points[0]))
            last = (float(msg.x_points[-1]), float(msg.y_points[-1]))
        self.latest_path_info = {
            "point_count": min(len(msg.x_points), len(msg.y_points)),
            "first": first,
            "last": last,
            "is_lane_changing": bool(msg.is_lane_changing),
        }
        self.latest_path_time = time.monotonic()

    def _odom_cb(self, msg):
        pose = msg.pose.pose
        q = pose.orientation
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        self.latest_pose = {
            "x": float(pose.position.x),
            "y": float(pose.position.y),
            "yaw": yaw,
            "speed": float(msg.twist.twist.linear.x),
        }
        self.latest_pose_time = time.monotonic()

    def _alpamayo_image_cb(self, msg):
        if PILImage is None:
            return
        try:
            payload = self._image_msg_to_jpeg_payload(msg)
        except Exception:
            return
        self.latest_alpamayo_image = payload
        self.latest_alpamayo_image_time = time.monotonic()
        self.alpamayo_image_buffer.append(payload)

    def _image_msg_to_jpeg_payload(self, msg):
        ch = 4 if msg.encoding in ("rgba8", "bgra8") else 3
        arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, ch)
        if msg.encoding in ("bgr8", "bgra8"):
            rgb = arr[:, :, :3][:, :, ::-1]
        else:
            rgb = arr[:, :, :3]
        image = PILImage.fromarray(np.ascontiguousarray(rgb))
        if self.alpamayo_image_max_width > 0 and image.width > self.alpamayo_image_max_width:
            scale = self.alpamayo_image_max_width / float(image.width)
            image = image.resize(
                (self.alpamayo_image_max_width, max(1, int(image.height * scale)))
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.alpamayo_image_quality)
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        return {
            "encoding": "jpeg_base64",
            "topic_encoding": str(msg.encoding),
            "width": image.width,
            "height": image.height,
            "stamp": stamp,
            "source_topic": self.alpamayo_image_topic,
            "received_monotonic": time.monotonic(),
            "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }

    def _load_zones(self):
        with open(self.map_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        return data.get("zones", {})

    def _zone_lines(self):
        lines = []
        for name, zone in self.zones.items():
            roles = ", ".join(zone.get("role", []) or ["-"])
            lines.append(f"- {name} : {roles}")
        return "\n".join(lines)

    def _warm_parser(self):
        """Load the parser model into VRAM at startup and keep it resident."""
        payload = {
            "model": self.parser_model,
            "stream": False,
            "think": False,
            "messages": [{"role": "user", "content": "ok"}],
            "options": {"num_predict": 1},
            "keep_alive": "15m",
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                response.read()
            self.get_logger().info("parser model preloaded (keep_alive=-1)")
        except Exception as exc:                                # noqa: BLE001
            self.get_logger().warn(f"parser warmup failed: {exc}")

    def parse_command(self, text):
        self.last_user_text = text
        requested_speed = parse_speed_raw(text, self.current_speed_raw)
        shortcut = self._deterministic_sequence_plan(text)
        if shortcut is not None:
            return self._with_speed_step(shortcut, requested_speed), 0.0, None
        shortcut = self._deterministic_drive_plan(text)
        if shortcut is not None:
            return self._with_speed_step(shortcut, requested_speed), 0.0, None
        if requested_speed is not None and not self._has_non_speed_driving_intent(text):
            return self._speed_plan(requested_speed), 0.0, None
        if self.parser_backend == "action_policy":
            started = time.monotonic()
            plan = self.action_policy.predict(text, self.current_lane)
            plan["reason"] = (
                f"action_policy confidence={plan.get('confidence', 0.0):.2f}"
            )
            normalized = self._normalize_plan(plan)
            return self._with_speed_step(normalized, requested_speed), time.monotonic() - started, None

        zone_enum = self.zone_names + ["T1", "M1", None]
        step_schema = {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "drive_to_zone",
                        "drive_direct",
                        "change_lane",
                        "keep_lane",
                        "stop",
                        "start",
                        "set_speed",
                        "none",
                    ],
                },
                "zone": {"type": ["string", "null"], "enum": zone_enum},
                "lane": {"type": "string", "enum": ["lane1", "lane2", "default"]},
                "speed": {"type": ["integer", "null"], "minimum": 0, "maximum": 250},
            },
            "required": ["action", "lane"],
        }
        schema = {
            "type": "object",
            "properties": {
                "steps": {"type": "array", "items": step_schema, "minItems": 1},
                "reason": {"type": "string"},
            },
            "required": ["steps"],
        }
        payload = {
            "model": self.parser_model,
            "stream": False,
            "think": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "system",
                    "content": (
                        f"Runtime context: current_lane={self.current_lane}. "
                        "Use this only to resolve unspecified lane-change direction."
                    ),
                },
                {"role": "user", "content": text},
            ],
            "format": schema,
            "options": {"temperature": 0, "num_predict": 768},
            # Keep the parser model resident. Without it, the FIRST command's
            # model load (~2.6 GB into VRAM) lands exactly when the user says
            # "start" — starving the SmolVLA policy server on the shared GPU
            # (bridge latency 287 -> 460 ms, underrun 24%, chunk fronts only)
            # and the launch wanders into the wrong lane (2026-08-21).
            "keep_alive": "15m",
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return None, time.monotonic() - started, str(exc)

        content = body.get("message", {}).get("content", "")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None, time.monotonic() - started, f"bad json: {content[:160]}"
        normalized = self._normalize_plan(parsed)
        return self._with_speed_step(normalized, requested_speed), time.monotonic() - started, None

    @staticmethod
    def _speed_plan(speed_raw):
        return {
            "steps": [{
                "action": "set_speed",
                "zone": None,
                "lane": "default",
                "speed": int(speed_raw),
            }],
            "reason": "deterministic speed command",
        }

    def _with_speed_step(self, plan, speed_raw):
        if speed_raw is None:
            return plan
        speed_step = self._speed_plan(speed_raw)["steps"][0]
        steps = [step for step in plan.get("steps", []) if step.get("action") != "set_speed"]
        return {**plan, "steps": [speed_step, *steps]}

    def _has_non_speed_driving_intent(self, text):
        text = str(text or "")
        return bool(
            self._match_zone_in_text(text)
            or CHANGE_LANE_RE.search(text)
            or STOP_WORD_RE.search(text)
            or DIRECT_DRIVE_RE.search(text)
            or re.search(r"\b(start|resume|continue)\b|출발|주행", text, re.IGNORECASE)
        )

    def _deterministic_drive_plan(self, text):
        """Handle simple destination commands without letting the LLM invent lanes."""
        if STANDALONE_DRIVE_RE.search(text or ""):
            return self._normalize_plan({
                "steps": [{"action": "start", "zone": None, "lane": "default"}],
                "reason": "deterministic cruise command",
            })
        if not (DRIVE_TO_RE.search(text) or DIRECT_DRIVE_RE.search(text)):
            return None
        if CHANGE_LANE_RE.search(text) or STOP_WORD_RE.search(text):
            return None
        zone = self._match_zone_in_text(text)
        if zone is None and re.search(r"\b(go|drive|move|navigate)\s+start\b", text, re.IGNORECASE):
            zone = "Start"
        if zone not in self.zones:
            return None
        lane = self._explicit_lane_from_text(text) or "default"
        action = "drive_direct" if DIRECT_DRIVE_RE.search(text) else "drive_to_zone"
        plan = {
            "steps": [{"action": action, "zone": zone, "lane": lane}],
            "reason": "deterministic simple destination command",
        }
        return self._normalize_plan(plan)

    def _deterministic_sequence_plan(self, text):
        """Parse repeated 'change laneX then go Z' chains without LLM lane drift."""
        if not CHANGE_LANE_RE.search(text or "") or not DRIVE_TO_RE.search(text or ""):
            return None
        parts = [p.strip() for p in SEQUENCE_SPLIT_RE.split(text) if p.strip()]
        if len(parts) < 2:
            return None
        steps = []
        pending_lane = None
        assumed_lane = self.current_lane if self.current_lane in {"lane1", "lane2"} else "lane2"
        saw_change = False
        for part in parts:
            lane = self._explicit_lane_from_text(part)
            has_change = CHANGE_LANE_RE.search(part) is not None
            zone = self._match_zone_in_text(part)
            if has_change:
                saw_change = True
                pending_lane = lane or self._opposite_lane(assumed_lane)
                lane = pending_lane
            if zone in self.zones:
                drive_lane = lane or pending_lane or "default"
                steps.append({
                    "action": "drive_to_zone",
                    "zone": zone,
                    "lane": drive_lane,
                })
                if drive_lane in {"lane1", "lane2"}:
                    assumed_lane = drive_lane
                pending_lane = None
        if not saw_change or len(steps) < 2:
            return None
        if pending_lane is not None:
            steps.append({"action": "change_lane", "zone": None, "lane": pending_lane})
        return self._normalize_plan({
            "steps": steps,
            "reason": "deterministic lane-change destination sequence",
        })

    def vla_judgment_text(self):
        if self.vla_judgment_backend == "alpamayo":
            return self._alpamayo_judgment_text()
        return self._local_vla_judgment_text()

    def _local_vla_judgment_text(self):
        parsed = self.last_parsed or {}
        steps = parsed.get("steps") or []
        detections = self._fresh(self.latest_detections, self.latest_detection_time, [])
        lane_info = self._fresh(self.latest_lane_info, self.latest_lane_info_time)
        path_info = self._fresh(self.latest_path_info, self.latest_path_time)
        pose = self._fresh(self.latest_pose, self.latest_pose_time)

        detection_text = self._detection_summary(detections)
        lane_text = self._lane_info_summary(lane_info)
        path_text = self._path_summary(path_info)
        pose_text = self._pose_summary(pose)
        step_text = self._steps_summary(steps)
        evidence = self._evidence_summary(detections, lane_info, path_info)

        lines = [
            "VLA Judgment (CoC-lite)",
            "",
            "Observation",
            f"- camera/YOLO: {detection_text}",
            f"- lane info: {lane_text}",
            f"- path planner: {path_text}",
            f"- pose: {pose_text}",
            f"- current lane: {self.current_lane}",
            f"- navigator: {self.last_nav_status}",
            "",
            "Language Intent",
            f"- command: {self.last_user_text}",
            f"- interpreted steps: {step_text}",
            "",
            "Causal Check",
            f"- perception evidence: {evidence}",
            f"- selected dispatch: {self.last_dispatch}",
            f"- action summary: {self.last_action_text}",
        ]
        return "\n".join(lines)

    def _alpamayo_judgment_text(self):
        self._maybe_request_alpamayo()
        if self.alpamayo_last_text.strip():
            return self.alpamayo_last_text.strip()
        if self.alpamayo_last_error:
            return f"Alpamayo 응답을 기다리는 중입니다. 현재 연결 상태: {self.alpamayo_last_error}"
        if not self.alpamayo_endpoint:
            return "Alpamayo endpoint가 설정되지 않았습니다."
        return "Alpamayo가 현재 장면을 분석하는 중입니다."

    def alpamayo_debug_text(self):
        image_status = "no fresh image"
        image_payload = self._fresh(
            self.latest_alpamayo_image,
            self.latest_alpamayo_image_time,
        )
        if image_payload:
            image_status = (
                f"{image_payload.get('width')}x{image_payload.get('height')} "
                f"{image_payload.get('encoding')} from {image_payload.get('topic_encoding')}"
            )
        header = [
            "Alpamayo Teacher",
            f"- model: {self.alpamayo_model_id}",
            f"- repo: {ALPAMAYO_REPO_URL}",
            f"- weights: {ALPAMAYO_HF_URL}",
            f"- image payload: {image_status}",
        ]
        if not self.alpamayo_endpoint:
            header.extend([
                "- status: endpoint not configured",
                "",
                "Run chat_gui_node with:",
                "  -p vla_judgment_backend:=alpamayo",
                "  -p alpamayo_endpoint:=http://127.0.0.1:8765/judge",
                "",
                "The endpoint should accept POST JSON:",
                "  {model, prompt, snapshot}",
                "and return JSON/text with a reasoning or judgment field.",
            ])
        else:
            header.append(f"- endpoint: {self.alpamayo_endpoint}")
            if self.alpamayo_last_stamp is None:
                header.append("- status: waiting for first teacher response")
            else:
                age = time.monotonic() - self.alpamayo_last_stamp
                header.append(f"- status: last response {age:.1f}s ago")
            if self.alpamayo_last_error:
                header.append(f"- error: {self.alpamayo_last_error}")

        teacher_text = self.alpamayo_last_text.strip()
        if not teacher_text:
            teacher_text = "No Alpamayo teacher output yet."

        return "\n".join([
            *header,
            "",
            "Teacher Output",
            teacher_text,
            "",
            "Local ROS Snapshot",
            self._local_vla_judgment_text(),
        ])

    def _maybe_request_alpamayo(self):
        if not self.alpamayo_endpoint or self.alpamayo_busy:
            return
        now = time.monotonic()
        if now - self.alpamayo_last_call < max(0.5, self.alpamayo_period):
            return
        self.alpamayo_last_call = now
        self.alpamayo_busy = True
        snapshot = self._vla_snapshot()
        prompt = self._alpamayo_prompt(snapshot)
        threading.Thread(
            target=self._request_alpamayo_worker,
            args=(prompt, snapshot),
            daemon=True,
        ).start()

    def _request_alpamayo_worker(self, prompt, snapshot):
        payload = {
            "model": self.alpamayo_model_id,
            "prompt": prompt,
            "snapshot": snapshot,
        }
        request = urllib.request.Request(
            self.alpamayo_endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.alpamayo_timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
            teacher_text, teacher_payload = self._extract_alpamayo_payload(raw)
            self.alpamayo_last_text = teacher_text
            self.alpamayo_last_error = ""
            self.alpamayo_last_stamp = time.monotonic()
            self._log_alpamayo_response(snapshot, teacher_text, teacher_payload)
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            if body:
                self.alpamayo_last_error = f"HTTP {exc.code}: {body[:1200]}"
            else:
                self.alpamayo_last_error = str(exc)
        except Exception as exc:  # Keep GUI alive even if the external teacher is down.
            self.alpamayo_last_error = str(exc)
        finally:
            self.alpamayo_busy = False

    @staticmethod
    def _extract_alpamayo_text(raw):
        return ChatGuiNode._extract_alpamayo_payload(raw)[0]

    @staticmethod
    def _extract_alpamayo_payload(raw):
        text = raw.strip()
        if not text:
            return "Empty Alpamayo teacher response.", {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text, {"raw": text}
        for key in (
            "reasoning",
            "judgment",
            "coc",
            "chain_of_causation",
            "text",
            "output",
            "message",
        ):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), data
        return json.dumps(data, ensure_ascii=False, indent=2), data

    def _log_alpamayo_response(self, snapshot, teacher_text, teacher_payload):
        if not self.alpamayo_log_jsonl or not self.alpamayo_log_csv:
            return
        now = dt.datetime.now().isoformat(timespec="seconds")
        image_files = self._save_alpamayo_images(snapshot, now)
        clean_snapshot = self._snapshot_for_log(snapshot, image_files)
        row = {
            "time": now,
            "model": str(teacher_payload.get("model") or self.alpamayo_model_id),
            "source": str(teacher_payload.get("source") or ""),
            "command": str(clean_snapshot.get("command") or ""),
            "steps": json.dumps(clean_snapshot.get("parsed_steps") or [], ensure_ascii=False),
            "current_lane": str(clean_snapshot.get("current_lane") or ""),
            "nav_status": str(clean_snapshot.get("nav_status") or ""),
            "dispatch": str(clean_snapshot.get("last_dispatch") or ""),
            "pose": json.dumps(clean_snapshot.get("pose") or {}, ensure_ascii=False),
            "image_count": str(len(clean_snapshot.get("images") or [])),
            "image_files": ";".join(image_files),
            "reasoning": teacher_text,
            "endpoint": self.alpamayo_endpoint,
        }
        record = {
            **row,
            "snapshot": clean_snapshot,
            "teacher_payload": teacher_payload,
        }
        try:
            with open(self.alpamayo_log_jsonl, "a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            with open(self.alpamayo_log_csv, "a", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=self._alpamayo_log_fields())
                writer.writerow(row)
        except OSError as exc:
            self.alpamayo_last_error = f"log write failed: {exc}"

    def _save_alpamayo_images(self, snapshot, timestamp):
        if not getattr(self, "alpamayo_image_dir", ""):
            return []
        saved = []
        safe_time = re.sub(r"[^0-9A-Za-z_\\-]", "_", timestamp)
        for index, image in enumerate(snapshot.get("images") or []):
            if image.get("encoding") != "jpeg_base64":
                continue
            data = image.get("data") or ""
            if not data:
                continue
            stamp = image.get("stamp")
            if isinstance(stamp, (int, float)) and stamp > 0:
                frame_id = f"cam_{stamp:.6f}".replace(".", "_")
            else:
                frame_id = safe_time
            path = os.path.join(self.alpamayo_image_dir, f"{frame_id}_{index:02d}.jpg")
            try:
                with open(path, "wb") as file:
                    file.write(base64.b64decode(data))
            except (OSError, ValueError, binascii.Error) as exc:
                self.alpamayo_last_error = f"image log write failed: {exc}"
                continue
            saved.append(os.path.relpath(path, self.alpamayo_log_dir))
        return saved

    @staticmethod
    def _snapshot_for_log(snapshot, image_files=None):
        clean = dict(snapshot)
        images = []
        image_files = image_files or []
        for index, image in enumerate(clean.get("images") or []):
            images.append({
                "encoding": image.get("encoding"),
                "topic_encoding": image.get("topic_encoding"),
                "width": image.get("width"),
                "height": image.get("height"),
                "stamp": image.get("stamp"),
                "source_topic": image.get("source_topic"),
                "received_monotonic": image.get("received_monotonic"),
                "data_bytes_base64": len(image.get("data") or ""),
                "file": image_files[index] if index < len(image_files) else "",
            })
        clean["images"] = images
        return clean

    def _vla_snapshot(self):
        parsed = self.last_parsed or {}
        return {
            "command": self.last_user_text,
            "action_summary": self.last_action_text,
            "parsed_steps": parsed.get("steps") or [],
            "reason": parsed.get("reason", ""),
            "current_lane": self.current_lane,
            "nav_status": self.last_nav_status,
            "last_dispatch": self.last_dispatch,
            "detections": self._fresh(self.latest_detections, self.latest_detection_time, []),
            "lane_info": self._fresh(self.latest_lane_info, self.latest_lane_info_time),
            "path": self._fresh(self.latest_path_info, self.latest_path_time),
            "pose": self._fresh(self.latest_pose, self.latest_pose_time),
            "images": self._fresh(
                list(self.alpamayo_image_buffer),
                self.latest_alpamayo_image_time,
                [],
            ),
            "zones": self.zone_names,
        }

    def _alpamayo_prompt(self, snapshot):
        clean_snapshot = self._snapshot_for_log(snapshot)
        return (
            "You are Alpamayo 1.5 used as a non-controlling teacher for a small "
            "ROS2 track vehicle. Review the latest camera/perception/planner "
            "snapshot and produce one concise natural-language paragraph based "
            "on the visible image sequence. "
            "Do not command the vehicle directly. Focus on whether the parsed "
            "intent, lane choice, target zone, and current motion are consistent. "
            "Only mention vehicles, pedestrians, traffic lights, or obstacles if "
            "they are actually visible in the provided camera frames. "
            "Do not use bullets, headings, JSON, numbered lists, or labels. "
            "Write 2 to 4 complete sentences as if explaining the current driving "
            "situation to an operator. If visual evidence is insufficient, say "
            "what is missing in the same paragraph.\n\n"
            f"Snapshot JSON:\n{json.dumps(clean_snapshot, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def _fresh(value, stamp, default=None, max_age=2.5):
        if stamp is None:
            return default
        if time.monotonic() - stamp > max_age:
            return default
        return value

    @staticmethod
    def _detection_summary(detections):
        if not detections:
            return "no fresh detections"
        counts = {}
        best = {}
        for det in detections:
            name = det["class"]
            counts[name] = counts.get(name, 0) + 1
            best[name] = max(best.get(name, 0.0), det["score"])
        parts = [
            f"{name} x{counts[name]} best={best[name]:.2f}"
            for name in sorted(counts)
        ]
        return ", ".join(parts)

    @staticmethod
    def _lane_info_summary(lane_info):
        if not lane_info:
            return "no fresh lane info"
        points = lane_info["points"]
        point_text = ", ".join(f"({x},{y})" for x, y in points[:3]) or "-"
        return (
            f"slope={lane_info['slope']:.2f}, "
            f"points={lane_info['point_count']} [{point_text}], "
            f"changing={lane_info['is_lane_changing']}"
        )

    @staticmethod
    def _path_summary(path_info):
        if not path_info:
            return "no fresh path"
        first = path_info["first"]
        last = path_info["last"]
        if first is None or last is None:
            span = "-"
        else:
            span = f"({first[0]:.1f},{first[1]:.1f}) -> ({last[0]:.1f},{last[1]:.1f})"
        return (
            f"points={path_info['point_count']}, "
            f"changing={path_info['is_lane_changing']}, span={span}"
        )

    @staticmethod
    def _pose_summary(pose):
        if not pose:
            return "no fresh odom"
        return (
            f"x={pose['x']:.2f}, y={pose['y']:.2f}, "
            f"yaw={pose['yaw']:.2f}, v={pose['speed']:.2f}"
        )

    @staticmethod
    def _steps_summary(steps):
        if not steps:
            return "-"
        parts = []
        for step in steps:
            action = step.get("action", "?")
            zone = step.get("zone")
            lane = step.get("lane")
            text = action
            if zone:
                text += f"({zone})"
            if lane and lane != "default":
                text += f"[{lane}]"
            if action == "set_speed" and step.get("speed") is not None:
                text += f"({step['speed']}/250)"
            parts.append(text)
        return " -> ".join(parts)

    @staticmethod
    def _evidence_summary(detections, lane_info, path_info):
        lane_seen = any(
            str(det.get("class", "")).lower() in {"lane1", "lane2"}
            for det in detections or []
        )
        if lane_seen and lane_info and path_info:
            return "lane markings, lane target points, and planned path are all fresh"
        if lane_seen and lane_info:
            return "lane markings and lane target points are fresh"
        if lane_info or path_info:
            return "planner/lane geometry is fresh, visual detections may be stale"
        if detections:
            return "visual detections are fresh, planner/lane geometry may be stale"
        return "waiting for fresh camera/perception/planner data"

    def dispatch_plan(self, plan):
        """Queue an ordered plan and dispatch steps up to the first blocking drive.

        A new plan replaces any plan still in flight. Returns a summary string of
        the steps dispatched in this synchronous burst; later steps (unblocked by
        the navigator reaching a zone) are announced through event_q.
        """
        steps = plan.get("steps", [])
        with self._plan_lock:
            self.last_parsed = {"steps": [dict(s) for s in steps], "reason": plan.get("reason", "")}
            self.pending_steps = [dict(s) for s in steps]
            self._waiting = None
            messages = self._run_pending()
        summary = " / ".join(m for m in messages if m)
        return summary or "No actionable driving command was found."

    def _run_pending(self):
        """Dispatch queued steps until a drive step starts (and we must wait for
        arrival) or the queue empties. Caller must hold self._plan_lock.
        Returns the list of message strings produced in this burst.
        """
        messages = []
        while self.pending_steps:
            step = self.pending_steps.pop(0)
            message, wait = self._dispatch_step(step)
            messages.append(message)
            if wait is not None:
                self._waiting = wait
                return messages
        self._waiting = None
        return messages

    def _dispatch_step(self, step):
        """Execute one step. Returns (message, wait) where wait is None for an
        instant step, or ("zone"|"direct", zone_name) if the step started an
        asynchronous drive that must complete before the next step runs.
        """
        action = step["action"]
        lane = step["lane"]
        zone = step.get("zone")

        if action == "set_speed":
            speed = max(0, min(250, int(step.get("speed") or 0)))
            self.current_speed_raw = speed
            self.speed_pub.publish(Int32(data=speed))
            self.last_dispatch = f"/speed_command {speed}"
            return f"Speed limit set to {speed}/250.", None

        if action == "drive_to_zone":
            if zone not in self.zones:
                self.last_dispatch = f"invalid zone: {zone}"
                return f"Unknown zone: {zone}", None
            if self._is_direct_only_zone(zone):
                return self._dispatch_step({
                    "action": "drive_direct",
                    "zone": zone,
                    "lane": "default",
                })
            payload = {"zone": zone}
            if lane in {"lane1", "lane2"}:
                payload["lane"] = lane
                self.lane_pub.publish(String(data=lane))
            self.nav_goal_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
            lane_text = f" / {lane}" if lane in {"lane1", "lane2"} else ""
            self.last_drive_step = {
                "action": "drive_to_zone",
                "zone": zone,
                "lane": lane if lane in {"lane1", "lane2"} else "default",
            }
            self.last_dispatch = f"{self.nav_goal_topic} {payload}"
            return f"Driving to {zone}{lane_text}.", ("zone", zone)

        if action == "drive_direct":
            if zone not in self.zones:
                self.last_dispatch = f"invalid direct zone: {zone}"
                return f"Unknown zone: {zone}", None
            self.nav_goal_pub.publish(String(data="stop"))
            self.motion_pub.publish(String(data="stop"))
            self.direct_goal_pub.publish(String(data=zone))
            self.last_dispatch = f"{self.direct_nav_goal_topic} {zone}"
            return f"Driving directly to {zone}, ignoring lane guidance.", ("direct", zone)

        if action in {"change_lane", "keep_lane"}:
            if lane not in {"lane1", "lane2"}:
                self.last_dispatch = "missing lane"
                return "The target lane is unclear.", None
            self.lane_pub.publish(String(data=lane))
            self.motion_pub.publish(String(data="start"))
            if self.policy_goal_mode:
                return self._dispatch_policy_cruise(lane, "lane_command")
            self.last_dispatch = f"/lane_mode_command {lane}"
            return f"Driving in {lane}.", None

        if action == "stop":
            self.motion_pub.publish(String(data="stop"))
            self.nav_goal_pub.publish(String(data="stop"))
            self.direct_goal_pub.publish(String(data="stop"))
            self.last_dispatch = "/motion_control_command stop"
            return "Stopping.", None

        if action == "start":
            self.motion_pub.publish(String(data="start"))
            if self.policy_goal_mode:
                return self._dispatch_policy_start()
            self.last_dispatch = "/motion_control_command start"
            return "Starting driving.", None

        self.last_dispatch = "none"
        return None, None

    def _dispatch_policy_start(self):
        """In policy-only mode, start/drive means cruise until stop."""
        lane = self.current_lane if self.current_lane in {"lane1", "lane2"} else "lane2"
        return self._dispatch_policy_cruise(lane, "start")

    def _dispatch_policy_cruise(self, lane, reason):
        zone = self._next_cruise_zone()
        return self._dispatch_policy_goal(zone, lane, reason, cruise=True)

    def _dispatch_policy_goal(self, zone, lane, reason, cruise=False):
        if zone not in self.zones:
            self.last_dispatch = f"policy cruise unavailable: {zone}"
            return "No follow-up driving target was found.", None
        payload = {"zone": zone}
        if cruise:
            payload["mode"] = "cruise"
        if lane in {"lane1", "lane2"}:
            payload["lane"] = lane
            self.lane_pub.publish(String(data=lane))
        self.nav_goal_pub.publish(String(data=json.dumps(payload, ensure_ascii=False)))
        self.motion_pub.publish(String(data="start"))
        self.last_drive_step = {
            "action": "drive_to_zone",
            "zone": zone,
            "lane": lane if lane in {"lane1", "lane2"} else "default",
        }
        self.last_dispatch = f"{self.nav_goal_topic} {payload} ({reason})"
        lane_text = f" / {lane}" if lane in {"lane1", "lane2"} else ""
        if cruise:
            return f"Cruising{lane_text}.", None
        return f"Continuing toward {zone}{lane_text}.", ("zone", zone)

    def _next_cruise_zone(self):
        for anchor in (self.last_arrived_zone, (self.last_drive_step or {}).get("zone")):
            if anchor in TRACK_CRUISE_ZONES:
                index = TRACK_CRUISE_ZONES.index(anchor)
                return TRACK_CRUISE_ZONES[(index + 1) % len(TRACK_CRUISE_ZONES)]
        return TRACK_CRUISE_ZONES[0]

    def _handle_status(self, text):
        """Forward navigator status to the GUI and advance the plan queue when the
        drive we were waiting on completes (or is cancelled)."""
        self.last_nav_status = text
        self.status_q.put(text)
        if self.control_backend == "smolvla":
            # In smolvla mode the navigator is a coordinate arrival supervisor
            # for VLA zone goals; the qwen plan queue is never used.
            self._handle_vla_watch_status(text)
            return
        with self._plan_lock:
            arrived_zone = self._arrived_zone_from_status(text)
            if arrived_zone is not None:
                self.last_arrived_zone = arrived_zone
            waiting = self._waiting
            if waiting is None:
                return
            kind, name = waiting
            if kind == "zone" and text.startswith("arrived:"):
                parts = text.split(None, 2)
                if len(parts) > 1 and self._zone_match(parts[1], name):
                    self._advance_locked()
            elif kind == "direct" and text.startswith("direct arrived:"):
                parts = text.split(None, 2)
                if len(parts) > 2 and self._zone_match(parts[2], name):
                    self._advance_locked()
            elif kind == "zone" and (text.startswith("idle:") or text.startswith("error:")):
                # A lane-follow drive never self-cancels, so idle/error here means the
                # drive was cancelled or failed externally; abandon the rest of the plan.
                # (A drive_direct step self-cancels /nav_goal, so its idle is ignored.)
                self.pending_steps = []
                self._waiting = None
                self.event_q.put(("system", "Remaining plan steps were cancelled."))

    def _arrived_zone_from_status(self, text):
        if text.startswith("arrived:"):
            parts = text.split(None, 2)
            return parts[1] if len(parts) > 1 and parts[1] in self.zones else None
        if text.startswith("direct arrived:"):
            parts = text.split(None, 2)
            return parts[2] if len(parts) > 2 and parts[2] in self.zones else None
        return None

    def _advance_locked(self):
        """Continue the plan after an arrival. Caller must hold self._plan_lock."""
        self._waiting = None
        for message in self._run_pending():
            if message:
                self.event_q.put(("assistant", message))

    def _zone_match(self, got, name):
        if got == name:
            return True
        return self._normalize_zone(got) == self._normalize_zone(name)

    @staticmethod
    def _is_direct_only_zone(zone):
        return str(zone or "") in DIRECT_ONLY_ZONES

    def _normalize_plan(self, parsed):
        raw_steps = parsed.get("steps")
        if not isinstance(raw_steps, list):
            # Tolerate a legacy single-object response.
            raw_steps = [parsed] if parsed.get("action") is not None else []
        steps = [self._normalize_step(step) for step in raw_steps if isinstance(step, dict)]
        steps = [step for step in steps if step["action"] != "none"]
        steps = self._apply_explicit_lane_override(steps)
        steps = self._apply_unspecified_lane_defaults(steps)
        steps = self._apply_stop_target(steps)
        steps = self._apply_change_lane_waypoint(steps)
        if not steps:
            steps = [{"action": "none", "zone": None, "lane": "default"}]
        return {"steps": steps, "reason": str(parsed.get("reason") or "")}

    def _apply_explicit_lane_override(self, steps):
        """Do not let the LLM turn "go T4 through lane2" into direct driving."""
        lane = self._explicit_lane_from_text(self.last_user_text or "")
        if lane is None:
            return steps
        fixed = []
        for step in steps:
            if (
                step["action"] == "drive_direct"
                and step.get("zone") in self.zones
                and not self._is_direct_only_zone(step.get("zone"))
            ):
                step = {
                    "action": "drive_to_zone",
                    "zone": step.get("zone"),
                    "lane": lane,
                }
            elif step["action"] == "drive_to_zone" and step["lane"] == "default":
                step = {**step, "lane": lane}
            fixed.append(step)
        return fixed

    @staticmethod
    def _explicit_lane_from_text(text):
        if LANE1_RE.search(text):
            return "lane1"
        if LANE2_RE.search(text):
            return "lane2"
        return None

    @staticmethod
    def _opposite_lane(lane):
        return "lane1" if lane == "lane2" else "lane2"

    def _apply_unspecified_lane_defaults(self, steps):
        """For plain "go T2", keep the current lane even if the LLM guessed one."""
        text = self.last_user_text or ""
        if self._explicit_lane_from_text(text) is not None or CHANGE_LANE_RE.search(text):
            return steps
        fixed = []
        for step in steps:
            if step["action"] == "drive_to_zone" and step["lane"] in {"lane1", "lane2"}:
                step = {**step, "lane": "default"}
            fixed.append(step)
        return fixed

    def _build_zone_text_patterns(self):
        """Ordered (regex, canonical zone) list for spotting a zone name in free
        text. Longest phrases first so 'crosswalk_stop' wins over 'crosswalk'."""
        entries = [(phrase, "Start") for phrase in START_LINE_PHRASES]
        entries += [("T1", "T1/M1"), ("M1", "T1/M1")]
        entries += [(name, name) for name in self.zone_names]
        entries += [(alias, canonical) for alias, canonical in ZONE_ALIASES.items()]
        entries.sort(key=lambda item: len(item[0]), reverse=True)
        patterns = []
        for phrase, canonical in entries:
            if re.fullmatch(r"[A-Za-z0-9 ]+", phrase):
                if phrase.lower() in AMBIGUOUS_BARE_ZONES:
                    continue
                # Bound against ascii alnum only, so an adjacent Korean particle
                # ("M3에서", "T4까지") still counts as a boundary but "M30" does not.
                regex = re.compile(
                    r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])",
                    re.IGNORECASE,
                )
            else:
                regex = re.compile(re.escape(phrase), re.IGNORECASE)
            patterns.append((regex, canonical))
        return patterns

    def _match_zone_in_text(self, text):
        for regex, canonical in self._zone_text_patterns:
            if regex.search(text):
                return canonical
        return None

    def _apply_stop_target(self, steps):
        """A small parser (qwen3:4b) often collapses "stop at <zone>" into a bare
        in-place stop. When the user tied the stop to reaching a zone, drive there
        and stop instead of halting where we stand."""
        if len(steps) != 1 or steps[0]["action"] != "stop":
            return steps
        text = self.last_user_text or ""
        if not (STOP_WORD_RE.search(text) and POSITION_TRIGGER_RE.search(text)):
            return steps
        zone = self._match_zone_in_text(text)
        if not zone or zone not in self.zones:
            return steps
        action = "drive_direct" if zone in DIRECT_ONLY_ZONES else "drive_to_zone"
        return [{"action": action, "zone": zone, "lane": steps[0]["lane"]}]

    def _apply_change_lane_waypoint(self, steps):
        """"change lane at <zone>" is a waypoint: drive to the zone in the current
        lane, then switch lanes there. The small parser mishandles this in two ways
        — it switches lanes immediately (drops the drive), or it drives to the zone
        and drops the lane change. Rebuild the two-step plan from the raw text."""
        text = self.last_user_text or ""
        if not (CHANGE_LANE_RE.search(text) and POSITION_TRIGGER_RE.search(text)):
            return steps
        zone = self._match_zone_in_text(text)
        if not zone or zone not in self.zones:
            return steps
        # Already a proper waypoint (drive then change lane): leave it alone.
        actions = [step["action"] for step in steps]
        if actions in (["drive_to_zone", "change_lane"], ["drive_direct", "change_lane"]):
            return steps
        # Only rebuild when the parser collapsed it into a single drive or a single
        # lane change; multi-step plans may carry a further destination we'd drop.
        if len(steps) != 1 or actions[0] not in {"change_lane", "drive_to_zone", "drive_direct"}:
            return steps
        lane = self._resolve_change_lane_target(text, steps[0])
        return [
            {"action": "drive_to_zone", "zone": zone, "lane": "default"},
            {"action": "change_lane", "zone": None, "lane": lane},
        ]

    def _resolve_change_lane_target(self, text, step):
        """Which lane to switch to at the waypoint: an explicit lane in the text
        wins, else the lane the parser already chose, else the opposite of now."""
        if LANE1_RE.search(text):
            return "lane1"
        if LANE2_RE.search(text):
            return "lane2"
        if step["action"] == "change_lane" and step["lane"] in {"lane1", "lane2"}:
            return step["lane"]
        return "lane1" if self.current_lane == "lane2" else "lane2"

    def _normalize_step(self, step):
        action = str(step.get("action") or "none").strip()
        if action not in {
            "drive_to_zone",
            "drive_direct",
            "change_lane",
            "keep_lane",
            "stop",
            "start",
            "set_speed",
            "none",
        }:
            action = "none"
        lane = str(step.get("lane") or "default").strip().lower()
        if lane not in {"lane1", "lane2"}:
            lane = "default"
        zone = step.get("zone")
        if zone is not None:
            zone = self._normalize_zone(str(zone).strip())
        speed = step.get("speed")
        if action == "set_speed":
            try:
                speed = max(0, min(250, int(speed)))
            except (TypeError, ValueError):
                action = "none"
                speed = None
        else:
            speed = None
        return {"action": action, "zone": zone, "lane": lane, "speed": speed}

    def _normalize_zone(self, zone):
        if zone in self.zones:
            return zone
        compact = re.sub(r"[\s_-]+", "", str(zone or "").lower())
        return ZONE_ALIASES.get(compact, zone)


class ChatGuiWindow:
    def __init__(self, node):
        self.node = node
        self.root = tk.Tk()
        self.root.title("nav-vla Driving Chat Console")
        self.root.geometry("1120x620")
        self.root.minsize(900, 500)

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Title.TLabel", font=("TkDefaultFont", 14, "bold"))
        self.style.configure("Status.TLabel", foreground="#344054")
        self.style.configure("Primary.TButton", padding=(12, 6))
        self.style.configure("Record.TButton", padding=(12, 6))

        self.recording = False
        self.record_stream = None
        self.record_frames = []
        self.voice_busy = False
        self.whisper_model = None
        self.voice_available = sd is not None and WhisperModel is not None
        self.debug_window = None
        self.debug_log = None
        self.vla_debug_window = None
        self.vla_debug_log = None
        self.debug_lines = []
        self.status_text = tk.StringVar(value=self._debug_text())

        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(
            header,
            text="nav-vla Driving Chat Console",
            style="Title.TLabel",
        ).pack(anchor=tk.W)
        if node.control_backend == "smolvla":
            parser_label = (
                "Control: SmolVLA — chat text is parsed and sent as a trained "
                f"sentence to {node.vla_instruction_topic}"
            )
        else:
            parser_label = (
                "Backend: learned action_policy"
                if node.parser_backend == "action_policy"
                else f"Model fixed: {self.node.parser_model}"
            )
        ttk.Label(header, text=parser_label, style="Status.TLabel").pack(anchor=tk.W)

        entry_row = ttk.Frame(outer)
        entry_row.pack(fill=tk.X, pady=(0, 10))
        self.entry = ttk.Entry(entry_row)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _event: self._send())
        self.send_button = ttk.Button(
            entry_row,
            text="Send",
            command=self._send,
            style="Primary.TButton",
        )
        self.send_button.pack(side=tk.LEFT, padx=(8, 0))
        self.stop_button = ttk.Button(
            entry_row,
            text="STOP",
            command=self._stop_smolvla,
        )
        if node.control_backend == "smolvla":
            self.stop_button.pack(side=tk.LEFT, padx=(8, 0))
        self.voice_auto_send = tk.BooleanVar(value=True)
        self.voice_button = ttk.Button(
            entry_row,
            text="Voice",
            command=self._toggle_voice,
            style="Record.TButton",
        )
        self.voice_button.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(
            entry_row,
            text="Auto send",
            variable=self.voice_auto_send,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            entry_row,
            text="Debug",
            command=self._open_debug_window,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            entry_row,
            text="VLA Debug",
            command=self._open_vla_debug_window,
        ).pack(side=tk.LEFT, padx=(8, 0))
        if not self.voice_available:
            self.voice_button.config(state=tk.DISABLED)

        content = ttk.Frame(outer)
        content.pack(fill=tk.BOTH, expand=True)
        content.columnconfigure(0, weight=1, uniform="main")
        content.columnconfigure(1, weight=1, uniform="main")
        content.rowconfigure(0, weight=1)

        chat_frame = ttk.Frame(content, padding=(0, 0, 0, 0))
        vla_frame = ttk.LabelFrame(content, text="VLA Judgment", padding=8)
        chat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        vla_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        # Header row: title on the left, the short live motion ticker (🚗 from
        # /vla/narration) on the right — out of the chat, as requested.
        chat_header = ttk.Frame(chat_frame)
        chat_header.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(chat_header, text="Conversation",
                  font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        # 🚗 motion ticker sits LEFT beside the title; the language selector
        # is the rightmost control (user-requested layout, 2026-08-28).
        self.ticker_var = tk.StringVar(value="")
        ttk.Label(chat_header, textvariable=self.ticker_var,
                  foreground="#6a1b9a").pack(side=tk.LEFT, padx=(10, 0))
        # Commentary language toggle (한/영) — feeds node.scene_lang, which
        # the LLM prompt, template fallback, and voice recognition obey.
        self.lang_var = tk.StringVar(value="한국어")
        lang_box = ttk.Combobox(
            chat_header, textvariable=self.lang_var, state="readonly",
            values=("한국어", "English"), width=8)
        lang_box.pack(side=tk.RIGHT)
        lang_box.bind("<<ComboboxSelected>>", lambda _e: setattr(
            self.node, "scene_lang",
            "en" if self.lang_var.get() == "English" else "ko"))

        self.log = scrolledtext.ScrolledText(
            chat_frame, wrap=tk.WORD, state=tk.DISABLED,
            background="#ffffff", borderwidth=0, highlightthickness=0)
        self.log.pack(fill=tk.BOTH, expand=True)
        # Messenger-style bubbles in a single transcript: the user's messages
        # hug the right edge, the VLA's hug the left — alignment carries the
        # speaker, so no "User:"/"Action:" prefixes. A tag background over the
        # wrapped block is the bubble.
        self.log.tag_config(
            "user", justify=tk.RIGHT, lmargin1=120, lmargin2=120, rmargin=10,
            background="#dcf8c6", foreground="#1b3c1b",
            borderwidth=1, relief=tk.SOLID,
            spacing1=6, spacing3=6, font=("TkDefaultFont", 10))
        self.log.tag_config(
            "assistant", justify=tk.LEFT, lmargin1=10, lmargin2=10, rmargin=120,
            background="#f7f7f7", foreground="#1a1a1a",
            borderwidth=1, relief=tk.SOLID,
            spacing1=6, spacing3=6, font=("TkDefaultFont", 10))
        self.log.tag_config(
            "reasoning", justify=tk.LEFT, lmargin1=10, lmargin2=10, rmargin=150,
            background="#eaf2fb", foreground="#4a6b8a",
            borderwidth=1, relief=tk.SOLID,
            spacing1=4, spacing3=4, font=("TkDefaultFont", 9, "italic"))
        self.log.tag_config(
            "system", justify=tk.CENTER, foreground="#888888",
            spacing1=4, spacing3=4, font=("TkDefaultFont", 9))
        self.log.tag_config(
            "error", justify=tk.CENTER, foreground="#b00020",
            spacing1=4, spacing3=4, font=("TkDefaultFont", 9))
        self._last_bubble_tag = None
        self._reason_start_idx = None

        self.vla_text = scrolledtext.ScrolledText(
            vla_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=12,
        )
        self.vla_text.pack(fill=tk.BOTH, expand=True)

        self._append_debug(f"zones: {', '.join(node.zone_names)}")
        if node.control_backend == "smolvla":
            self._append_debug(
                "SmolVLA mode: chat text is parsed, then rewritten into a "
                "canonical trained sentence"
            )
            self._append_debug(
                "zone goals: VLA cruises the lane, navigator watches the zone "
                "coordinates and this GUI stops the VLA on arrival"
            )
            self._append_debug(
                "예: 'T2로 가', 'change to lane1', 'speed 200', 'stop'"
            )
        else:
            self._append_debug("예: 'M3로 가', '2차선 따라서 crosswalk_stop까지 가', '1차선으로 변경', '정지'")
        if self.voice_available:
            self._append_debug(f"voice ready: whisper={WHISPER_MODEL}")
            self._append_debug("voice auto-send: on")
        else:
            self._append_debug("voice disabled: install sounddevice and faster-whisper")
        self.entry.focus_set()
        self.root.after(150, self._drain_status)
        self.root.after(250, self._refresh_vla_panel)
        if node.control_backend == "smolvla":
            node.start_scene_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._send_text(text)

    def _send_text(self, text):
        self._append("user", text)
        self._append_debug(f"User: {text}")
        if self.node.control_backend == "smolvla":
            # The parse step may call the LLM, so keep it off the Tk thread.
            self.send_button.config(state=tk.DISABLED)
            self.voice_button.config(state=tk.DISABLED)
            self.status_text.set(self._debug_text(extra="thinking..."))

            def smolvla_worker():
                response = self.node.dispatch_smolvla_instruction(text)
                self.root.after(0, lambda: self._handle_smolvla_result(response))

            threading.Thread(target=smolvla_worker, daemon=True).start()
            return
        self.send_button.config(state=tk.DISABLED)
        self.voice_button.config(state=tk.DISABLED)
        self.status_text.set(self._debug_text(extra="thinking..."))

        def worker():
            parsed, latency, error = self.node.parse_command(text)
            self.root.after(0, lambda: self._handle_result(parsed, latency, error))

        threading.Thread(target=worker, daemon=True).start()

    def _stop_smolvla(self):
        response = self.node.dispatch_smolvla_instruction("")
        self.status_text.set(self._debug_text(extra=response))
        self._append("assistant", response)
        self._append_debug(f"Action: {response}")

    def _handle_smolvla_result(self, response):
        self.send_button.config(state=tk.NORMAL)
        if self.voice_available and not self.recording and not self.voice_busy:
            self.voice_button.config(state=tk.NORMAL)
        self.status_text.set(self._debug_text(extra=response))
        self._append("assistant", response)
        self._append_debug(f"Action: {response}")

    def _handle_result(self, parsed, latency, error):
        self.send_button.config(state=tk.NORMAL)
        if self.voice_available and not self.recording and not self.voice_busy:
            self.voice_button.config(state=tk.NORMAL)
        if error:
            self.status_text.set(self._debug_text(extra=f"error: {error}"))
            self._append("error", f"오류: {error}")
            self._append_debug(f"Error: {error}")
            return
        response = self.node.dispatch_plan(parsed)
        self.node.last_action_text = response
        compact = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        self.status_text.set(self._debug_text(latency=latency))
        self._append("assistant", response)
        self._append_debug(f"Action: {response}")
        self._append_debug(compact)
        self._append_debug(self._debug_text(latency=latency))

    def _toggle_voice(self):
        if not self.voice_available or self.voice_busy:
            return
        if self.recording:
            self._stop_voice_recording()
        else:
            self._start_voice_recording()

    def _start_voice_recording(self):
        self.record_frames = []

        def audio_cb(indata, _frames, _time_info, status):
            if status:
                self.root.after(0, lambda: self._append_debug(f"Voice status: {status}"))
            self.record_frames.append(indata.copy())

        try:
            self.record_stream = sd.InputStream(
                samplerate=VOICE_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                callback=audio_cb,
            )
            self.record_stream.start()
        except Exception as exc:
            self.record_stream = None
            self.record_frames = []
            self._append_debug(f"Voice error: {exc}")
            return

        self.recording = True
        self.voice_button.config(text="Stop voice")
        self.send_button.config(state=tk.DISABLED)
        self.status_text.set(self._debug_text(extra="recording voice..."))
        self._append_debug("Voice: recording started")

    def _stop_voice_recording(self):
        stream = self.record_stream
        self.record_stream = None
        self.recording = False
        self.voice_busy = True
        self.voice_button.config(text="Transcribing...", state=tk.DISABLED)
        self.send_button.config(state=tk.DISABLED)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                self._append_debug(f"Voice stop error: {exc}")

        frames = list(self.record_frames)
        self.record_frames = []
        if not frames:
            self._finish_voice("")
            return

        audio = np.concatenate(frames, axis=0).reshape(-1).astype(np.float32)

        def worker():
            try:
                text = self._transcribe_voice(audio)
                error = None
            except Exception as exc:
                text = ""
                error = str(exc)
            self.root.after(0, lambda: self._finish_voice(text, error))

        threading.Thread(target=worker, daemon=True).start()

    def _transcribe_voice(self, audio):
        if self.whisper_model is None:
            self.whisper_model = WhisperModel(
                WHISPER_MODEL,
                device="cpu",
                compute_type="int8",
            )
        segments, _info = self.whisper_model.transcribe(
            audio,
            beam_size=3,
            vad_filter=True,
            # Korean commands mis-detect as Japanese/Chinese on short
            # utterances with auto language; the GUI's scene_lang toggle is
            # the intent signal, so follow it.
            language="ko" if self.node.scene_lang != "en" else "en",
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return self._normalize_voice_text(text)

    @staticmethod
    def _normalize_voice_text(text):
        replacements = {
            "엠 원": "M1",
            "엠원": "M1",
            "엠 투": "M2",
            "엠투": "M2",
            "엠 쓰리": "M3",
            "엠쓰리": "M3",
            "티 원": "T1",
            "티원": "T1",
            "티 투": "T2",
            "티투": "T2",
            "티 쓰리": "T3",
            "티쓰리": "T3",
            "티 포": "T4",
            "티포": "T4",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text.strip()

    def _finish_voice(self, text, error=None):
        self.voice_busy = False
        self.voice_button.config(text="Voice")
        if self.voice_available:
            self.voice_button.config(state=tk.NORMAL)
        self.send_button.config(state=tk.NORMAL)
        if error:
            self.status_text.set(self._debug_text(extra=f"voice error: {error}"))
            self._append_debug(f"Voice error: {error}")
            return
        if not text:
            self.status_text.set(self._debug_text(extra="voice: no speech"))
            self._append_debug("Voice: no speech")
            return
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        self.status_text.set(self._debug_text(extra=f"voice: {text}"))
        self._append_debug(f"Voice: {text}")
        if self.voice_auto_send.get():
            self._send_text(text)

    def _drain_status(self):
        try:
            while True:
                tag, message = self.node.event_q.get_nowait()
                if tag == "assistant":
                    self._append("assistant", message)
                    self.node.last_action_text = message
                elif tag == "narration":
                    # Short motion ticker lives in the chat header, not the
                    # transcript — the transcript gets scene commentary
                    # bubbles from the scene worker instead.
                    self.ticker_var.set(f"🚗 {message}")
                elif tag == "scene":
                    self._append("reasoning", message)
                self._append_debug(f"Event[{tag}]: {message}")
        except queue.Empty:
            pass
        try:
            while True:
                status = self.node.status_q.get_nowait()
                self.status_text.set(self._debug_text(status=status))
                self._append_debug("Status: " + status)
        except queue.Empty:
            pass
        self.root.after(150, self._drain_status)

    def _refresh_vla_panel(self):
        text = self.node.vla_judgment_text()
        self.vla_text.configure(state=tk.NORMAL)
        self.vla_text.delete("1.0", tk.END)
        self.vla_text.insert(tk.END, text)
        self.vla_text.configure(state=tk.DISABLED)
        self._refresh_vla_debug_window()
        # 1 Hz is enough for a status panel; 500 ms full-text rewrites were a
        # visible part of the GUI stutter alongside the YOLO GPU contention.
        self.root.after(1000, self._refresh_vla_panel)

    def _debug_text(self, latency=None, status=None, extra=None):
        parsed = self.node.last_parsed or {}
        steps = parsed.get("steps") or []
        if steps:
            steps_text = " -> ".join(self._step_label(step) for step in steps)
        else:
            steps_text = "-"
        if self.node.control_backend == "smolvla":
            parser_label = "SmolVLA (parsed instruction)"
        else:
            parser_label = (
                "learned action_policy"
                if self.node.parser_backend == "action_policy"
                else self.node.parser_model
            )
        lines = [
            f"Parser: {parser_label}",
            f"Steps: {steps_text}",
            f"Reason: {parsed.get('reason', '-')}",
            f"Dispatch: {self.node.last_dispatch}",
        ]
        if latency is not None:
            lines.append(f"Parse latency: {latency * 1000.0:.0f} ms")
        if status:
            lines.append(f"Navigator status: {status}")
        if extra:
            lines.append(str(extra))
        return "\n".join(lines)

    def _open_debug_window(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
            return

        self.debug_window = tk.Toplevel(self.root)
        self.debug_window.title("nav-vla Debug")
        self.debug_window.geometry("820x520")
        self.debug_window.minsize(560, 360)
        self.debug_window.protocol("WM_DELETE_WINDOW", self._close_debug_window)

        outer = ttk.Frame(self.debug_window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            outer,
            textvariable=self.status_text,
            style="Status.TLabel",
            justify=tk.LEFT,
            anchor=tk.NW,
        ).pack(fill=tk.X, anchor=tk.NW, pady=(0, 8))

        self.debug_log = scrolledtext.ScrolledText(
            outer,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.debug_log.pack(fill=tk.BOTH, expand=True)
        for line in self.debug_lines:
            self._write_debug_line(line)

    def _close_debug_window(self):
        if self.debug_window is not None:
            self.debug_window.destroy()
        self.debug_window = None
        self.debug_log = None

    def _open_vla_debug_window(self):
        if self.vla_debug_window is not None and self.vla_debug_window.winfo_exists():
            self.vla_debug_window.lift()
            return

        self.vla_debug_window = tk.Toplevel(self.root)
        self.vla_debug_window.title("nav-vla VLA Debug")
        self.vla_debug_window.geometry("920x640")
        self.vla_debug_window.minsize(620, 420)
        self.vla_debug_window.protocol("WM_DELETE_WINDOW", self._close_vla_debug_window)

        outer = ttk.Frame(self.vla_debug_window, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        self.vla_debug_log = scrolledtext.ScrolledText(
            outer,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.vla_debug_log.pack(fill=tk.BOTH, expand=True)
        self._refresh_vla_debug_window()

    def _close_vla_debug_window(self):
        if self.vla_debug_window is not None:
            self.vla_debug_window.destroy()
        self.vla_debug_window = None
        self.vla_debug_log = None

    def _refresh_vla_debug_window(self):
        if self.vla_debug_log is None:
            return
        self.vla_debug_log.configure(state=tk.NORMAL)
        self.vla_debug_log.delete("1.0", tk.END)
        self.vla_debug_log.insert(tk.END, self.node.alpamayo_debug_text())
        self.vla_debug_log.configure(state=tk.DISABLED)

    def _append_debug(self, text):
        line = str(text)
        self.debug_lines.append(line)
        if len(self.debug_lines) > 1000:
            self.debug_lines = self.debug_lines[-1000:]
        self._write_debug_line(line)

    def _write_debug_line(self, line):
        if self.debug_log is None:
            return
        self.debug_log.configure(state=tk.NORMAL)
        self.debug_log.insert(tk.END, str(line) + "\n")
        self.debug_log.see(tk.END)
        self.debug_log.configure(state=tk.DISABLED)

    @staticmethod
    def _step_label(step):
        action = step.get("action", "?")
        zone = step.get("zone")
        lane = step.get("lane")
        parts = [action]
        if zone:
            parts.append(str(zone))
        if lane and lane != "default":
            parts.append(str(lane))
        return ":".join(parts)

    def _append(self, tag, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n", tag)
        # 1 Hz commentary grows the transcript forever; an ever-growing Text
        # widget is a known Tk stutter source. Keep the last ~300 lines.
        if int(self.log.index("end-1c").split(".")[0]) > 400:
            self.log.delete("1.0", "100.0")
        self._last_bubble_tag = tag
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def close(self):
        if self.node.control_backend == "smolvla":
            self.node.dispatch_smolvla_instruction("")
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.destroy()
            self.debug_window = None
            self.debug_log = None
        if self.vla_debug_window is not None and self.vla_debug_window.winfo_exists():
            self.vla_debug_window.destroy()
            self.vla_debug_window = None
            self.vla_debug_log = None
        if self.record_stream is not None:
            try:
                self.record_stream.stop()
                self.record_stream.close()
            except Exception:
                pass
            self.record_stream = None
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main(args=None):
    rclpy.init(args=args)
    node = ChatGuiNode()
    ui = str(node.declare_parameter("ui", "dashboard").value)
    spin = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin.start()
    try:
        if ui == "legacy":
            ChatGuiWindow(node).run()
        else:
            from sant_vla_pkg.driving_dashboard import run_dashboard
            run_dashboard(node)
    finally:
        if node._ego_pose_stream is not None:
            node._ego_pose_stream.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

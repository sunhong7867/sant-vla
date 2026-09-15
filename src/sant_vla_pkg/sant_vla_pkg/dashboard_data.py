"""Geometry and bounded telemetry shared by the dashboard and its tests."""

import math
import json
import html
import threading
import time
import numpy as np


class StatusSummary:
    """Turn repeated bridge telemetry into changes a driver can act on."""
    def __init__(self):
        self.connected = False
        self.task = ""
        self.watchdog = 0
        self.watchdog_active = False
        self.slow = False
        self.override = None

    def feed(self, message):
        try:
            data = json.loads(html.unescape(str(message)))
        except (ValueError, TypeError):
            return []
        if not isinstance(data, dict):
            return []
        events = []
        if "task" in data:
            if not self.connected:
                events.append("차량 제어 연결됨 · 주행 지시 수신 중" if data["task"] else "차량 제어 연결됨 · 출발 명령 대기")
                self.connected = True
            task = str(data["task"])
            if task != self.task:
                lane = "안쪽 1차선" if "inner lane" in task else "바깥쪽 2차선" if "outer lane" in task else "새 경로"
                events.append(f"주행 지시 갱신 · {lane}" if task else "정지 지시 수신 · 남은 주행 동작 취소")
                self.task = task
        hits = data.get("watchdog_hits")
        if isinstance(hits, (int, float)):
            if hits > self.watchdog and not self.watchdog_active:
                events.append("주행 입력 지연 감지 · 안전 정지 발생")
                self.watchdog_active = True
            self.watchdog = hits
        if self.watchdog_active and isinstance(data.get("queue"), (int, float)) and data["queue"] > 0:
            events.append("주행 입력 수신 정상화")
            self.watchdog_active = False
        latency = data.get("latency_ms")
        if isinstance(latency, (int, float)):
            slow = latency > (400 if self.slow else 500)
            if slow != self.slow:
                events.append(f"모델 응답 지연 · {latency:.0f} ms" if slow else "모델 응답 지연 해소")
                self.slow = slow
        override = data.get("override")
        if override is not None and override != self.override:
            if override == "hold":
                events.append("감독 정지 · 장애물 또는 신호 조건 확인 중")
            self.override = override
        return events


def integrate_actions(actions, pose):
    """Project raw body-frame (dx, dy, dyaw) increments into Gazebo world XY.

    This is the model's unshaped prediction, not the executed controller path.
    """
    x, y, yaw = pose
    points = [(x, y)]
    for action in actions[:200]:
        if len(action) != 3:
            raise ValueError("Expected dx, dy, dyaw")
        dx, dy, dyaw = map(float, action)
        if not all(math.isfinite(v) for v in (dx, dy, dyaw)):
            raise ValueError("Non-finite action")
        c, s = math.cos(yaw), math.sin(yaw)
        x, y = x + c * dx - s * dy, y + s * dx + c * dy
        yaw += dyaw
        points.append((x, y))
    return points


class Telemetry:
    """Latest-only mailbox: camera/ROS callbacks never enqueue video frames."""

    def __init__(self):
        self._lock = threading.Lock()
        self._values = {}

    def put(self, key, value):
        with self._lock:
            self._values[key] = (time.monotonic(), value)

    def snapshot(self):
        with self._lock:
            return dict(self._values)

    def clear_motion(self):
        with self._lock:
            for key in ("pose", "plan", "plan_info", "image"):
                self._values.pop(key, None)

    def clear_plan(self):
        with self._lock:
            for key in ("plan", "plan_info"):
                self._values.pop(key, None)


def project_ground_path(points, model_pose, image_size, camera_pose, hfov):
    """World ground points -> RGB pixels using the SDF camera's +X optical axis.

    Model yaw is the Gazebo model yaw. The camera extrinsic is relative to that
    model (including sensor/link transforms); output excludes behind-camera points.
    """
    width, height = image_size
    if not points or width <= 0 or height <= 0:
        return []
    mx, my, yaw = model_pose
    x, y, z, roll, pitch, cyaw = camera_pose
    cr,sr,cp,sp,cy,sy = math.cos(roll),math.sin(roll),math.cos(pitch),math.sin(pitch),math.cos(cyaw),math.sin(cyaw)
    rotation = np.array([[cy*cp,cy*sp*sr-sy*cr,cy*sp*cr+sy*sr],
                         [sy*cp,sy*sp*sr+cy*cr,sy*sp*cr-cy*sr],[-sp,cp*sr,cp*cr]])
    c,s = math.cos(yaw),math.sin(yaw)
    focal = width/(2*math.tan(hfov/2))
    pixels = []
    for wx,wy in points:
        dx,dy = wx-mx,wy-my
        model = np.array([c*dx+s*dy-x, -s*dx+c*dy-y, -0.01265-z])
        forward,left,up = rotation.T @ model
        if forward <= 0.2:
            continue
        u,v = width/2-focal*left/forward, height/2-focal*up/forward
        if 0 <= u < width and 0 <= v < height:
            pixels.append((float(u),float(v)))
    return pixels


def fresh(snapshot, key, age=2.0, now=None):
    item = snapshot.get(key)
    if item is None:
        return None
    now = time.monotonic() if now is None else now
    return item[1] if now - item[0] <= age else None

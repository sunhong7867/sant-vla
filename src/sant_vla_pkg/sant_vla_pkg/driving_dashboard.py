"""Single-window driving console; ROS callbacks never touch Qt widgets."""

from collections import deque
import html
import json
import math
import os
from pathlib import Path
import queue
import random
import re
import signal
import urllib.request
import threading
import time
import xml.etree.ElementTree as ET

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal, QObject, QEvent
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QComboBox, QCheckBox,
    QPushButton, QSplitter, QTabWidget, QTextBrowser, QVBoxLayout, QWidget, QGridLayout, QSizePolicy,
)

from sant_vla_pkg.dashboard_data import Telemetry, StatusSummary, fresh, integrate_actions, project_ground_path
from sant_vla_pkg.dashboard_voice import VoiceInput
from sant_vla_pkg.dashboard_language import DisplayLanguage
from sant_vla_pkg.gazebo_services import move_camera, pose_message, request, top_camera_pose
from sant_vla_pkg.race_scenarios import (atomic_json, load_scenarios, model_directory,
                                         obstacle_body_yaw, reset_scenario, set_signal,
                                         static_model)
from sant_vla_pkg.gazebo_panel import GazeboPanel
from sant_vla_pkg.gz_pose import WorldPoseStream, list_models, resolve_gz_bin
from sant_vla_pkg.gz_reset import set_model_pose
from sant_vla_pkg import goto_command
from sant_vla_pkg import goto_layout as G


STYLE = """
QMainWindow, QWidget { background: #0b1220; color: #e5edf8;
  font-family: 'Noto Sans CJK KR', 'DejaVu Sans'; font-size: 12px; }
QFrame#card { background: #111c2c; border: 1px solid #243247; border-radius: 12px; }
QFrame#card QLabel { background: transparent; border: none; }
QLabel#muted { color: #8c9db5; font-size: 11px; }
QLabel#section { font-size: 13px; font-weight: 700; }
QLabel#metric { font-size: 15px; font-weight: 600; }
QLabel#status { color: #6de3ce; padding: 6px 10px; background: #142d32; border-radius: 8px; }
QPushButton { background: #1c2c42; border: 1px solid #30435d; border-radius: 7px;
  padding: 7px 12px; font-weight: 600; }
QPushButton:hover { background: #2b405d; border-color: #7895bb; }
QPushButton:pressed, QPushButton:checked { background: #255b65; border-color: #6de3ce; }
QPushButton:disabled { color: #65748b; background: #152033; }
QPushButton#primary { background: #67dfcb; color: #082322; border: none; }
QPushButton#stop { background: #572633; color: #ffb8bd; border: 1px solid #944451; }
QLineEdit { background: #0c1626; border: 1px solid #354960; border-radius: 9px;
  padding: 11px; selection-background-color: #296d75; }
QLineEdit:focus { border-color: #6de3ce; }
QTextBrowser { background: #111c2c; border: none; padding: 8px; }
QSplitter::handle { background: #0b1220; width: 8px; height: 8px; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #111c2c; padding: 9px 14px; color: #8c9db5; }
QTabBar::tab:selected { color: #6de3ce; border-bottom: 2px solid #6de3ce; }
QScrollBar:vertical { background: #111c2c; width: 7px; }
QScrollBar::handle:vertical { background: #354960; border-radius: 3px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def label(text, name=None):
    result = QLabel(text)
    if name:
        result.setObjectName(name)
    return result


def card(title, subtitle=None):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    layout.addWidget(label(title, "section"))
    if subtitle:
        info = label(subtitle, "muted")
        info.setWordWrap(True)
        layout.addWidget(info)
    return frame, layout



SMOLVLA_ONLY = os.environ.get("NAVVLA_PERCEIVER", "qwen") == "smolvla"
LOOK_RE = re.compile(r"보여|보이|보입|뭐가\s*있|뭐\s*있|what.*see", re.I)
REVERSE_RE = re.compile(r"뒤로|후진|빠꾸|back\s*up|reverse|backward", re.I)
# "그럼 바리케이트로" — a known name with the verb left out (10-14: went to the chat, which promised to drive)
ELLIPTIC_GOTO_RE = re.compile(r"(으로|로|쪽으로|쪽)\s*[.!~]*\s*$")
# a text-only chat model cannot move the car; sentences that promise to (10-14: "바리케이드 쪽으로 이동하겠습니다")
PROMISE_RE = re.compile(r"(이동|출발|접근|조정|주행|향|움직이|가|가\s?보|찾아\s?보|확인해\s?보)(하|해)?\s*겠")

class CameraView(QWidget):
    def __init__(self):
        super().__init__()
        self.frame = QImage()
        self.note = "카메라 신호 대기 중"
        self.path_pixels = []
        self.setMinimumSize(180, 90)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#080e19"))
        if not self.frame.isNull():
            viewport = self.rect().adjusted(0, 28 if self.note else 0, 0, 0)
            size = self.frame.size().scaled(viewport.size(), Qt.KeepAspectRatio)
            rect = QRectF((self.width() - size.width()) / 2,
                          viewport.y() + (viewport.height() - size.height()) / 2,
                          size.width(), size.height())
            painter.drawImage(rect, self.frame)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(QPen(QColor("#69f9c9"), 2))
            painter.setBrush(QColor("#69f9c9"))
            previous = None
            for u,v in self.path_pixels:
                pixel = QPointF(rect.x()+u*rect.width()/self.frame.width(),
                                rect.y()+v*rect.height()/self.frame.height())
                if previous is not None:
                    painter.drawLine(previous, pixel)
                painter.drawEllipse(pixel, 3, 3)
                previous = pixel
        if self.note:
            painter.fillRect(0, 0, self.width(), 28, QColor("#142133"))
            painter.setPen(QColor("#a8b9d0"))
            painter.drawText(self.rect().adjusted(10, 0, -10, 0), Qt.AlignTop, self.note)


DRIVE_KEYS = {Qt.Key_W, Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_Space}


class DriveCameraView(CameraView):
    """Front camera that doubles as the manual-drive pad (lecture mode, 2026-10-08):
    click it and W/A/S/D drive the car; Esc, a click anywhere else or leaving the
    window ends it (the window's event filter clears the focus). Only key state
    lives here; the window turns it into /cmd_vel."""
    drive_focus = Signal(bool)

    def __init__(self):
        super().__init__()
        self.drive_enabled = False
        # Keys currently down. Only a real (non-auto-repeat) release or losing
        # focus clears one: X11 auto-repeats just the LAST key pressed, so with
        # W + A held, W stops repeating — a "no repeat for 1 s = released" rule
        # dropped the other key and the steering let go (user report 10-08).
        self.held = {}
        self.drive_text = ""

    def enable_drive(self):
        self.drive_enabled = True
        self.setFocusPolicy(Qt.ClickFocus)
        self.setToolTip("클릭하면 수동주행: W/S 가속·감속(후진), A/D 조향, Space 정지\n"
                        "다른 곳을 클릭하거나 Esc 를 누르면 수동주행이 꺼집니다.")

    def mousePressEvent(self, event):
        if self.drive_enabled:
            event.accept()           # do not propagate: the parent card would end it again
        else:
            super().mousePressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if not self.drive_enabled:
            return
        if event.reason() != Qt.MouseFocusReason:
            # Qt hands focus back to the last focus widget when the window is
            # re-activated; only a click on the camera may start driving.
            QTimer.singleShot(0, self.clearFocus)
            return
        self.drive_focus.emit(True)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.held.clear()
        if self.drive_enabled:
            self.drive_focus.emit(False)
            self.update()

    def keyPressEvent(self, event):
        if self.drive_enabled and event.key() == Qt.Key_Escape:
            self.clearFocus()
        elif self.drive_enabled and event.key() in DRIVE_KEYS:
            self.held[event.key()] = time.monotonic()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.drive_enabled and event.key() in DRIVE_KEYS:
            if not event.isAutoRepeat():
                self.held.pop(event.key(), None)
        else:
            super().keyReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not (self.drive_enabled and self.hasFocus()):
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#6de3ce"), 3))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        painter.fillRect(0, self.height() - 26, self.width(), 26, QColor("#0f3a37"))
        painter.setPen(QColor("#d8fff8"))
        painter.drawText(self.rect().adjusted(10, 0, -10, -6), Qt.AlignBottom | Qt.AlignLeft,
                         self.drive_text or "수동주행 · W/S 가감속 · A/D 조향 · Space 정지 · Esc/다른 곳 클릭 = 해제")


# BEV footprint (half-extents along/across the body, metres) per obstacle model
# family, for drawing only. Cars keep the original 1.8 x 4.4 m rectangle.
OBSTACLE_FOOTPRINT = {"ob_box": (.8, .8), "ob_barrel": (.5, .5), "ob_cone": (.6, .6),
                      "ob_barrier": (.25, 1.2), "ob_person": (.25, .25), "cone": (.4, .4)}
OBSTACLE_Z = 0.01265
# Palette labels (Korean; DisplayLanguage translates known pairs)
OBSTACLE_LABEL = {"prius_hybrid": "차량 (ego 와 동일)", "hatchback": "해치백", "hatchback_red": "해치백 빨강",
                  "hatchback_blue": "해치백 파랑", "hatchback_green": "해치백 초록",
                  "hatchback_yellow": "해치백 노랑", "ob_box": "박스", "ob_barrel": "드럼통",
                  "ob_cone": "꼬깔", "ob_barrier": "바리케이드", "ob_person": "사람"}


def obstacle_models():
    """Model dirs the lecture editor may spawn: the ego car itself, the hatchbacks
    and the ob_* props (simulation_pkg/models). prius_hybrid_ob* are legacy copies."""
    names = []
    try:
        for d in sorted(model_directory().iterdir()):
            n = d.name
            if (d / "model.sdf").is_file() and (
                    n == "prius_hybrid" or n.startswith("hatchback") or n.startswith("ob_")):
                names.append(n)
    except OSError:
        pass
    return names


class BevView(QWidget):
    """World-frame map, actual trajectory and raw VLA chunk with shared scale.

    With `editable` (lecture mode) obstacles can be dragged, and a right-click
    adds or removes one; the widget only emits signals, the window talks to gz.
    """
    obstacle_add = Signal(str, float, float)      # model, world x, y
    obstacle_move = Signal(str, float, float)     # entity, world x, y
    obstacle_remove = Signal(str)                 # entity
    obstacle_selected = Signal(str)               # entity ("" = none)
    place_done = Signal()                         # placement click consumed

    def __init__(self, lanes, zones):
        super().__init__()
        self.editable = False
        self.place_model = None      # model to drop on the next left click
        self.selected = None         # entity highlighted (Delete removes it)
        self.drag_ob = None          # entity being dragged (editable only)
        self._press_pos = None
        self._frame = None           # (cx, cy, scale) of the last paint
        self.setFocusPolicy(Qt.ClickFocus)
        self.lanes = lanes or {}
        self.zones = zones
        self.pose = None
        self.trail = deque(maxlen=1800)
        self.prediction = []
        self.obstacles = []
        self.lane = "lane2"
        self.follow = False
        self.rotated = True
        self.zoom = 1.0
        self.pan = QPointF()
        self.drag = None
        self.translate = lambda text: text
        self.setMinimumSize(260, 140)
        self.setMouseTracking(True)

    def reset_view(self):
        self.zoom = 1.0
        self.pan = QPointF()
        self.update()

    def wheelEvent(self, event):
        self.zoom = max(0.5, min(12.0, self.zoom * (1.15 if event.angleDelta().y() > 0 else 1 / 1.15)))
        self.update()

    # ---- pixel <-> world (inverse of pt() in paintEvent, same frame) ----
    def to_world(self, pos):
        if not self._frame:
            return None
        cx, cy, scale = self._frame
        dx = (pos.x() - self.width() / 2 - self.pan.x()) / scale
        dy = (self.height() / 2 - pos.y() + self.pan.y()) / scale
        if self.rotated:
            dx, dy = -dy, dx
        return cx + dx, cy + dy

    def obstacle_at(self, pos):
        w = self.to_world(pos)
        if w is None:
            return None
        best, best_d = None, 2.8
        for ob in self.obstacles:
            d = math.hypot(ob["x"] - w[0], ob["y"] - w[1])
            if d < best_d:
                best, best_d = ob, d
        return best

    def set_place_model(self, model):
        self.place_model = model
        self.setCursor(Qt.CrossCursor if model else Qt.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._press_pos = event.position()
        if self.editable and self.place_model:
            w = self.to_world(event.position())
            if w is not None:
                model, self.place_model = self.place_model, None
                self.setCursor(Qt.ArrowCursor)
                self.obstacle_add.emit(model, w[0], w[1])
                self.place_done.emit()
            return
        hit = self.obstacle_at(event.position()) if self.editable else None
        if hit is not None and hit.get("entity"):
            self.drag_ob = hit["entity"]
            self.selected = hit["entity"]
            self.obstacle_selected.emit(self.selected)
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
        else:
            self.drag = event.position()

    def mouseMoveEvent(self, event):
        if self.drag_ob is not None:
            w = self.to_world(event.position())
            for ob in self.obstacles:
                if ob.get("entity") == self.drag_ob and w is not None:
                    ob["x"], ob["y"] = w
            self.update()
        elif self.drag is not None:
            self.pan += event.position() - self.drag
            self.drag = event.position()
            self.update()
        elif self.editable and not self.place_model:
            self.setCursor(Qt.OpenHandCursor if self.obstacle_at(event.position()) else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.drag_ob is not None:
            entity, self.drag_ob = self.drag_ob, None
            self.setCursor(Qt.ArrowCursor)
            moved = (self._press_pos is not None
                     and (event.position() - self._press_pos).manhattanLength() > 4)
            w = self.to_world(event.position())
            if moved and w is not None:
                self.obstacle_move.emit(entity, w[0], w[1])
        elif (self.editable and self.selected and self._press_pos is not None
              and (event.position() - self._press_pos).manhattanLength() <= 4):
            self.selected = None            # plain click on empty map: deselect
            self.obstacle_selected.emit("")
            self.update()
        self.drag = None
        self._press_pos = None

    def keyPressEvent(self, event):
        if self.editable and event.key() == Qt.Key_Escape and self.place_model:
            self.set_place_model(None)
            self.place_done.emit()
        elif self.editable and event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.selected:
            entity, self.selected = self.selected, None
            self.obstacle_selected.emit("")
            self.obstacle_remove.emit(entity)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0c1523"))
        points = [v for lane in self.lanes.values() for v in lane]
        if not points:
            p.setPen(QColor("#9aacbf"))
            p.drawText(self.rect(), Qt.AlignCenter, self.translate("차선 지도 없음 · track_paths.json 확인"))
            return
        xs, ys = zip(*points)
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        extent_x, extent_y = max(xs)-min(xs), max(ys)-min(ys)
        if self.rotated:
            extent_x, extent_y = extent_y, extent_x
        scale = min((self.width() - 70) / max(1, extent_x),
                    (self.height() - 40) / max(1, extent_y)) * self.zoom
        if self.follow and self.pose:
            cx, cy = self.pose[:2]
        self._frame = (cx, cy, scale)
        def pt(x, y):
            dx, dy = x-cx, y-cy
            if self.rotated:
                dx, dy = dy, -dx
            return QPointF(self.width() / 2 + dx * scale + self.pan.x(),
                           self.height() / 2 - dy * scale + self.pan.y())
        p.setPen(QPen(QColor("#172538"), 1))
        for x in range(-100, 101, 5):
            p.drawLine(pt(x, -100), pt(x, 100))
        for y in range(-100, 101, 5):
            p.drawLine(pt(-100, y), pt(100, y))
        def path_line(values, color, width, closed=False):
            if not values:
                return
            path = QPainterPath(pt(*values[0]))
            for point in list(values)[1:]:
                path.lineTo(pt(*point))
            if closed:
                path.closeSubpath()
            p.setPen(QPen(QColor(color), width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        for lane, values in self.lanes.items():
            path_line(values, "#202e41", max(4, 1.8 * scale), True)
            path_line(values, "#647994" if lane != self.lane else "#85a7d5", 1.5, True)
        p.setFont(QFont("DejaVu Sans", 8))
        for name, zone in self.zones.items():
            if self.zoom < 2 and name not in {"Start", "M2", "T2", "M3", "T3", "T4"}:
                continue
            pose = zone.get("pose", {})
            if "x" not in pose or "y" not in pose:
                continue
            center = pt(pose["x"], pose["y"])
            p.setPen(QColor("#93a8c4"))
            p.setBrush(QColor("#283c55"))
            p.drawEllipse(center, 3, 3)
            p.drawText(center + QPointF(5, -5), name)
        for obstacle in self.obstacles:
            x, y, yaw = obstacle["x"], obstacle["y"], obstacle.get("yaw", 0)
            model = obstacle.get("model", "") or ""
            if model in OBSTACLE_FOOTPRINT:
                hx, hy = OBSTACLE_FOOTPRINT[model]
            elif model in G.FLEET:                  # go-to-object props: round, radius r
                hx = hy = G.FLEET[model][1]
            else:
                hx, hy = .9, 2.2
            c, s = math.cos(yaw), math.sin(yaw)
            corners = [pt(x+c*dx-s*dy, y+s*dx+c*dy)
                       for dx,dy in [(-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)]]
            active = self.editable and obstacle.get("entity") in (self.drag_ob, self.selected)
            p.setPen(QPen(QColor("#ffffff" if active else "#ffead0"), 2 if active else 1))
            p.setBrush(QColor("#ff8c42" if model.startswith("ob_") else "#ffb76b"))
            p.drawPolygon(QPolygonF(corners))
            if self.editable and self.zoom >= 1.5:
                p.setPen(QColor("#ffead0"))
                p.drawText(pt(x, y) + QPointF(6, -6), obstacle.get("entity", ""))
        path_line(self.trail, "#59b9f7", 3)
        path_line(self.prediction, "#6dfbd0", 3)
        p.setBrush(QColor("#6dfbd0"))
        for point in self.prediction[::4]:
            p.drawEllipse(pt(*point), 2.5, 2.5)
        if self.pose:
            x, y, yaw = self.pose
            p.save()
            p.translate(pt(x, y))
            p.rotate((90 if self.rotated else 0)-math.degrees(yaw-math.pi/2))
            p.setPen(QPen(QColor("#d8fff8"), 1.5))
            p.setBrush(QColor("#38bfa9"))
            p.drawPolygon(QPolygonF([QPointF(11, 0), QPointF(-7, -6), QPointF(-4, 0), QPointF(-7, 6)]))
            p.restore()
        p.setPen(QPen(QColor("#8c9db5"), 2))
        p.drawLine(QPointF(14, self.height()-16), QPointF(14+5*scale, self.height()-16))
        p.drawText(QPointF(14, self.height()-23), "5 m")
        p.drawText(QPointF(self.width()-45, 20), "N →" if self.rotated else "N ↑")
        if self.editable and self.place_model:
            p.fillRect(0, 0, self.width(), 24, QColor("#1d3a2f"))
            p.setPen(QColor("#9ff2c9"))
            p.drawText(self.rect().adjusted(8, 0, -8, 0), Qt.AlignTop | Qt.AlignLeft,
                       self.translate("지도를 클릭해 놓기") + f" · {self.place_model} · Esc")


class ResultBus(QObject):
    parsed = Signal(int, str, object)
    failed = Signal(int, str)
    replied = Signal(str)
    service = Signal(str)
    scenario_done = Signal(str, str)
    goto_ready = Signal(int, str, str, str)     # generation, text, sector ("" = failed), note
    goal_status = Signal(str)                   # /goal_from_scene/status line (point-goal mode)


# Follow-camera offsets in the vehicle frame: (left, back, height).
# The low, close diagonal views are for checking whether a wheel touches a lane line.
FOLLOW_OFFSETS = {"ego": (0., 8., 5.), "ego_left": (2.5, 4.5, 2.), "ego_right": (-2.5, 4.5, 2.)}


class DashboardWindow(QMainWindow):
    def __init__(self, node, telemetry, launch_gazebo=True):
        super().__init__()
        self.node = node
        self.display_language = DisplayLanguage(node, self)
        self.telemetry = telemetry
        self.generation = 0
        self.closing = False
        self.parse_lock = threading.Lock()
        self.resetting = False
        self.close_after_reset = False
        self.sim_paused = False
        self.paused_snapshot = None
        self.pause_time = None
        self.require_connection = launch_gazebo
        self.lecture_mode = bool(getattr(node, "lecture_mode", False))
        self.avoid_default = bool(getattr(node, "avoid_enable", True))
        self.scenarios = load_scenarios()
        self.registry_path = Path(getattr(node, "avoid_obstacle_file", "/tmp/navvla-dashboard/obstacles.json"))
        self.language_path = self.registry_path.with_name("ui_language.json")
        self.persist_language = launch_gazebo
        self.startup_path = self.registry_path.with_name("startup.json")
        self.registry_mtime = None
        self.scene_mtime = None
        self.camera_calibration = None
        try:
            sdf = ET.parse(model_directory()/"prius_hybrid/model.sdf")
            link = next(l for l in sdf.findall(".//link") if l.find("sensor[@name='camera']") is not None)
            self.camera_calibration = (list(map(float, link.findtext("pose").split())),
                                       float(link.findtext("sensor[@name='camera']/camera/horizontal_fov")))
        except (OSError, ET.ParseError, StopIteration, ValueError, AttributeError):
            pass
        self.image_stamp = 0.0
        self.reason_stamp = 0.0
        self.reason_log = deque(maxlen=80)
        self.chat_log = deque(maxlen=120)
        self.event_log = deque(maxlen=200)
        self.bus = ResultBus(self)
        self.bus.parsed.connect(self.on_parsed)
        self.bus.failed.connect(self.on_failed)
        self.bus.replied.connect(self.on_replied)
        self.bus.service.connect(self.show_service_result)
        self.bus.scenario_done.connect(self.on_scenario_done)
        self.bus.goto_ready.connect(self.on_goto_ready)
        self.bus.goal_status.connect(self.on_goal_status)
        # point-goal mode (2026-10-13, g5d line): the sentence goes to goal_from_scene_node
        # (Qwen2.5-VL picks the object, LiDAR the distance) which feeds /vla_goal; the policy
        # only hears "Target.". Turned on by smolvla_demo.sh NAVVLA_POINT_GOAL=1.
        self.point_goal = os.environ.get("NAVVLA_POINT_GOAL", "0") == "1"
        self.goal_request_pub = None
        # go-to-object practice + manual driving (lecture mode, 2026-10-08)
        self.goto_objects = []       # placed layout objects (with "sector"), GUI thread only
        self.goto_origin = None      # car (x, y, yaw) when they were placed
        self.goto_run = None         # arrival watch for the last go-to command
        self.manual_v = 0.0
        self.manual_pub = None
        self.manual_timer = QTimer(self)
        self.manual_timer.timeout.connect(self.manual_tick)
        self.setWindowTitle("NAV / VLA · Driving Studio")
        self.resize(1540, 960)
        self.setMinimumSize(1080, 800)
        self.setStyleSheet(STYLE)
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        self.main_splitter = main = QSplitter(Qt.Horizontal)
        main.setChildrenCollapsible(False)
        self.left_splitter = left = QSplitter(Qt.Vertical)
        left.setChildrenCollapsible(False)
        scene, scene_layout = card("01  Simulation")
        config = Path(__file__).resolve().parents[1] / "config/dashboard_gazebo.config"
        if not config.exists():
            from ament_index_python.packages import get_package_share_directory
            config = Path(get_package_share_directory("sant_vla_pkg")) / "config/dashboard_gazebo.config"
        self.gazebo = GazeboPanel(config, launch=launch_gazebo)
        self.camera_mode = "top"
        self.fit_timer = QTimer(self)
        self.fit_timer.setSingleShot(True)
        self.fit_timer.timeout.connect(self.fit_top_view)
        self.gazebo.resized.connect(lambda: self.fit_timer.start(300))
        self.gazebo.ready.connect(lambda: self.fit_timer.start(500))
        self.gazebo.setMinimumHeight(300)
        scene_layout.addWidget(self.gazebo, 1)
        left.addWidget(scene)

        lower = QSplitter(Qt.Horizontal)
        lower.setChildrenCollapsible(False)
        bev_panel, bev_layout = card("02  BEV · Lanes & Paths")
        bev_tools = QHBoxLayout()
        self.bev = BevView(node._track_lanes, node.zones)
        self.bev.translate = self.display_language.text
        if self.lecture_mode:
            self.bev.editable = True
            self.bev.obstacle_add.connect(self.obstacle_add)
            self.bev.obstacle_move.connect(self.obstacle_move)
            self.bev.obstacle_remove.connect(self.obstacle_remove)
            self.bev.obstacle_selected.connect(self.on_obstacle_selected)
            self.bev.place_done.connect(lambda: self.place_button.setChecked(False))
        follow = QPushButton("차량 중심")
        follow.setCheckable(True)
        follow.toggled.connect(lambda enabled: setattr(self.bev, "follow", enabled))
        reset = QPushButton("전체 지도")
        reset.clicked.connect(lambda: (follow.setChecked(False), self.bev.reset_view()))
        bev_tools.addWidget(follow)
        bev_tools.addWidget(reset)
        rotate = QPushButton("지도 회전")
        rotate.clicked.connect(lambda: (setattr(self.bev, "rotated", not self.bev.rotated), self.bev.update()))
        bev_tools.addWidget(rotate)
        bev_tools.addStretch()
        bev_layout.addLayout(bev_tools)
        bev_layout.addWidget(self.bev, 1)
        self.bev_status = label("위치 신호 대기 중", "muted")
        self.bev_status.setWordWrap(True)
        bev_layout.addWidget(self.bev_status)
        legend = label('<span style="color:#85a7d5">━ 기준 차선</span>  '
                       '<span style="color:#59b9f7">━ 실제 궤적</span>  '
                       '<span style="color:#6de3ce">━ VLA 예측</span>  '
                       '<span style="color:#ffb76b">● 장애물</span>', "muted")
        legend.setWordWrap(True)
        self.bev.setToolTip("휠: 확대/축소 · 드래그: 이동\nVLA 예측은 제어 보정 전 모델 출력입니다.")
        bev_layout.addWidget(legend)
        lower.addWidget(bev_panel)
        camera_panel, camera_layout = card("03  Vehicle Cameras", "전방 영상 · 차량 중심 근접 탑뷰")
        camera_row = QHBoxLayout()
        self.camera = DriveCameraView()
        if self.lecture_mode:
            self.camera.enable_drive()
            self.camera.drive_focus.connect(self.set_manual_drive)
            QApplication.instance().installEventFilter(self)
        camera_row.addWidget(self.camera, 1)
        self.top_camera = CameraView()
        self.top_camera.note = "차량 탑뷰 · 신호 대기 중"
        camera_row.addWidget(self.top_camera, 1)
        camera_layout.addLayout(camera_row, 1)
        lower.addWidget(camera_panel)
        lower.setStretchFactor(0, 0)
        lower.setStretchFactor(1, 1)
        lower.setSizes([320, 780])
        left.addWidget(lower)
        left.setSizes([670, 245])
        main.addWidget(left)

        sidebar = QWidget()
        sidebar.setMinimumWidth(355)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        controls, controls_layout = card("DRIVING STUDIO")
        controls.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.setSpacing(6)
        status_row = QHBoxLayout()
        self.language_selector = QComboBox()
        self.language_selector.addItem("한국어", "ko")
        self.language_selector.addItem("English", "en")
        self.language_selector.setAccessibleName("Language / 언어")
        self.language_selector.setToolTip("채팅과 추론은 화면 표시용으로 번역합니다. 주행 명령과 모델 출력 원문은 유지됩니다.")
        self.language_selector.currentIndexChanged.connect(self.change_language)
        status_row.addWidget(self.language_selector)
        self.connection = label("● 연결 대기", "status")
        status_row.addWidget(self.connection, 1)
        stop = QPushButton("■ 정지")
        stop.setObjectName("stop")
        stop.clicked.connect(self.stop_driving)
        status_row.addWidget(stop)
        controls_layout.addLayout(status_row)
        metrics = QGridLayout()
        metrics.setVerticalSpacing(4)
        metrics.setHorizontalSpacing(14)
        self.metrics = {}
        for i, (key, title) in enumerate((("speed", "차량 속도"), ("lane", "목표 차선"),
                                         ("mode", "주행 상태"), ("latency", "추론 지연"))):
            metrics.addWidget(label(title, "muted"), 2*(i//2), i%2)
            value = label("—", "metric")
            self.metrics[key] = value
            metrics.addWidget(value, 2*(i//2)+1, i%2)
        controls_layout.addLayout(metrics)
        for group, actions in (("시점", (("전체 탑뷰", "top"), ("대각선", "overview"), ("차량 추적", "ego"),
                                  ("왼쪽 뒤", "ego_left"), ("오른쪽 뒤", "ego_right"))),
                               ("시뮬레이션", (("일시정지", "pause"), ("재개", "play")))):
            toolbar = QHBoxLayout()
            toolbar.setSpacing(5)
            toolbar.addWidget(label(group, "muted"))
            for title, action in actions:
                button = QPushButton(title)
                button.setStyleSheet("padding: 5px 7px;")
                button.clicked.connect(lambda _checked=False, a=action: self.camera_action(a))
                toolbar.addWidget(button)
            toolbar.addStretch()
            controls_layout.addLayout(toolbar)
        signal_row = QHBoxLayout()
        signal_row.setSpacing(5)
        signal_row.addWidget(label("신호등", "muted"))
        self.signal_buttons = {}
        for title, color in (("🔴 빨간불", "red"), ("🟢 초록불", "green")):
            button = QPushButton(title)
            button.setStyleSheet("padding: 5px 7px;")
            button.clicked.connect(lambda _checked=False, c=color: self.set_signal_color(c))
            self.signal_buttons[color] = button
            signal_row.addWidget(button)
        signal_row.addStretch()
        controls_layout.addLayout(signal_row)
        race_row = QHBoxLayout()
        self.race_selector = QComboBox()
        for key, scenario in self.scenarios.items():
            self.race_selector.addItem(scenario["label"], key)
        self.race_selector.activated.connect(self.change_scenario)
        race_row.addWidget(self.race_selector, 1)
        self.reset_button = QPushButton("경기 리셋")
        self.reset_button.clicked.connect(self.change_scenario)
        race_row.addWidget(self.reset_button)
        controls_layout.addLayout(race_row)
        self.race_status = label(self.scenarios["qualifying"]["description"], "muted")
        self.race_status.setWordWrap(True)
        controls_layout.addWidget(self.race_status)
        if self.lecture_mode:
            # 단기강좌: 경기 종류는 쓰지 않는다. 리셋은 lecture 배치로 되돌리는 용도.
            self.race_selector.hide()
            if "lecture" in self.scenarios:
                self.race_selector.setCurrentIndex(self.race_selector.findData("lecture"))
                self.race_status.setText(self.scenarios["lecture"]["description"])
            self.reset_button.setText("출발 위치로 리셋")
            # 장애물 팔레트: [모델][지도에 추가][선택 제거]. 추가를 누르면 다음 BEV
            # 클릭 지점에 놓인다(차선 2.5 m 안이면 스냅). 장애물 클릭=선택, 드래그=
            # 이동, Delete=제거.
            ob_row = QHBoxLayout()
            self.obstacle_model = QComboBox()
            for model in obstacle_models():
                self.obstacle_model.addItem(OBSTACLE_LABEL.get(model, model), model)
            self.obstacle_model.setCurrentIndex(max(0, self.obstacle_model.findData("prius_hybrid")))
            ob_row.addWidget(self.obstacle_model, 1)
            self.place_button = QPushButton("지도에 추가")
            self.place_button.setCheckable(True)
            self.place_button.toggled.connect(
                lambda on: self.bev.set_place_model(self.obstacle_model.currentData() if on else None))
            ob_row.addWidget(self.place_button)
            self.remove_button = QPushButton("선택 제거")
            self.remove_button.setEnabled(False)
            self.remove_button.clicked.connect(self.remove_selected_obstacle)
            ob_row.addWidget(self.remove_button)
            controls_layout.addLayout(ob_row)
            # 말로 지정한 물체로 가기: 차량 앞 왼쪽·정면·오른쪽에 물체 하나씩 (s1 학습 배치와 같은 규칙)
            goto_row = QHBoxLayout()
            self.goto_spawn_button = QPushButton("앞에 물체 3개")
            self.goto_spawn_button.setToolTip("지금 차량 앞 왼쪽·정면·오른쪽(±20°)에 무작위 물체를 하나씩 놓습니다.\n"
                                              "거리는 7~8 m 와 11.5~12.5 m 를 섞습니다(학습 데이터와 같은 규칙).")
            self.goto_spawn_button.clicked.connect(self.goto_spawn)
            goto_row.addWidget(self.goto_spawn_button)
            clear = QPushButton("물체 치우기")
            clear.clicked.connect(lambda: self.goto_clear())
            goto_row.addWidget(clear)
            self.goto_heldout = QCheckBox("미학습 물체 1개")
            self.goto_heldout.setToolTip("셋 중 하나를 학습에 없던 물체(공룡·로봇·사람·초록 꼬깔)로 바꿉니다.")
            goto_row.addWidget(self.goto_heldout)
            goto_row.addStretch()
            controls_layout.addLayout(goto_row)
            hint = label("물체로 가기: '왼쪽 물체로 가줘' (바로 전송) · '공룡으로 가줘' (VLM 이 화면에서 방향 판단)"
                         " · 수동주행: 전방 카메라 클릭 후 WASD", "muted")
            hint.setWordWrap(True)
            controls_layout.addWidget(hint)
            self.race_status.setText(self.race_status.text()
                                     + " · 장애물: 추가 후 지도 클릭, 클릭=선택, 드래그=이동, Delete=제거")
        sidebar_layout.addWidget(controls)

        self.right_splitter = right = QSplitter(Qt.Vertical)
        right.setChildrenCollapsible(False)
        chat_panel, chat_layout = card("04  Driving Chat")
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(False)
        chat_layout.addWidget(self.chat, 1)
        voice_row = QHBoxLayout()
        self.voice = VoiceInput(self)
        self.voice_button = QPushButton("음성 입력")
        self.voice_button.clicked.connect(self.voice.toggle)
        self.voice.state_changed.connect(self.voice_button.setText)
        self.voice.error.connect(lambda text: self.add_chat("error", text))
        self.voice.text_ready.connect(self.on_voice_text)
        voice_row.addWidget(self.voice_button)
        self.voice_auto_send = QCheckBox("인식 후 자동 전송")
        self.voice_auto_send.setChecked(True)
        voice_row.addWidget(self.voice_auto_send)
        voice_row.addStretch()
        chat_layout.addLayout(voice_row)
        input_row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("예: 1차선 따라 T2까지 가")
        self.entry.returnPressed.connect(self.send_entry)
        input_row.addWidget(self.entry, 1)
        self.send_button = QPushButton("전송 ↗")
        self.send_button.setObjectName("primary")
        self.send_button.clicked.connect(self.send_entry)
        input_row.addWidget(self.send_button)
        chat_layout.addLayout(input_row)
        self.command_status = label("명령 대기 중", "muted")
        self.command_status.setWordWrap(True)
        chat_layout.addWidget(self.command_status)
        right.addWidget(chat_panel)

        reason_panel, reason_layout = card("05  Reasoning")
        self.reason_tabs = QTabWidget()
        self.reasoning = QTextBrowser()
        self.reasoning.setPlainText("모델 reasoning 수신 대기 중\n현재 정책 서버에서 reasoning 출력을 켜야 표시됩니다.")
        self.scene_text = QTextBrowser()
        self.scene_text.setPlainText("장면 해설 대기 중 · 별도 관찰/해설 모듈의 출력입니다.")
        self.events = QTextBrowser()
        self.events.document().setMaximumBlockCount(200)
        self.status_summary = StatusSummary()
        self.last_status_connected = None
        self.events.setPlainText("연결·주행 지시·감독 정지·입력 지연 등 상태가 바뀔 때만 기록합니다.")
        self.reason_tabs.addTab(self.reasoning, "모델 reasoning")
        self.reason_tabs.addTab(self.scene_text, "장면 해설")
        self.reason_tabs.addTab(self.events, "주행 기록")
        reason_layout.addWidget(self.reason_tabs, 1)
        self.reason_status = label("모델 출력 대기 중", "muted")
        reason_layout.addWidget(self.reason_status)
        right.addWidget(reason_panel)
        right.setSizes([340, 230])
        sidebar_layout.addWidget(right, 1)
        main.addWidget(sidebar)
        main.setSizes([1110, 395])
        root.addWidget(main, 1)
        self.footer = label("ROS 2 · Gazebo · " + node.control_backend.upper() + "     |     실시간 데이터 연결 대기", "muted")
        root.addWidget(self.footer)
        self.add_chat("system", "주행 준비가 되면 명령을 입력하세요. 정지 버튼은 명령 해석을 기다리지 않고 즉시 동작합니다.")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(100)
        self._wide_layout = None
        self.apply_readable_layout()
        if self.persist_language:
            try:
                saved = json.loads(self.language_path.read_text()).get("language", "ko")
                self.language_selector.setCurrentIndex(1 if saved == "en" else 0)
            except (OSError, ValueError, AttributeError):
                pass

    def change_language(self, _index):
        self.display_language.language = self.language_selector.currentData()
        self.display_language.failed.clear()
        self.node.scene_lang = self.display_language.language
        if self.persist_language:
            try:
                self.language_path.parent.mkdir(parents=True, exist_ok=True)
                self.language_path.write_text(json.dumps({"language": self.display_language.language}))
            except OSError:
                self.record_event("언어 설정을 저장하지 못했습니다.")
        self.display_language.apply(self)
        self.camera.update()
        self.top_camera.update()

    def apply_readable_layout(self):
        if not hasattr(self, "events"):
            return
        wide = self.isFullScreen() or self.isMaximized() or self.width() >= 1900
        if wide == getattr(self, "_wide_layout", None):
            return
        self._wide_layout = wide
        self.main_splitter.setSizes([1000, 1000] if wide else [1110, 395])
        self.left_splitter.setSizes([700, 300] if wide else [670, 245])
        self.right_splitter.setSizes([600, 400])
        pixels = 20 if wide else 16
        for browser in (self.chat, self.reasoning, self.scene_text, self.events):
            browser.setStyleSheet(f"QTextBrowser {{ font-size: {pixels}px; }}")
            font = browser.font()
            font.setPixelSize(pixels)
            browser.document().setDefaultFont(font)
        self.entry.setStyleSheet(f"QLineEdit {{ font-size: {pixels}px; }}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.apply_readable_layout()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            QTimer.singleShot(0, self.apply_readable_layout)

    def record_event(self, text):
        self.event_log.append(f"<p><span style='color:#8c9db5'>{time.strftime('%H:%M:%S')}</span>"
                              f"　{html.escape(str(text))}</p>")
        self.events.setHtml("".join(self.event_log))

    def add_chat(self, role, text):
        if role in {"user", "assistant", "error"}:
            self.record_event(("입력: " if role == "user" else "") + str(text))
        colors = {"user": "#6de3ce", "assistant": "#dce7f7", "system": "#8c9db5", "error": "#ffb8bd"}
        names = {"user": "YOU", "assistant": "VLA ASSISTANT", "system": "STUDIO", "error": "알림"}
        alignment = "right" if role == "user" else "left"
        self.chat_log.append(f'<p align="{alignment}" style="color:{colors[role]}; margin-top:14px">'
                             f'<b>{names[role]}</b><br>{html.escape(str(text)).replace(chr(10), "<br>")}</p>')
        self.chat.setHtml("".join(self.chat_log))
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def on_voice_text(self, generation, text):
        if self.closing or self.resetting or generation != self.voice.generation:
            return
        if not text:
            self.add_chat("error", "인식된 음성이 없습니다. 다시 녹음해 주세요.")
            return
        self.entry.setText(text)
        if self.voice_auto_send.isChecked():
            self.send_entry()

    def send_entry(self):
        text = self.entry.text().strip()
        if text:
            self.entry.clear()
            self.send(text)

    def send(self, text):
        # Fast stop bypasses the parser and invalidates any pending LLM result.
        if text.strip().lower() in {"정지", "멈춰", "stop", "cancel", "pause"}:
            self.add_chat("user", text)
            self.stop_driving()
            return
        if not self.send_button.isEnabled():
            self.command_status.setText("경기 재설정 중입니다." if self.resetting else "명령 해석 중입니다. 정지는 언제든 사용할 수 있습니다.")
            return
        if self.require_connection and self.node.control_backend == "smolvla":
            if fresh(self.telemetry.snapshot(), "status", age=3) is None:
                self.add_chat("error", "차량 제어 연결이 아직 준비되지 않았습니다. 상단 연결 상태와 실행 로그를 확인해 주세요.")
                return
        if self.sim_paused:
            self.add_chat("error", "시뮬레이션을 재개한 뒤 출발 명령을 보내 주세요.")
            return
        if self.point_goal and getattr(self, "goal_asking", False) and self.is_goal_answer(text):
            # reply to the goal node's "이걸로 갈까요? (응 / 아니)" question
            self.add_chat("user", text)
            self.goal_asking = False
            from std_msgs.msg import String
            self.goal_request_pub.publish(String(data=f"answer:{text}"))
            return
        if REVERSE_RE.search(text):
            # 2026-10-13: "뒤로 조금만 가봐" was parsed into the nearest supported action (start driving
            # in the outer lane) and answered "뒤로 조금만 가보겠습니다". No policy here learned to reverse.
            self.add_chat("user", text)
            self.add_chat("assistant", "후진은 지금 모델이 배우지 않은 동작이라 할 수 없습니다. "
                                       "차를 뒤로 옮기려면 3D 화면을 클릭해 수동주행(S 키)을 써 주세요.")
            self.command_status.setText("후진은 지원하지 않음")
            return
        if self.point_goal and goto_command.is_goto(text, self.goto_nouns()):
            self.add_chat("user", text)
            self.send_point_goal(text)
            return
        if self.point_goal and SMOLVLA_ONLY and ELLIPTIC_GOTO_RE.search(text) and not REVERSE_RE.search(text):
            from sant_vla_pkg.smolvla_perceiver import names_in
            if names_in(text):
                self.add_chat("user", text)
                self.send_point_goal(text)
                return
        if self.point_goal and SMOLVLA_ONLY:
            # 2026-10-13: SmolVLA-only mode makes no Qwen call at all — "what do you see" is answered
            # by the goal node's SmolVLA head, everything else is out of scope
            self.add_chat("user", text)
            # every other sentence is conversation: ask the goal node what SmolVLA sees now, then a
            # text-only LLM (EXAONE, no image, no Qwen) words a natural reply from those facts
            self.sv_pending = text
            self.send_point_goal("look:", quiet=True)
            QTimer.singleShot(4000, lambda t=text: self._sv_look_timeout(t))
            return
        if self.goto_objects and goto_command.is_goto(text, self.goto_nouns()):
            self.add_chat("user", text)
            self.send_goto(text)
            return
        self.goto_run = None
        self.generation += 1
        generation = self.generation
        self.add_chat("user", text)
        self.send_button.setEnabled(False)
        self.command_status.setText("명령을 해석하고 있습니다…")
        def worker():
            try:
                with self.parse_lock:
                    if self.closing or generation != self.generation:
                        return
                    result = self.node.parse_command(text)
                if not self.closing:
                    self.bus.parsed.emit(generation, text, result)
            except Exception as exc:
                if not self.closing:
                    self.bus.failed.emit(generation, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def on_parsed(self, generation, text, result):
        if self.closing or generation != self.generation:
            return
        self.send_button.setEnabled(True)
        plan, latency, error = result
        if error:
            self.on_failed(generation, error)
            return
        # Do not forward failed/unsupported commands as unvalidated raw VLA text.
        if not plan or not any(s.get("action") != "none" for s in plan.get("steps", [])):
            # Not a driving command: answer as the assistant (state questions,
            # small talk) without touching the vehicle; template error if the
            # LLM is unavailable.
            self.command_status.setText("답변을 작성하고 있습니다…")
            self.chat_reply(text, generation)
            return
        if self.point_goal and any(s.get("action") not in ("none", "stop") for s in plan.get("steps", [])):
            # the point-goal policy (g5d) hears only "Target."; lane / zone / speed sentences mean
            # nothing to it (it crept off on "Start driving in the outer lane" in the 10-13 GUI test)
            self.add_chat("assistant", "지금은 목표 지점 모드라 정책이 차선 주행·차선 변경·구역 이동·속도 명령을 배우지 않았습니다. "
                                       "물체로 가기만 됩니다(예: '빨간 꼬깔로 가줘'). 멈추려면 '정지'라고 해 주세요.")
            self.command_status.setText("목표 지점 모드에서 지원하지 않는 명령")
            return
        try:
            if self.node.control_backend == "smolvla":
                response = self.node.dispatch_smolvla_instruction(text, parsed_result=result)
            else:
                response = self.node.dispatch_plan(plan)
            summary = self.command_summary(plan, response)
            self.command_status.setText(f"명령 전송 완료 · 해석 {latency:.2f}초 · 답변 작성 중…")
            facts = self.node.command_facts(plan.get("steps", []), response)
            self.phrase_reply(text, facts, fallback=summary, generation=generation)
        except Exception as exc:
            self.on_failed(generation, str(exc))

    def chat_reply(self, text, generation):
        """Not a driving command: open conversation with the live camera frame
        (node.assistant_chat), falling back to the short action-report reply."""
        chat = getattr(self.node, "assistant_chat", None)
        if chat is None:
            self.phrase_reply(text, "차량 동작 변화 없음(명령 아님)", fallback=None, generation=generation)
            return
        def worker():
            try:
                reply = chat(text)
            except Exception:                                   # noqa: BLE001
                reply = None
            if self.closing:
                return
            if reply:
                self.bus.replied.emit(reply)
            else:
                self.bus.failed.emit(generation, "답변을 만들지 못했습니다(모델 연결 실패 또는 형식에 맞지 않는 출력). 다시 물어봐 주세요.")
        threading.Thread(target=worker, daemon=True).start()

    def phrase_reply(self, text, event, fallback, generation):
        """Let the assistant LLM word the reply off the Qt thread. The event
        text is what actually happened (the deterministic summary), so the
        model can only rephrase it; `fallback` is shown when the LLM fails
        (None = report a failed command instead)."""
        def worker():
            try:
                reply = self.node.assistant_reply(text, event)
            except Exception:                                   # noqa: BLE001
                reply = None
            if self.closing:
                return
            if reply:
                self.bus.replied.emit(reply)
            elif fallback:
                self.node.remember_turn(text, fallback)
                self.bus.replied.emit(fallback)
            else:
                self.bus.failed.emit(generation, "실행 가능한 주행 명령을 찾지 못했습니다.")
        threading.Thread(target=worker, daemon=True).start()

    def on_replied(self, reply):
        # Not gated on generation: a reply for an earlier command still
        # belongs in the log even if a newer command is already in flight.
        if self.closing:
            return
        self.add_chat("assistant", reply)
        status = self.command_status.text()
        if status.endswith(" · 답변 작성 중…"):
            self.command_status.setText(status[:-len(" · 답변 작성 중…")])
        elif status == "답변을 작성하고 있습니다…":
            self.command_status.setText("답변 완료")

    def commanded_lane_name(self):
        # smolvla mode has no lane feedback: the commanded adapter lane is the
        # truth (current_lane can be overwritten by /lane_state estimates).
        lane = (self.node._vla_lane if self.node.control_backend == "smolvla"
                else self.node.current_lane)
        return "안쪽 1차선" if lane == "lane1" else "바깥쪽 2차선"

    def command_summary(self, plan, response):
        # Keep the exact canonical instruction in the status log, and make
        # the conversation about what the driver asked the vehicle to do.
        if ("보내지 않았" in response or "nothing was sent" in response.lower()
                or "not a trained" in response.lower()):
            return response
        lane = self.commanded_lane_name()
        if "〔예약〕" in response:
            # Staged waypoint plan: the zone is a pass-through, not a stop.
            steps = plan.get("steps", [])
            zone = next((s.get("zone") for s in steps
                         if s.get("action") == "drive_to_zone"), "목표 지점")
            names = {"lane1": "안쪽 1차선", "lane2": "바깥쪽 2차선"}
            target = next((names.get(s.get("lane"), "반대 차선") for s in steps
                           if s.get("action") in {"change_lane", "keep_lane"}),
                          None)
            tail = (f"도착하면 {target}으로 변경해" if target
                    else "도착하면 예약된 설정을 적용해")
            return (f"{zone}까지 {lane}을 유지해 이동하고, {tail} 정차 없이 "
                    "계속 주행합니다.")
        parts = []
        for step in plan.get("steps", []):
            action = step.get("action")
            if action == "start":
                parts.append(f"{lane} 주행 시작 명령을 보냈습니다.")
            elif action == "change_lane":
                parts.append(f"{lane}으로 차선 변경을 요청했습니다.")
            elif action == "keep_lane":
                parts.append(f"{lane}을 유지하도록 요청했습니다.")
            elif action == "stop":
                parts.append("정지 명령을 보냈습니다.")
            elif action in {"drive_to_zone", "drive_direct"}:
                route = "직행으로" if action == "drive_direct" else f"{lane}을 따라"
                parts.append(f"{route} {step.get('zone')}까지 이동한 뒤 정차하도록 요청했습니다.")
            elif action == "set_speed":
                if self.node.control_backend == "smolvla":
                    raw = step.get("speed", 0)
                    tier = "느린" if raw <= 90 else "보통" if raw <= 130 else "빠른"
                    parts.append(f"{tier} 속도 단계로 설정했습니다.")
                else:
                    parts.append(f"속도 설정을 {step.get('speed')}으로 변경했습니다.")
        if "no step sequencing" in response:
            parts.append("현재 VLA 모드는 여러 단계를 차례로 실행하지 않고 마지막 주행 설정을 적용합니다.")
        return "\n".join(parts) or response

    def on_failed(self, generation, error):
        if self.closing or generation != self.generation:
            return
        self.send_button.setEnabled(True)
        self.command_status.setText("명령 처리 실패")
        self.add_chat("error", error)

    def stop_driving(self):
        self.generation += 1
        self.goto_run = None
        self.telemetry.clear_plan()
        if self.paused_snapshot:
            self.paused_snapshot.pop("plan", None)
            self.paused_snapshot.pop("plan_info", None)
        self.voice.cancel()
        self.send_button.setEnabled(not self.resetting)
        if self.node.control_backend == "smolvla":
            self.node.dispatch_smolvla_instruction("")
        else:
            self.node.dispatch_plan({"steps": [{"action": "stop", "lane": "default", "zone": None}]})
        if self.goal_request_pub is not None:
            from std_msgs.msg import String
            self.goal_asking = False
            self.goal_request_pub.publish(String(data="stop"))
        self.command_status.setText("정지 명령 전송 · 대기 중 명령 취소")
        if not self.closing:
            self.add_chat("assistant", "정지 명령을 전송했습니다.")

    def change_scenario(self, _value=None):
        if self.resetting:
            return
        key = self.race_selector.currentData()
        self.stop_driving()
        self.resetting = True
        self.node.avoid_enable = False
        for widget in (self.race_selector, self.reset_button, self.send_button, self.entry, self.voice_button):
            widget.setEnabled(False)
        self.race_status.setText("경기를 재설정하고 있습니다…")
        self.telemetry.clear_motion()
        self.bev.trail.clear()
        self.bev.prediction = []
        self.bev.obstacles = []
        self.camera.path_pixels = []
        # The old DiffDrive command must be zero before the new car subscribes.
        from geometry_msgs.msg import Twist
        from std_msgs.msg import String
        if not getattr(self, "reset_publishers", None):
            self.reset_publishers = (
                self.node.create_publisher(String, "/vla/hold", 5),
                self.node.create_publisher(String, "/vla/speed_floor", 5),
                self.node.create_publisher(Twist, "/cmd_vel", 5))
        hold, floor, cmd = self.reset_publishers
        hold.publish(String(data="1"))
        floor.publish(String(data="0"))
        cmd.publish(Twist())
        def worker():
            try:
                # Let subscribers consume STOP before removing the vehicle.
                time.sleep(.3)
                reset_scenario(key, self.registry_path, self.bus.service.emit)
                error = ""
            except Exception as exc:
                error = str(exc)
            if not self.closing:
                self.bus.scenario_done.emit(key, error)
        threading.Thread(target=worker, daemon=True).start()

    def on_scenario_done(self, key, error):
        from std_msgs.msg import String
        self.resetting = False
        self.reset_publishers[0].publish(String(data="0"))
        publishers = self.reset_publishers
        self.reset_publishers = None
        QTimer.singleShot(1000, lambda: [self.node.destroy_publisher(pub) for pub in publishers])
        self.sim_paused = False
        self.telemetry.clear_motion()
        self.bev.trail.clear()
        for widget in (self.race_selector, self.reset_button, self.send_button, self.entry, self.voice_button):
            widget.setEnabled(True)
        if error:
            self.race_status.setText("경기 재설정 실패 · 차량은 정지 상태")
            self.add_chat("error", error)
        else:
            self.apply_scenario(key)
            if self.lecture_mode:
                self.goto_clear(quiet=True)
            self.add_chat("assistant", self.scenarios[key]["label"] + " 배치를 마쳤습니다. 출발 명령을 기다립니다.")
            self.camera_action("top")
        if self.close_after_reset:
            QTimer.singleShot(0, self.close)

    def apply_scenario(self, key):
        scenario = self.scenarios[key]
        self.race_selector.setCurrentIndex(self.race_selector.findData(key))
        self.race_status.setText(scenario["description"])
        self.node.current_lane = self.node._vla_lane = scenario["lane"]
        # lecture: keep the avoid_enable the launcher asked for (--avoidance on|off)
        self.node.avoid_enable = key == "mission1" or (key == "lecture" and self.avoid_default)
        self.node._avoid_home_lane = None
        if getattr(self.node, "_avoid_stopped", False):
            self.node._set_avoid_stopped(False)
        self.node._avoid_clear_since = None
        self.node._avoid_obstacles_mtime = None
        self.bev.trail.clear()

    # ------------------------------------------------ lecture obstacle editor
    def on_obstacle_selected(self, entity):
        self.remove_button.setEnabled(bool(entity))
        self.remove_button.setText(f"제거 · {entity}" if entity else "선택 제거")

    def remove_selected_obstacle(self):
        entity, self.bev.selected = self.bev.selected, None
        self.on_obstacle_selected("")
        if entity:
            self.obstacle_remove(entity)
            self.bev.update()

    def _registry(self):
        try:
            return [o for o in json.loads(self.registry_path.read_text()) if isinstance(o, dict)]
        except (OSError, ValueError):
            return []

    def _snap_lane(self, x, y):
        """Nearest lane point within 2.5 m -> (x, y, travel_yaw, lane); else free."""
        best = (x, y, 0.0, "parking", 2.5)
        for lane, pts in (self.node._track_lanes or {}).items():
            for i, (px, py) in enumerate(pts):
                d = math.hypot(px - x, py - y)
                if d < best[4]:
                    nx, ny = pts[(i + 1) % len(pts)]
                    best = (px, py, math.atan2(ny - py, nx - px), lane, d)
        return best[:4]

    def _obstacle_job(self, job, done=None):
        """Run one gz + registry edit off the GUI thread. Jobs are serialised
        under one lock and each re-reads the registry inside the lock: three
        quick right-click adds otherwise all picked "obstacle1" and the last
        writer dropped the other two (offscreen test, 2026-09-22)."""
        if not hasattr(self, "_obstacle_lock"):
            self._obstacle_lock = threading.Lock()
        def worker():
            try:
                with self._obstacle_lock:
                    text = job()
            except Exception as exc:                            # noqa: BLE001
                text = f"장애물 작업 실패: {exc}"
            if not self.closing:
                self.bus.service.emit(text)
                if done:
                    done()
        threading.Thread(target=worker, daemon=True).start()

    def obstacle_add(self, model, x, y):
        sx, sy, travel, lane = self._snap_lane(x, y)
        yaw = obstacle_body_yaw(model, travel)
        def job():
            entries = self._registry()
            used = {o.get("entity") for o in entries}
            n = 1
            while f"obstacle{n}" in used:
                n += 1
            name = f"obstacle{n}"       # matches reset_scenario's cleanup pattern
            cache = self.registry_path.parent / "scene_models"
            cache.mkdir(parents=True, exist_ok=True)
            filename = cache / f"{name}.sdf"
            ET.ElementTree(static_model(model, name)).write(filename, encoding="unicode")
            pose = (sx, sy, OBSTACLE_Z, 0.0, 0.0, yaw)
            request("/world/default/create", "gz.msgs.EntityFactory",
                    f"sdf_filename: {json.dumps(str(filename))} name: {json.dumps(name)} "
                    f"allow_renaming: false pose: {{{pose_message(pose)}}}")
            entries.append({"entity": name, "model": model, "kind": "vehicle",
                            "x": sx, "y": sy, "yaw": yaw, "lane": lane})
            atomic_json(self.registry_path, entries)
            return f"장애물 추가: {name} {model} ({lane})"
        self._obstacle_job(job)

    def obstacle_move(self, entity, x, y):
        sx, sy, travel, lane = self._snap_lane(x, y)
        def job():
            entries = self._registry()
            entry = next((o for o in entries if o.get("entity") == entity), None)
            if entry is None:
                return f"장애물 이동 실패: {entity} 없음"
            yaw = (obstacle_body_yaw(entry.get("model", ""), travel)
                   if lane != "parking" else entry.get("yaw", 0.0))
            pose = (sx, sy, OBSTACLE_Z, 0.0, 0.0, yaw)
            request("/world/default/set_pose", "gz.msgs.Pose",
                    f"name: {json.dumps(entity)} " + pose_message(pose))
            entry.update({"x": sx, "y": sy, "yaw": yaw, "lane": lane})
            atomic_json(self.registry_path, entries)
            return f"장애물 이동: {entity} ({lane})"
        self._obstacle_job(job)

    def obstacle_remove(self, entity):
        def job():
            entries = [o for o in self._registry() if o.get("entity") != entity]
            request("/world/default/remove", "gz.msgs.Entity",
                    f"name: {json.dumps(entity)} type: MODEL")
            atomic_json(self.registry_path, entries)
            return f"장애물 제거: {entity}"
        self._obstacle_job(job)

    # ------------------------------------------------ go-to-object practice
    SECTOR_KO = {"left": "왼쪽", "ahead": "정면", "right": "오른쪽"}

    def goto_nouns(self):
        out = []
        for o in self.goto_objects:
            out += [o["noun"], G.NOUN_KO.get(o["noun"], o["noun"])]
        return out

    def goto_spawn(self):
        """Three props ahead of the car, one per sector, as in the s1 corpus."""
        pose = self.bev.pose
        if pose is None or self.resetting:
            self.add_chat("error", "차량 위치를 받은 뒤에 물체를 놓을 수 있습니다.")
            return
        self.stop_driving()
        x, y, yaw = pose
        heading = yaw + G.YAW_OFFSET              # gz model yaw -> travel heading
        rng = random.Random()
        chosen, nouns = [], set()
        if self.goto_heldout.isChecked():
            # held-out props may be larger (dinosaurs 2.4 m, r 1.2); cars (r 2.2) never fit
            # go_dino_trex (really a styracosaurus toy) read as "goat"/"bird" to Qwen2.5-VL from
            # every side (probe 2026-10-13), so a "dinosaur" request could never find it
            m = rng.choice([m for m, v in G.FLEET.items() if v[2] == "heldout" and v[1] <= 1.2
                            and m != "go_dino_trex"])
            chosen.append(m)
            nouns.add(G.noun(m))
        # trained props keep the s1 corpus rule (r <= 0.9, no cars)
        train = [m for m, v in G.FLEET.items() if v[2] == "train" and v[1] <= G.SECTOR_MAX_R]
        for m in rng.sample(train, len(train)):
            if len(chosen) == 3:
                break
            if G.noun(m) not in nouns:
                chosen.append(m)
                nouns.add(G.noun(m))
        layout = G.sector_layout_at(rng, x, y, heading, chosen)
        if layout is None:
            self.add_chat("error", "차량 앞에 세 물체를 놓을 자리가 없습니다(트랙 바닥 끝에 가깝거나 바깥을 보고 있음). "
                                   "수동주행으로 트랙 안쪽을 보게 옮긴 뒤 다시 눌러 주세요.")
            return
        objs = layout["objects"]
        for o in objs:
            if o["model"].startswith("go_dino"):
                # side-on to the car: seen from the front/back Qwen called the T-rex a wolf and the
                # triceratops a dog/donkey; side views read "dinosaur" (yaw probe 2026-10-13)
                o["yaw"] = math.atan2(o["y"] - y, o["x"] - x) + rng.choice((math.pi / 2, -math.pi / 2))
        self.goto_objects = objs
        self.goto_origin = (x, y, yaw)
        previous = {f"goto_{m}" for m in G.FLEET}
        def job():
            gz = resolve_gz_bin()
            present = set(list_models(gz))
            cache = self.registry_path.parent / "scene_models"
            cache.mkdir(parents=True, exist_ok=True)
            used = set()
            for o in objs:
                name = f"goto_{o['model']}"
                used.add(name)
                if name in present:        # teleport: repeated gz create wedges the world
                    set_model_pose(gz, name, o["x"], o["y"], o["yaw"], z=OBSTACLE_Z)
                    continue
                filename = cache / f"{name}.sdf"
                ET.ElementTree(static_model(o["model"], name)).write(filename, encoding="unicode")
                request("/world/default/create", "gz.msgs.EntityFactory",
                        f"sdf_filename: {json.dumps(str(filename))} name: {json.dumps(name)} "
                        f"allow_renaming: false pose: {{{pose_message((o['x'], o['y'], OBSTACLE_Z, 0.0, 0.0, o['yaw']))}}}")
            for i, name in enumerate(sorted((previous & present) - used)):
                set_model_pose(gz, name, 60.0 + 6 * i, 70.0, 0.0, z=-30.0)
            entries = [e for e in self._registry() if e.get("kind") != "goto"]
            entries += [{"entity": f"goto_{o['model']}", "model": o["model"], "kind": "goto",
                         "x": o["x"], "y": o["y"], "yaw": o["yaw"], "lane": None,
                         "sector": o["sector"], "noun": o["noun"]} for o in objs]
            atomic_json(self.registry_path, entries)
            return "물체 배치 완료: " + ", ".join(f"{self.SECTOR_KO[o['sector']]} {o['model']}" for o in objs)
        self._obstacle_job(job)
        by = {o["sector"]: o for o in objs}
        lines = [f"{self.SECTOR_KO[k]}: {G.NOUN_KO.get(by[k]['noun'], by[k]['noun'])} ({by[k]['dist']:.1f} m)"
                 + (" · 미학습" if G.FLEET[by[k]["model"]][2] == "heldout" else "")
                 for k in ("left", "ahead", "right")]
        example = G.NOUN_KO.get(by["right"]["noun"], by["right"]["noun"])
        self.add_chat("assistant", "차량 앞에 물체 3개를 놓았습니다.\n" + "\n".join(lines)
                      + f"\n예: '왼쪽 물체로 가줘', '{example}{G._ro(example)} 가줘'")

    def goto_clear(self, quiet=False):
        """Park every go-to prop under the plane and drop them from the registry."""
        self.goto_objects = []
        self.goto_origin = None
        self.goto_run = None
        def job():
            gz = resolve_gz_bin()
            names = sorted(n for n in list_models(gz) if n.startswith("goto_"))
            for i, name in enumerate(names):
                set_model_pose(gz, name, 60.0 + 6 * i, 70.0, 0.0, z=-30.0)
            entries = self._registry()
            if any(e.get("kind") == "goto" for e in entries):
                atomic_json(self.registry_path, [e for e in entries if e.get("kind") != "goto"])
            return "" if quiet else f"물체 치움: {len(names)}개"
        self._obstacle_job(job)

    @staticmethod
    def is_goal_answer(text):
        t = text.strip()      # yes words: same list as goal_from_scene_node.YES
        yes = re.match(r"^(응+|어+|네|넹|예|맞아|맞아요|맞음|맞습니다|그래|그래요|그거|그거야|ㅇㅇ+|좋아|가자|가줘|고고|ok|okay|yes|y)"
                       r"(?=$|[\s.!~,요])", t, re.I)
        return bool(yes or re.match(r"^(\d+|아니|아냐|ㄴㄴ|노|no\b|n$|싫|다른|틀려|그거 아니)", t, re.I) or len(t) <= 3)

    def send_point_goal(self, text, quiet=False):
        from std_msgs.msg import String
        self._goal_sub_ready()
        if quiet:
            self.goal_request_pub.publish(String(data=text))
            return
        self.sv_last_request = text
        self.goto_run = None
        self.node.avoid_enable = False             # the supervisor would hold in front of the target
        self.node.dispatch_smolvla_instruction("")  # clear queue; the goal node then sends "Target."
        self.goal_nomatch_shown = False
        self.goal_asking = False
        self.goal_request_pub.publish(String(data=text))
        if os.environ.get("NAVVLA_PERCEIVER", "qwen") == "smolvla":
            self.command_status.setText("SmolVLA 가 전방 화면에서 목표를 찾는 중…")
            pass       # the goal node answers at once (found / not a trained name / not visible)
        else:
            self.command_status.setText("VLM 이 전방 화면에서 목표를 찾는 중…")
            self.add_chat("assistant", "Qwen-VL 이 화면에서 목표를 찾고, 정책은 그 방향·거리로 갑니다.")

    def _sv_look_timeout(self, text):
        if getattr(self, "sv_pending", None) == text:
            self.sv_pending = None
            res, self.sv_result = getattr(self, "sv_result", None), None
            self._sv_chat(text, (f"방금 요청 처리 결과(이미 끝남): {res}\n" if res else "")
                          + "SmolVLA 목표 노드가 응답하지 않아 지금 화면을 확인하지 못함")

    def _sv_chat(self, user, facts):
        """SmolVLA-only mode conversation: natural Korean from the facts SmolVLA produced. The text
        model never sees the image, so it can only talk about what SmolVLA recognised."""
        hist = getattr(self, "sv_history", None)
        if hist is None:
            hist = self.sv_history = deque(maxlen=8)
        try:
            spd = float(self.metrics["speed"].text().split()[0])
            state = f"속도 {spd:.1f} m/s, " + ("정지해 있음" if spd < 0.1 else "움직이는 중")
        except (ValueError, IndexError, KeyError):
            state = "알 수 없음"
        sv_goal = getattr(self, "sv_last_request", None)
        if sv_goal:
            state += f", 마지막 이동 요청: '{sv_goal}'"
        known = "빨간·노란·흰·파란 꼬깔, 소화전, 의자, 쓰레기통, 강아지, 드럼통, 상자, 바리케이드, 말"
        system = ("당신은 시뮬레이션 자율주행차에 타고 있는 대화 도우미입니다. 사람과 이야기하듯 자연스러운 존댓말로 "
                  "1~3문장만 답하세요. 목록, 번호, 괄호, 마크다운, 이모지는 쓰지 마세요.\n"
                  "규칙:\n"
                  "1. 차가 무엇을 보는지는 [관찰]에 적힌 것만 말합니다. 물체의 움직임, 색, 날씨, 감정처럼 적히지 않은 내용은 덧붙이지 않습니다. "
                  "왼쪽·오른쪽·정면과 거리는 그대로 옮기고, '12 m 넘게'는 '꽤 멀리'라고 말해도 됩니다. 확신 값과 영어 이름은 말하지 않습니다.\n"
                  f"2. 이 차의 눈(SmolVLA)이 알아볼 수 있는 물체는 {known}뿐입니다. 사용자가 그 밖의 물체(모양, 동물, 사람 등)를 물으면 "
                  "'없다'고 단정하지 말고 '그건 제가 알아보지 못하는 물체라 있는지 확인할 수 없어요'처럼 말합니다.\n"
                  "3. 대화만으로 차가 움직이지 않습니다. 직접 무엇을 하겠다고 약속하지 않습니다. 차를 움직이는 방법은 알아볼 수 있는 물체 이름으로 "
                  "'쓰레기통으로 가줘'처럼 말하는 것과 '정지'뿐이니, 다른 방법을 제안하지 않습니다.\n"
                  "4. [관찰]에 요청 처리 결과가 있으면 그 일은 이미 끝났습니다. 왜 출발하지 않았는지 쉬운 말로 설명하고, 기다려 달라거나 다시 찾겠다고 하지 않습니다.\n"
                  "5. 알아볼 수 있는 물체 종류를 말할 때 그것들이 지금 주변에 있다고 말하지 않습니다. 주변에 있는 것은 [관찰]의 물체뿐입니다.\n"
                  "6. 차가 움직이는지 서 있는지는 [차 상태]만 따릅니다.\n"
                  "7. [관찰]은 매번 새로 본 것입니다. 이전 답에서 말한 물체라도 이번 [관찰]에 없으면 지금은 보이지 않는다고 말합니다. "
                  "물체끼리 어느 쪽이 더 가깝다는 비교는 [관찰]의 거리로만 합니다.\n"
                  "8. '거리 모름'으로 적힌 물체는 숫자 거리를 말하지 말고 '멀리'라고만 합니다.")
        msgs = [{"role": "system", "content": system}, *list(hist),
                {"role": "user", "content": f"[관찰]\n{facts}\n[차 상태]\n{state}\n[사용자]\n{user or '(요청 없음)'}"}]
        host = os.environ.get("NAVVLA_CHAT_HOST", "http://127.0.0.1:11501")
        model = os.environ.get("NAVVLA_CHAT_MODEL", "exaone3.5:7.8b")
        def worker():
            reply = None
            try:
                body = json.dumps({"model": model, "stream": False, "messages": msgs, "keep_alive": "30m",
                                   "options": {"temperature": 0.3, "num_predict": 200}}).encode("utf-8")
                req = urllib.request.Request(f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    reply = json.loads(r.read().decode("utf-8"))["message"]["content"].strip()
            except Exception:                                   # noqa: BLE001
                reply = None
            if reply:
                reply = self._drop_promises(reply)
            if not reply:
                reply = facts                                   # no LLM: the facts themselves, unvarnished
            hist.append({"role": "user", "content": user or "(요청 없음)"})
            hist.append({"role": "assistant", "content": reply})
            if not self.closing:
                self.bus.replied.emit(reply)
        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _drop_promises(reply):
        """Remove sentences in which the chat model says it will drive somewhere; it cannot."""
        sents = re.split(r"(?<=[.!?。])\s+", reply.strip())
        keep = [x for x in sents if not PROMISE_RE.search(x)]
        if len(keep) == len(sents):
            return reply
        keep = [x for x in keep if not re.fullmatch(r"(잠시만?\s*기다려\s*주세요|알겠습니다)[.!]?|잠시만?\s*기다려\s*주세요[.!]?", x.strip())]
        keep.append("대화로는 차가 움직이지 않아요. 움직이려면 '바리케이드로 가줘'처럼 물체 이름으로 말씀해 주세요.")
        return " ".join(keep)

    def _goal_sub_ready(self):
        from std_msgs.msg import String
        if self.goal_request_pub is None:
            self.goal_request_pub = self.node.create_publisher(String, "/goal_request", 5)
            self.goal_status_sub = self.node.create_subscription(
                String, "/goal_from_scene/status", lambda m: self.bus.goal_status.emit(m.data), 5)
            time.sleep(0.3)        # let the new publisher match the goal node once

    def on_goal_status(self, line):
        if self.closing:
            return
        if line.startswith("gate:"):
            self.command_status.setText("목표 도착 · 정지")
            self.add_chat("assistant", "목표 앞에 도착해 멈췄습니다.")
        elif line.startswith("ASK:"):
            self.goal_asking = True
            self.goal_nomatch_shown = True
            self.command_status.setText("확인 필요 · 응 / 아니 / 번호로 답해 주세요")
            self.add_chat("assistant", line[4:].strip())
        elif line.startswith("LOOK:"):
            user = getattr(self, "sv_pending", None)
            if user is not None:
                self.sv_pending = None
                res, self.sv_result = getattr(self, "sv_result", None), None
                facts = f"차 카메라로 SmolVLA 가 지금 알아본 물체: {line[5:].strip()}"
                if res:
                    facts = f"방금 요청 처리 결과(이미 끝남): {res}\n" + facts
                self._sv_chat(user, facts)
        elif line.startswith("SEEN:"):
            self.goal_asking = False
            self.goal_nomatch_shown = True
            self.command_status.setText("목표 미확정 · 정지")
            if SMOLVLA_ONLY:
                # word the refusal together with what SmolVLA sees now (without it the text model
                # invented nearby objects)
                user = getattr(self, "sv_last_request", "") or ""
                self.sv_result = line[5:].strip()
                self.sv_pending = user
                self.send_point_goal("look:", quiet=True)
                QTimer.singleShot(4000, lambda t=user: self._sv_look_timeout(t))
            else:
                self.add_chat("assistant", line[5:].strip())
        elif line.startswith("confirmed:"):
            self.goal_asking = False
            self.command_status.setText("확인한 물체로 이동 중")
            self.add_chat("assistant", "확인했습니다. 그 물체로 이동합니다.")
        elif line.startswith("VLM: no matching"):
            # the node keeps the last goal and re-asks every second; say it once per request
            self.command_status.setText("목표를 화면에서 찾지 못함")
            if not getattr(self, "goal_nomatch_shown", False):
                self.goal_nomatch_shown = True
                self.add_chat("error", "화면에서 말한 물체를 찾지 못했습니다. (이미 찾은 목표가 있으면 그 방향으로 계속 갑니다)")
        elif line.startswith("refresh failed"):
            self.add_chat("error", f"목표 계산 실패: {line[16:120]}")
        elif not line.startswith(("request:", "cleared")):
            self.command_status.setText(line[:90])

    def send_goto(self, text):
        sector = goto_command.sector_of(text)
        if sector:
            self.dispatch_goto(sector, "문장에 방향 단어가 있어 그대로 사용")
            return
        image = self.camera.frame
        if image.isNull():
            self.add_chat("error", "전방 카메라 영상이 없어 VLM 에게 보낼 수 없습니다.")
            return
        path = self.registry_path.with_name("goto_frame.jpg")
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(path), "JPG", 90)
        self.generation += 1
        generation = self.generation
        self.goto_run = None
        self.send_button.setEnabled(False)
        self.command_status.setText("VLM 이 전방 화면에서 대상을 찾는 중…")
        host = getattr(self.node, "scene_host", None) or getattr(self.node, "host", "http://127.0.0.1:11501")
        model = getattr(self.node, "scene_model", None) or "qwen2.5vl:7b"
        jpeg = path.read_bytes()
        def worker():
            sector, note, sec = goto_command.vlm_sector(host, model, jpeg, text)
            if not self.closing:
                self.bus.goto_ready.emit(generation, text, sector or "", f"{note} · {sec:.1f}초")
        threading.Thread(target=worker, daemon=True).start()

    def on_goto_ready(self, generation, text, sector, note):
        if self.closing or generation != self.generation:
            return
        self.send_button.setEnabled(not self.resetting)
        if not sector:
            self.command_status.setText("대상 판단 실패")
            self.add_chat("error", note)
            return
        self.dispatch_goto(sector, note)

    def dispatch_goto(self, sector, why):
        target = next((o for o in self.goto_objects if o["sector"] == sector), None)
        moved_note = ""
        pose, origin = self.bev.pose, self.goto_origin
        if target is not None and pose is not None and origin is not None:
            shift = math.dist(pose[:2], origin[:2])
            turn = abs(math.degrees(math.remainder(pose[2] - origin[2], math.tau)))
            if shift > 1.0 or turn > 15.0:
                # The layout's sectors were fixed at placement; pick the prop that is
                # in that screen direction from where the car is now.
                heading = pose[2] + G.YAW_OFFSET
                def bearing(o):
                    return math.degrees(math.remainder(
                        math.atan2(o["y"] - pose[1], o["x"] - pose[0]) - heading, math.tau))
                target = min(self.goto_objects,
                             key=lambda o: abs(bearing(o) - G.SECTOR_CENTRES[sector]))
                # Real-track sessions never start from a fixed pose, so this is not a
                # warning in the chat — only an event-log line for whoever reviews the run.
                moved_note = f"물체 배치 후 차 이동 {shift:.1f} m · {turn:.0f}° — 현재 위치 기준으로 대상 선택"
        if self.node.control_backend != "smolvla" or target is None:
            self.add_chat("error", "물체로 가기는 SmolVLA 제어에서 물체를 놓은 뒤에만 쓸 수 있습니다.")
            return
        sentence = goto_command.sector_sentence(sector)
        from std_msgs.msg import String
        self.node.avoid_enable = False             # the supervisor would hold in front of the props
        self.node.dispatch_smolvla_instruction("")  # clear queue and counters first
        self.node.vla_instruction_pub.publish(String(data=sentence))
        self.node._vla_mode = "goto"
        self.goto_run = {"target": target, "start": None, "moved": False, "anchor": None,
                         "still": None, "t0": time.monotonic()}
        name = G.NOUN_KO.get(target["noun"], target["noun"])
        self.add_chat("assistant", f"{self.SECTOR_KO[sector]} 물체({name})로 갑니다.\n"
                                   f"정책에 보낸 문장: \"{sentence}\"\n({why})")
        if moved_note:
            self.record_event(moved_note)
        self.command_status.setText(f"물체로 이동 중 · {sentence}")

    def goto_watch(self, pose, now):
        """Same end rule as tools/eval/goto_trial.py: moved, then 3 s still; or a
        touch of another prop; or 60 s. Success = nearest prop is the target and
        the bumper gap is 0.6-1.8 m."""
        run = self.goto_run
        x, y = pose[:2]
        if run["start"] is None:
            run["start"] = (x, y)
        if math.dist((x, y), run["start"]) > 0.8:
            run["moved"] = True
        if run["anchor"] is None or math.dist((x, y), run["anchor"]) > 0.05:
            run["anchor"], run["still"] = (x, y), None
        else:
            run["still"] = run["still"] or now
        target = run["target"]
        touched = next((o for o in self.goto_objects if o is not target
                        and math.dist((x, y), (o["x"], o["y"])) < o["r"] + 1.3), None)
        timeout = now - run["t0"] > 60
        if not (touched or timeout or (run["moved"] and run["still"] and now - run["still"] > 3)):
            return
        self.goto_run = None
        self.node.dispatch_smolvla_instruction("")
        dist = {id(o): math.dist((x, y), (o["x"], o["y"])) for o in self.goto_objects}
        nearest = min(self.goto_objects, key=lambda o: dist[id(o)])
        # 실제 여유 = 충돌 앞면(1.904 m) 기준. EGO_HALF_LEN(2.3, 교사 상수)으로
        # 재면 0.396 m 과소로 나와 정상 정차가 과주로 보인다 (2026-10-12 실측).
        gap = dist[id(target)] - G.EGO_COLLIDE_LEN - target["r"]
        ko = lambda o: f"{self.SECTOR_KO[o['sector']]} {G.NOUN_KO.get(o['noun'], o['noun'])}"
        if touched:
            verdict = f"실패 · 다른 물체({ko(touched)})에 닿음"
        elif timeout:
            verdict = "실패 · 60초 안에 멈추지 않음"
        elif nearest is target and 0.6 <= gap <= 1.8:
            verdict = "성공"
        else:
            verdict = "실패"
        self.add_chat("assistant", f"도착 판정: {verdict}\n가장 가까운 물체 {ko(nearest)} · 목표 {ko(target)}"
                                   f" · 목표까지 범퍼 간격 {gap:.1f} m (성공 기준 0.6~1.8 m)")
        self.command_status.setText(f"물체로 가기 끝 · {verdict}")

    # ------------------------------------------------ manual driving (front camera + WASD)
    MANUAL_VMAX, MANUAL_VREV, MANUAL_K = 3.0, 1.0, 0.25    # m/s, m/s, 1/m (car-like: w = k v)

    def eventFilter(self, obj, event):
        # Any click outside the front camera ends manual driving.
        if (event.type() == QEvent.MouseButtonPress and self.camera.hasFocus()
                and isinstance(obj, QWidget) and obj is not self.camera):
            self.camera.clearFocus()
        return False

    def set_manual_drive(self, on):
        from geometry_msgs.msg import Twist
        if on:
            if self.resetting or self.node.control_backend != "smolvla":
                self.camera.clearFocus()
                return
            self.generation += 1
            self.goto_run = None
            self.node.dispatch_smolvla_instruction("")     # the bridge goes silent on an empty task
            if self.manual_pub is None:
                self.manual_pub = self.node.create_publisher(Twist, "/cmd_vel", 5)
            self.manual_v = 0.0
            self.node._vla_mode = "manual"
            self.manual_timer.start(50)
            self.command_status.setText("수동주행 중 · 다른 곳을 클릭하면 해제")
        elif self.manual_timer.isActive():
            self.manual_timer.stop()
            self.manual_v = 0.0
            if self.manual_pub is not None:
                self.manual_pub.publish(Twist())
            if getattr(self.node, "_vla_mode", "") == "manual":
                self.node._vla_mode = "idle"
            self.command_status.setText("수동주행 해제 · 정지")

    def manual_tick(self):
        from geometry_msgs.msg import Twist
        dt = 0.05
        held = set(self.camera.held)
        v = self.manual_v
        toward_zero = lambda rate: max(0.0, v - rate * dt) if v > 0 else min(0.0, v + rate * dt)
        if Qt.Key_Space in held:
            v = toward_zero(6.0)
        elif Qt.Key_W in held and Qt.Key_S not in held:
            v = min(self.MANUAL_VMAX, v + (2.0 if v >= 0 else 5.0) * dt)
        elif Qt.Key_S in held and Qt.Key_W not in held:
            v = v - 4.0 * dt if v > 0 else max(-self.MANUAL_VREV, v - 1.0 * dt)
        else:
            v = toward_zero(1.5)
        self.manual_v = v
        steer = (Qt.Key_A in held) - (Qt.Key_D in held)
        t = Twist()
        t.linear.x = v
        t.angular.z = max(-1.0, min(1.0, steer * self.MANUAL_K * v))
        self.manual_pub.publish(t)
        side = {1: "왼쪽", -1: "오른쪽", 0: "직진"}[steer]
        self.camera.drive_text = (f"수동주행 {v:+.1f} m/s · {side} · W/S 가감속 · A/D 조향 · Space 정지"
                                  " · Esc/다른 곳 클릭 = 해제")

    def refresh_scene(self):
        for path, attr in ((self.registry_path, "registry_mtime"),
                           (self.registry_path.with_name("scene.json"), "scene_mtime")):
            try:
                modified = path.stat().st_mtime_ns
                if modified == getattr(self, attr):
                    continue
                data = json.loads(path.read_text())
                if attr == "registry_mtime":
                    if self.bev.drag_ob is not None:
                        continue        # do not yank the obstacle out of the hand
                    self.bev.obstacles = [o for o in data if "x" in o and "y" in o]
                elif data.get("scenario") in self.scenarios:
                    self.apply_scenario(data["scenario"])
                setattr(self, attr, modified)
            except (OSError, ValueError, TypeError):
                pass

    def fit_top_view(self):
        if not self.closing and self.camera_mode == "top" and self.gazebo.native_id:
            self.camera_action("top")

    def camera_action(self, action):
        if action in {"top", "overview"} or action in FOLLOW_OFFSETS:
            self.camera_mode = action
        pose = self.bev.pose
        if action in FOLLOW_OFFSETS and pose is None:
            self.footer.setText("차량 위치가 수신된 후 차량 시점을 사용할 수 있습니다.")
            return
        # The embedded Gazebo window reserves 50 logical pixels for its toolbar.
        aspect = self.gazebo.width()/max(1, self.gazebo.height()-50)
        def worker():
            try:
                if action in {"pause", "play"}:
                    request("/world/default/control", "gz.msgs.WorldControl",
                            "pause: " + ("true" if action == "pause" else "false"))
                else:
                    request("/gui/follow", "gz.msgs.StringMsg", 'data: ""')
                    if action in FOLLOW_OFFSETS:
                        x,y,yaw = pose
                        heading = yaw-math.pi/2
                        side, back, height = FOLLOW_OFFSETS[action]
                        # Vehicle-local +X is the driver's left (yaw direction in world).
                        cx = x-back*math.cos(heading)+side*math.cos(yaw)
                        cy = y-back*math.sin(heading)+side*math.sin(yaw)
                        target = [cx, cy, height, 0., math.atan2(height-1., math.hypot(back, side)),
                                  math.atan2(y-cy, x-cx)]
                    elif action == "top":
                        target = top_camera_pose(aspect)
                    else:
                        target = [-38., -46., 50., 0., .70, .88]
                    move_camera(target)
                    if action in FOLLOW_OFFSETS:
                        # Gazebo follow offsets are in the target's local frame;
                        # the Prius rear is +Y, its forward direction is -Y and its left is +X.
                        time.sleep(.6)
                        request("/gui/follow", "gz.msgs.StringMsg", 'data: "ego_vehicle"')
                        request("/gui/follow/offset", "gz.msgs.Vector3d",
                                "x: %g y: %g z: %g" % FOLLOW_OFFSETS[action])
                message = {"pause":"시뮬레이션 일시정지", "play":"시뮬레이션 재개",
                           "top":"전체 탑뷰", "overview":"대각선 시점", "ego":"차량 추적 시점",
                           "ego_left":"왼쪽 뒤 추적 시점", "ego_right":"오른쪽 뒤 추적 시점"}[action]
            except Exception as exc:
                message = f"시점/시뮬 제어 실패: {exc}"
            if not self.closing:
                self.bus.service.emit(message)
        threading.Thread(target=worker, daemon=True).start()

    def set_signal_color(self, color):
        if self.resetting:
            return
        key = self.race_selector.currentData()
        for button in self.signal_buttons.values():
            button.setEnabled(False)
        def worker():
            try:
                set_signal(key, self.registry_path, color)
                message = "신호등 변경: " + ("🔴 빨간불" if color == "red" else "🟢 초록불")
            except Exception as exc:
                message = f"신호등 변경 실패: {exc}"
            if not self.closing:
                self.bus.service.emit(message)
        threading.Thread(target=worker, daemon=True).start()

    def show_service_result(self, text):
        if not text:
            return
        if text.startswith("신호등 변경"):
            for button in self.signal_buttons.values():
                button.setEnabled(True)
        if not self.closing:
            self.footer.setText(text)
            self.record_event(text)
            if text in {"시뮬레이션 일시정지", "시뮬레이션 재개"}:
                self.sim_paused = text == "시뮬레이션 일시정지"
                self.paused_snapshot = self.telemetry.snapshot() if self.sim_paused else None
                self.pause_time = time.monotonic() if self.sim_paused else None

    def refresh(self):
        now = time.monotonic()
        if not self.resetting:
            self.refresh_scene()
        snapshot = self.paused_snapshot if self.sim_paused else self.telemetry.snapshot()
        data_time = self.pause_time if self.sim_paused else now
        pose = fresh(snapshot, "pose", now=data_time) if not self.resetting else None
        scene_ready = pose is not None and not self.resetting
        try:
            startup = json.loads(self.startup_path.read_text())
            if time.time()-startup.get("time", 0) < 300 and startup.get("stage") in {"starting", "scene"}:
                scene_ready = False
        except (OSError, ValueError):
            pass
        self.race_selector.setEnabled(scene_ready)
        self.reset_button.setEnabled(scene_ready)
        self.bev.pose = pose
        if pose is not None:
            xy = pose[:2]
            if self.bev.trail and math.dist(xy, self.bev.trail[-1]) > 5:
                self.bev.trail.clear()  # simulator reset / teleport
            if not self.bev.trail or math.dist(xy, self.bev.trail[-1]) > 0.05:
                self.bev.trail.append(xy)
        self.bev.lane = self.node.current_lane
        if self.goto_run and pose is not None and not self.sim_paused:
            self.goto_watch(pose, now)
        plan = fresh(snapshot, "plan", age=2.0, now=data_time)
        self.bev.prediction = plan if plan is not None and pose is not None else []
        plan_info = fresh(snapshot, "plan_info", age=2.0, now=data_time) or {}
        preview_note = f" · 미래 {plan_info['horizon_s']:.1f}초" if self.bev.prediction and plan_info else ""
        lap = fresh(snapshot, "lap", age=3.0)
        lap_note = ""
        if lap and (lap.get("target") or lap.get("lap")):
            lap_note = f"🏁 {int(lap['lap']) + 1}바퀴째 {int(lap.get('pct', 0) * 100)}%"
            if lap.get("target"):
                lap_note += f" / 목표 {int(lap['target'])}바퀴"
            lap_note += " · "
        self.bev_status.setText(f"{lap_note}● 궤적 {len(self.bev.trail)} · 예측 {max(0,len(self.bev.prediction)-1)}{preview_note} · 장애물 {len(self.bev.obstacles)}" if pose is not None
                                else "위치 신호 없음/지연 · 차량과 예측 경로 표시 중단")
        self.bev.update()
        odom = self.node.latest_pose
        odom_time = self.node.latest_pose_time
        self.metrics["speed"].setText(f"{abs(odom['speed']):.2f} m/s" if odom and odom_time and now-odom_time < 2 else "— m/s")
        self.metrics["lane"].setText("1차선 · 안쪽" if self.node.current_lane == "lane1" else "2차선 · 바깥쪽")
        mode = getattr(self.node, "_vla_mode", "idle")
        mode_text = {"idle": "대기 / 정지", "cruise": "순항", "zone": "목적지 주행", "direct": "직행",
                     "goto": "물체로 이동", "manual": "수동주행"}.get(mode, mode)
        if getattr(self.node, "_avoid_stopped", False):
            mode_text = "회피 중 · 전방 확인 대기"
        self.metrics["mode"].setText(mode_text)
        if self.node.control_backend != "smolvla":
            self.metrics["mode"].setText("내비게이터 제어")
        override = fresh(snapshot, "override", age=0.6, now=now)
        if override and override.get("override") in {"hold", "watchdog"}:
            self.metrics["mode"].setText("감독 정지" if override["override"] == "hold" else "입력 지연 정지")
        status = fresh(snapshot, "status", age=3.0, now=now)
        connected = status is not None
        if self.last_status_connected is not None and connected != self.last_status_connected:
            self.record_event("차량 제어 상태 수신 복구" if connected else "차량 제어 상태 수신 끊김 · 연결 확인 필요")
        if connected or self.last_status_connected is not None:
            self.last_status_connected = connected
        if self.resetting:
            self.connection.setText("↻  경기 재설정 중")
        elif self.sim_paused:
            self.connection.setText("Ⅱ  시뮬레이션 일시정지")
        elif status:
            self.connection.setText("●  VLA 연결됨" if status.get("chunks", 0) else "●  제어 연결 · 출발 대기")
        else:
            self.connection.setText("○  VLA 신호 대기")
            try:
                startup = json.loads(self.startup_path.read_text())
                self.connection.setText("●  실행 실패" if startup["stage"] == "failed" else "○  연결 준비 중")
                self.command_status.setText(startup["message"])
            except (OSError, ValueError, KeyError):
                pass
        self.metrics["latency"].setText(f"{status['latency_ms']:.0f} ms" if status and "latency_ms" in status else "— ms")
        image = fresh(snapshot, "image", now=data_time)
        if image is not None:
            stamp = snapshot["image"][0]
            if stamp != self.image_stamp:
                self.image_stamp = stamp
                self.camera.frame = image
            self.camera.path_pixels = project_ground_path(
                self.bev.prediction, pose, (image.width(), image.height()),
                *self.camera_calibration) if pose and self.camera_calibration else []
            self.camera.note = "● VLA 실시간 예측" + preview_note if self.camera.path_pixels else "전방 카메라 · 예측 경로 대기"
        else:
            self.camera.path_pixels = []
            self.camera.note = "카메라 신호 없음 / 지연"
        self.camera.update()
        top_image = fresh(snapshot, "top_image", now=data_time) if not self.resetting else None
        if top_image is not None:
            self.top_camera.frame = top_image
            self.top_camera.note = "차량 탑뷰 · 차량 중심"
        else:
            self.top_camera.frame = QImage()
            self.top_camera.note = "차량 탑뷰 · 신호 없음 / 지연"
        self.top_camera.update()
        reasoning = snapshot.get("reasoning")
        if reasoning:
            stamp, text = reasoning
            if stamp != self.reason_stamp:
                self.reason_stamp = stamp
                self.reason_log.append(f'<p style="color:#8c9db5">{time.strftime("%H:%M:%S")}</p>'
                                       f'<p>{html.escape(text).replace(chr(10), "<br>")}</p>')
                self.reasoning.setHtml("".join(self.reason_log))
                self.reasoning.verticalScrollBar().setValue(self.reasoning.verticalScrollBar().maximum())
            self.reason_status.setText(f"모델 reasoning · 마지막 수신 {now-stamp:.0f}초 전")
        # Bound each drain so a producer cannot starve painting or STOP.
        for _ in range(40):
            try:
                tag, message = self.node.event_q.get_nowait()
            except queue.Empty:
                break
            if tag == "assistant":
                self.add_chat("assistant", message)
            elif tag == "scene":
                self.scene_text.setPlainText(message)
            elif tag == "narration":
                self.footer.setText(message)
        for _ in range(30):
            try:
                message = self.node.status_q.get_nowait()
            except queue.Empty:
                break
            for description in self.status_summary.feed(message):
                self.record_event(description)
        self.display_language.speed_trend = fresh(snapshot, "speed_trend", age=2.0)
        self.display_language.apply(self)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.resetting:
            self.close_after_reset = True
            self.command_status.setText("경기 배치를 정리한 뒤 창을 닫습니다…")
            event.ignore()
            return
        self.closing = True
        self.timer.stop()
        self.stop_driving()
        self.voice.close()
        self.display_language.close()
        self.gazebo.stop()
        event.accept()


def attach_telemetry(node):
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.qos import QoSProfile, DurabilityPolicy, HistoryPolicy
    latched_qos = QoSProfile(depth=1, history=HistoryPolicy.KEEP_LAST,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
    from sensor_msgs.msg import Image
    from std_msgs.msg import String
    telemetry = Telemetry()
    def image_cb(msg, key="image"):
        formats = {"rgb8": QImage.Format_RGB888, "bgr8": QImage.Format_BGR888,
                   "rgba8": QImage.Format_RGBA8888, "mono8": QImage.Format_Grayscale8}
        fmt = formats.get(msg.encoding.lower())
        if fmt is None or msg.width == 0 or msg.height == 0:
            return
        if len(msg.data) < msg.step * msg.height:
            return
        image = QImage(bytes(msg.data), msg.width, msg.height, msg.step, fmt).copy()
        if key == "top_image":
            # The existing overhead camera spans ~11.7m horizontally.
            # Crop to ~8.8m: the vehicle and nearby lane boundaries remain
            # visible without altering any camera used for model input.
            width, height = round(image.width()*.75), round(image.height()*.75)
            image = image.copy((image.width()-width)//2, (image.height()-height)//2, width, height)
        telemetry.put(key, image)
    def status_cb(msg):
        try:
            data = json.loads(msg.data)
            if isinstance(data, dict) and "latency_ms" in data:
                telemetry.put("status", data)
            if isinstance(data, dict) and "override" in data:
                telemetry.put("override", data)
        except (ValueError, TypeError):
            pass
    def reason_cb(msg):
        try:
            data = json.loads(msg.data)
            text = data.get("text", "") if isinstance(data, dict) else str(data)
        except ValueError:
            text = msg.data
        if text:
            telemetry.put("reasoning", text)
    def lap_cb(msg):
        try:
            telemetry.put("lap", json.loads(msg.data))
        except (ValueError, TypeError):
            pass
    def plan_cb(msg, preview=False):
        try:
            data = json.loads(msg.data)
            if not data["actions"]:
                telemetry.clear_plan()
                return
            snapshot = telemetry.snapshot()
            previous = fresh(snapshot, "plan_info", age=1.5)
            if not preview and previous and previous.get("source") == "preview":
                return
            # A world anchor from BEFORE inference avoids shifting the whole
            # prediction forward by the distance travelled during inference.
            pose = data.get("origin") or fresh(snapshot, "pose")
            if pose is None:
                return
            # Prius travels along model -Y; VLA dx is vehicle-forward.
            heading_pose = (pose[0], pose[1], pose[2]+data.get("yaw_to_heading", -math.pi/2))
            points = integrate_actions(data["actions"], heading_pose)
            telemetry.put("plan", points)
            telemetry.put("plan_info", {"source":"preview" if preview else "control",
                "horizon_s": len(data["actions"])/float(data.get("rate_hz", 10)),
                "requested_at": data.get("requested_at")})
        except (ValueError, KeyError, TypeError, IndexError):
            pass
    # Measured commanded-speed trend for the narration: the model's own trend
    # word is poorly grounded, so we read the actual /cmd_vel slope and hand it
    # to the translator (see dashboard_language.reasoning_ko).
    from geometry_msgs.msg import Twist
    speed_hist = deque()          # (t_mono, |v|), trimmed to a 2 s window
    def cmd_vel_cb(msg):
        t = time.monotonic()
        speed_hist.append((t, abs(msg.linear.x)))
        while speed_hist and t - speed_hist[0][0] > 2.0:
            speed_hist.popleft()
        recent = [v for ts, v in speed_hist if t - ts <= 0.6]
        older = [v for ts, v in speed_hist if t - ts >= 1.4]
        if not recent or not older:
            return
        dv = sum(recent) / len(recent) - sum(older) / len(older)
        telemetry.put("speed_trend",
                      "up" if dv > 0.15 else "down" if dv < -0.15 else "hold")
    subscriptions = [
        node.create_subscription(Twist, "/cmd_vel", cmd_vel_cb, qos_profile_sensor_data),
        node.create_subscription(Image, node.alpamayo_image_topic, image_cb, qos_profile_sensor_data),
        node.create_subscription(Image, "/ego_top_camera/image_raw",
                                 lambda msg: image_cb(msg, "top_image"), qos_profile_sensor_data),
        node.create_subscription(String, "/vla/reasoning", reason_cb, 5),
        node.create_subscription(String, "/vla/lap", lap_cb, latched_qos),
        node.create_subscription(String, "/vla/plan", plan_cb, 5),
        node.create_subscription(String, "/vla/preview", lambda msg: plan_cb(msg, True), 5),
        node.create_subscription(String, node.vla_status_topic, status_cb, 5),
    ]
    # One dedicated stream works even while idle, before avoidance starts.
    pose_stream = WorldPoseStream(resolve_gz_bin(), "ego_vehicle").start()
    stop = threading.Event()
    def pose_worker():
        seq = -1
        while not stop.wait(0.05):
            if pose_stream.latest is not None and pose_stream.seq != seq:
                seq = pose_stream.seq
                telemetry.put("pose", pose_stream.latest)
    thread = threading.Thread(target=pose_worker, daemon=True)
    thread.start()
    def cleanup():
        stop.set()
        pose_stream.stop()
        thread.join(timeout=1)
        for sub in subscriptions:
            node.destroy_subscription(sub)
    return telemetry, cleanup


def run_dashboard(node):
    # cv2 imports in the old backend may have installed Qt5 paths globally.
    for key in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_QPA_FONTDIR"):
        if "cv2" in os.environ.get(key, ""):
            os.environ.pop(key)
    if os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    app = QApplication.instance() or QApplication([])
    telemetry, cleanup = attach_telemetry(node)
    window = DashboardWindow(node, telemetry)
    old_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    for sig in old_handlers:
        signal.signal(sig, lambda *_args: window.close())
    window.showMaximized()          # F11: 전체화면 전환
    if node.control_backend == "smolvla":
        node.start_scene_worker()
    try:
        app.exec()
    finally:
        cleanup()
        window.gazebo.stop()
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)

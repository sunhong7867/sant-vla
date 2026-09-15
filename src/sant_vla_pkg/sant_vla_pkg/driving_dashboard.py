"""Single-window driving console; ROS callbacks never touch Qt widgets."""

from collections import deque
import html
import json
import math
import os
from pathlib import Path
import queue
import signal
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
from sant_vla_pkg.gazebo_services import move_camera, request, top_camera_pose
from sant_vla_pkg.race_scenarios import load_scenarios, model_directory, reset_scenario, set_signal
from sant_vla_pkg.gazebo_panel import GazeboPanel
from sant_vla_pkg.gz_pose import WorldPoseStream, resolve_gz_bin


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


class BevView(QWidget):
    """World-frame map, actual trajectory and raw VLA chunk with shared scale."""

    def __init__(self, lanes, zones):
        super().__init__()
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

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag = event.position()

    def mouseMoveEvent(self, event):
        if self.drag is not None:
            self.pan += event.position() - self.drag
            self.drag = event.position()
            self.update()

    def mouseReleaseEvent(self, _event):
        self.drag = None

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
            c, s = math.cos(yaw), math.sin(yaw)
            corners = [pt(x+c*dx-s*dy, y+s*dx+c*dy)
                       for dx,dy in [(-.9,-2.2),(.9,-2.2),(.9,2.2),(-.9,2.2)]]
            p.setPen(QPen(QColor("#ffead0"), 1))
            p.setBrush(QColor("#ffb76b"))
            p.drawPolygon(QPolygonF(corners))
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


class ResultBus(QObject):
    parsed = Signal(int, str, object)
    failed = Signal(int, str)
    service = Signal(str)
    scenario_done = Signal(str, str)


# Follow-camera offsets in the vehicle frame: (left, back, height).
# The low, close diagonal views are for checking whether a wheel touches a lane line.
FOLLOW_OFFSETS = {"ego": (0., 8., 5.), "ego_left": (3.5, 6., 2.5), "ego_right": (-3.5, 6., 2.5)}


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
        self.bus.service.connect(self.show_service_result)
        self.bus.scenario_done.connect(self.on_scenario_done)
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
        self.camera = CameraView()
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
        names = {"user": "YOU", "assistant": "DRIVING ASSISTANT", "system": "STUDIO", "error": "알림"}
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
        # Do not forward failed/unsupported commands as unvalidated raw VLA text.
        if error or not plan or not any(s.get("action") != "none" for s in plan.get("steps", [])):
            self.on_failed(generation, error or "실행 가능한 주행 명령을 찾지 못했습니다.")
            return
        try:
            if self.node.control_backend == "smolvla":
                response = self.node.dispatch_smolvla_instruction(text, parsed_result=result)
            else:
                response = self.node.dispatch_plan(plan)
            self.add_chat("assistant", self.command_summary(plan, response))
            self.command_status.setText(f"명령 전송 완료 · 해석 {latency:.2f}초")
        except Exception as exc:
            self.on_failed(generation, str(exc))

    def command_summary(self, plan, response):
        # Keep the exact canonical instruction in the status log, and make
        # the conversation about what the driver asked the vehicle to do.
        if "nothing was sent" in response.lower() or "not a trained" in response.lower():
            return response
        lane = "안쪽 1차선" if self.node.current_lane == "lane1" else "바깥쪽 2차선"
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
            self.add_chat("assistant", self.scenarios[key]["label"] + " 배치를 마쳤습니다. 출발 명령을 기다립니다.")
            self.camera_action("top")
        if self.close_after_reset:
            QTimer.singleShot(0, self.close)

    def apply_scenario(self, key):
        scenario = self.scenarios[key]
        self.race_selector.setCurrentIndex(self.race_selector.findData(key))
        self.race_status.setText(scenario["description"])
        self.node.current_lane = self.node._vla_lane = scenario["lane"]
        self.node.avoid_enable = key == "mission1"
        self.node._avoid_home_lane = None
        if getattr(self.node, "_avoid_stopped", False):
            self.node._set_avoid_stopped(False)
        self.node._avoid_clear_since = None
        self.node._avoid_obstacles_mtime = None
        self.bev.trail.clear()

    def refresh_scene(self):
        for path, attr in ((self.registry_path, "registry_mtime"),
                           (self.registry_path.with_name("scene.json"), "scene_mtime")):
            try:
                modified = path.stat().st_mtime_ns
                if modified == getattr(self, attr):
                    continue
                data = json.loads(path.read_text())
                if attr == "registry_mtime":
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
        plan = fresh(snapshot, "plan", age=2.0, now=data_time)
        self.bev.prediction = plan if plan is not None and pose is not None else []
        plan_info = fresh(snapshot, "plan_info", age=2.0, now=data_time) or {}
        preview_note = f" · 미래 {plan_info['horizon_s']:.1f}초" if self.bev.prediction and plan_info else ""
        self.bev_status.setText(f"● 궤적 {len(self.bev.trail)} · 예측 {max(0,len(self.bev.prediction)-1)}{preview_note} · 장애물 {len(self.bev.obstacles)}" if pose is not None
                                else "위치 신호 없음/지연 · 차량과 예측 경로 표시 중단")
        self.bev.update()
        odom = self.node.latest_pose
        odom_time = self.node.latest_pose_time
        self.metrics["speed"].setText(f"{abs(odom['speed']):.2f} m/s" if odom and odom_time and now-odom_time < 2 else "— m/s")
        self.metrics["lane"].setText("1차선 · 안쪽" if self.node.current_lane == "lane1" else "2차선 · 바깥쪽")
        mode = getattr(self.node, "_vla_mode", "idle")
        mode_text = {"idle": "대기 / 정지", "cruise": "순항", "zone": "목적지 주행", "direct": "직행"}.get(mode, mode)
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
    subscriptions = [
        node.create_subscription(Image, node.alpamayo_image_topic, image_cb, qos_profile_sensor_data),
        node.create_subscription(Image, "/ego_top_camera/image_raw",
                                 lambda msg: image_cb(msg, "top_image"), qos_profile_sensor_data),
        node.create_subscription(String, "/vla/reasoning", reason_cb, 5),
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

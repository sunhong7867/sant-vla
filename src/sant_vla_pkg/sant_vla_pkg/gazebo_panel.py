"""Embed our own Gazebo GUI client using Qt's foreign-window support on X11."""

import os
from pathlib import Path
import signal
import subprocess
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from sant_vla_pkg.gz_pose import resolve_gz_bin


def owned_window(display, process_group):
    """Only select windows belonging to the client we spawned, never by title."""
    from Xlib import X, error
    pid_atom = display.intern_atom("_NET_WM_PID")
    type_atom = display.intern_atom("_NET_WM_WINDOW_TYPE")
    normal = display.intern_atom("_NET_WM_WINDOW_TYPE_NORMAL")
    clients = display.screen().root.get_full_property(
        display.intern_atom("_NET_CLIENT_LIST"), X.AnyPropertyType)
    # Gazebo's QML plugins also create native children with PID properties.
    # Only a window-manager client is eligible; embedding a plugin child
    # would leave the actual main window outside and render a blank panel.
    if clients is None:
        return None
    for wid in clients.value:
        window = display.create_resource_object("window", int(wid))
        try:
            pid = window.get_full_property(pid_atom, X.AnyPropertyType)
            kind = window.get_full_property(type_atom, X.AnyPropertyType)
            if pid and (kind is None or normal in kind.value):
                try:
                    belongs = os.getpgid(int(pid.value[0])) == process_group
                except ProcessLookupError:
                    belongs = False
                geom = window.get_geometry()
                if belongs and geom.width > 100 and geom.height > 100:
                    return window.id
        except error.XError:
            continue
    return None


class GazeboPanel(QWidget):
    ready = Signal()
    resized = Signal()
    def __init__(self, config_path, parent=None, launch=True):
        super().__init__(parent)
        self.config_path = str(config_path)
        self.process = None
        self.foreign = None
        self.container = None
        self.display = None
        self.log_file = None
        self.native_id = None
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.message = QLabel("Gazebo 연결을 준비하고 있습니다…")
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setWordWrap(True)
        self.layout.addWidget(self.message, 1)
        self.retry = QPushButton("3D 뷰 다시 연결")
        self.retry.clicked.connect(self.start)
        self.layout.addWidget(self.retry)
        self.retry.hide()
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        if launch:
            QTimer.singleShot(100, self.start)

    def start(self):
        self.stop()
        if QApplication.platformName() != "xcb":
            self.fail("3D 통합 뷰는 X11/XWayland가 필요합니다.\nQT_QPA_PLATFORM=xcb로 실행해 주세요.")
            return
        try:
            from Xlib.display import Display
            self.display = Display()
            # ROS and cv2 may export Qt5 plugin paths. Never pass PySide6's
            # Qt paths to Gazebo (Qt5), or the client aborts before rendering.
            env = os.environ.copy()
            for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QML2_IMPORT_PATH"):
                env.pop(key, None)
            env["QT_QPA_PLATFORM"] = "xcb"
            root = Path(__file__).resolve().parents[3]
            models = root / "src/simulation_pkg/models"
            if not models.is_dir():
                from ament_index_python.packages import get_package_share_directory
                models = Path(get_package_share_directory("simulation_pkg")) / "models"
            if models.is_dir():
                env["GZ_SIM_RESOURCE_PATH"] = str(models) + os.pathsep + env.get("GZ_SIM_RESOURCE_PATH", "")
            # Match the simulator's PRIME rendering selection.
            nvidia = "/usr/share/glvnd/egl_vendor.d/10_nvidia.json"
            if Path(nvidia).exists():
                env.update(__NV_PRIME_RENDER_OFFLOAD="1",
                           __GLX_VENDOR_LIBRARY_NAME="nvidia",
                           __EGL_VENDOR_LIBRARY_FILENAMES=nvidia)
            logs = Path(os.environ.get("NAVVLA_DASHBOARD_LOG_DIR", "/tmp/navvla-dashboard"))
            logs.mkdir(parents=True, exist_ok=True)
            self.log_path = logs / "gazebo-gui.log"
            self.log_file = self.log_path.open("a", encoding="utf-8")
            self.process = subprocess.Popen(
                [resolve_gz_bin(), "sim", "-g", "--gui-config", self.config_path,
                 "--render-engine-gui", "ogre", "--force-version", "8"],
                env=env, stdout=self.log_file, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self.started = time.monotonic()
            self.message.setText("Gazebo 3D 뷰 연결 중…\n시뮬레이터가 준비되면 화면이 표시됩니다.")
            self.message.show()
            self.retry.hide()
            self.timer.setInterval(100)
            self.timer.start()
        except Exception as exc:
            self.stop()
            self.fail(f"3D 뷰를 시작하지 못했습니다.\n{exc}")

    def poll(self):
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.stop()
            self.fail(f"Gazebo 뷰 연결이 종료되었습니다.\n로그: {self.log_path}")
            return
        if self.foreign is not None:
            self.sync_native()
            return
        try:
            wid = owned_window(self.display, self.process.pid)
            if wid:
                self.foreign = QWindow.fromWinId(wid)
                if self.foreign is None:
                    raise RuntimeError("Qt could not attach the Gazebo window")
                # Qt6's createWindowContainer alone does not reliably reparent
                # Gazebo's Qt5 QQuickWindow under Mutter. Own a native Qt
                # surface and explicitly reparent the X11 client into it.
                self.native_id = wid
                self.container = QWidget(self)
                self.container.setAttribute(Qt.WA_NativeWindow)
                self.container.setMinimumSize(180, 120)
                self.container.setFocusPolicy(Qt.StrongFocus)
                self.layout.insertWidget(0, self.container, 1)
                self.container.show()
                self.message.hide()
                self.layout.activate()
                self.sync_native()
                self.timer.setInterval(1000)
                self.ready.emit()
            elif time.monotonic() - self.started > 90:
                self.stop()
                self.fail(f"3D 뷰 연결 시간이 초과되었습니다.\n로그: {self.log_path}")
        except Exception as exc:
            self.stop()
            self.fail(f"3D 창 연결 실패: {exc}")

    def sync_native(self):
        if self.native_id is None or self.container is None:
            return
        try:
            self._sync_native_window()
        except Exception as exc:
            self.stop()
            self.fail(f"3D 창 연결이 끊겼습니다: {exc}")

    def _sync_native_window(self):
        child = self.display.create_resource_object("window", self.native_id)
        parent_id = int(self.container.winId())
        if child.query_tree().parent.id != parent_id:
            child.unmap()
            child.change_attributes(override_redirect=True)
            child.reparent(parent_id, 0, 0)
        child.configure(x=0, y=0, width=max(1, self.container.width()),
                        height=max(1, self.container.height()), border_width=0)
        child.map()
        self.display.sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Layout geometry settles after the parent resize event.
        QTimer.singleShot(0, self.sync_native)
        self.resized.emit()

    def fail(self, text):
        self.message.setText(text)
        self.message.show()
        self.retry.show()

    def stop(self):
        self.timer.stop()
        if self.process is not None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
            except ProcessLookupError:
                pass
            self.process = None
        if self.container is not None:
            self.layout.removeWidget(self.container)
            self.container.deleteLater()
            self.container = None
            self.foreign = None
            self.native_id = None
        if self.display is not None:
            self.display.close()
            self.display = None
        if self.log_file is not None:
            self.log_file.close()
            self.log_file = None

"""Dashboard geometry, command cancellation, and offscreen UI integration."""

import math
import os
from pathlib import Path
import queue
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from sant_vla_pkg.dashboard_data import Telemetry, fresh, integrate_actions, project_ground_path


def test_body_frame_prediction_rotates_each_increment():
    points = integrate_actions([(1, 0, math.pi/2), (1, 1, 0)], (10, 20, 0))
    assert points[0] == (10, 20)
    assert points[1] == (11, 20)
    assert points[2] == pytest.approx((10, 21))
    assert integrate_actions([(2, 0, 0)], (0, 0, math.pi/2))[-1] == pytest.approx((0, 2))
    with pytest.raises(ValueError):
        integrate_actions([(float("nan"), 0, 0)], (0, 0, 0))


def test_stale_data_is_not_presented_as_live():
    assert fresh({"pose": (10., (1, 2, 0))}, "pose", now=11.) == (1, 2, 0)
    assert fresh({"pose": (10., (1, 2, 0))}, "pose", now=13.) is None
    assert fresh({}, "pose") is None


def test_status_summary_suppresses_heartbeat_and_reports_changes():
    import json
    from sant_vla_pkg.dashboard_data import StatusSummary
    summary = StatusSummary()
    status = dict(task="", queue=0, chunks=0, watchdog_hits=0, latency_ms=0)
    assert "출발 명령 대기" in summary.feed(json.dumps(status))[0]
    for _ in range(100):
        assert summary.feed(json.dumps(status)) == []
    status.update(task="Start driving in the outer lane, slowly.", chunks=1, queue=30)
    assert "바깥쪽 2차선" in summary.feed(json.dumps(status))[0]
    status.update(chunks=2, queue=15, latency_ms=100)
    assert summary.feed(json.dumps(status)) == []
    status.update(watchdog_hits=1, latency_ms=650, queue=0)
    assert len(summary.feed(json.dumps(status))) == 2
    assert summary.feed(json.dumps(status)) == []
    status.update(watchdog_hits=2)
    assert summary.feed(json.dumps(status)) == []
    status.update(task="", latency_ms=100)
    changes = summary.feed(json.dumps(status))
    assert any("정지 지시" in change for change in changes)
    assert any("지연 해소" in change for change in changes)
    assert summary.feed("not json") == []


def test_large_window_balances_panels_and_enlarges_reading_text(window, tmp_path):
    ui, _, app = window
    ui.resize(2490, 1400)
    ui.show()
    app.processEvents()
    a,b = ui.main_splitter.sizes()
    assert abs(a-b) < 10
    assert ui.chat.document().defaultFont().pixelSize() == 20
    ui.add_chat("user", "바깥쪽 차선을 유지하면서 출발해 줘")
    ui.add_chat("assistant", "바깥쪽 2차선 주행을 시작합니다.")
    ui.telemetry.put("reasoning", "Keeping to the outer lane; turning left through the corner.")
    ui.node.status_q.put('{"task":"", "queue":0, "watchdog_hits":0}')
    ui.refresh()
    assert "queue" not in ui.events.toPlainText()
    assert "출발 명령 대기" in ui.events.toPlainText()
    assert ui.grab().save(str(tmp_path / "readable-dashboard.png"))
    ui.resize(1080,800)
    app.processEvents()
    assert ui.chat.document().defaultFont().pixelSize() == 16
    assert ui.entry.isVisible()


def test_language_switch_retranslates_history_without_changing_input(window):
    ui, sent, _ = window
    language = ui.display_language
    language.close()  # deterministic display tests do not contact a server
    original = "안쪽 차선으로 가 주세요."
    english = "Please move to the inner lane."
    reasoning = "Keeping to the outer lane."
    language.cache[("en", original)] = english
    language.cache[("ko", reasoning)] = "바깥쪽 차선을 유지합니다."
    ui.entry.setText(original)
    ui.add_chat("user", original)
    ui.telemetry.put("reasoning", reasoning)
    ui.refresh()
    assert "바깥쪽 차선을 유지합니다." in ui.reasoning.toPlainText()
    ui.language_selector.setCurrentIndex(1)
    ui.refresh()
    assert ui.metrics["mode"].text() == "Idle / Stopped"
    assert english in ui.chat.toPlainText()
    assert reasoning in ui.reasoning.toPlainText()
    assert ui.entry.text() == original
    assert sent == []
    ui.language_selector.setCurrentIndex(0)
    ui.refresh()
    assert original in ui.chat.toPlainText()
    assert "바깥쪽 차선을 유지합니다." in ui.reasoning.toPlainText()
    from PySide6.QtWidgets import QLabel
    assert [w.text() for w in ui.findChildren(QLabel) if w.objectName()=="section" and w.text().startswith("01")] == ["01  Simulation"]


def test_language_translation_escapes_markup_and_deduplicates_numeric_updates(window):
    ui, _, _ = window
    language = ui.display_language
    language.close()
    language.language = "en"
    assert language.text("모델 reasoning · 마지막 수신 12초 전") == "Model reasoning · Received 12 s ago"
    assert not language.pending
    assert language.text("남은 거리 12.3 미터") == "Translating…"
    assert language.text("남은 거리 12.4 미터") == "Translating…"
    assert len(language.pending) == 1
    language.cache[("en", "테스트 문장")] = '<script>alert("x")</script>'
    rendered = language.markup('<p align="right">테스트 문장</p>')
    assert '<script>' not in rendered
    assert '&lt;script&gt;' in rendered


def test_camera_projection_uses_vehicle_forward_and_rejects_points_behind():
    # The Prius camera looks toward model -Y. Ground ahead must land below
    # the horizon and straight ahead must stay at the image's horizontal center.
    camera = (0, 0, 2, 0, 0, -math.pi/2)
    points = project_ground_path([(0,-10),(0,10)], (0,0,0), (640,480), camera, math.pi/2)
    assert len(points) == 1
    assert points[0][0] == pytest.approx(320)
    assert 240 < points[0][1] < 480
    rotated = project_ground_path([(10,0)], (0,0,math.pi/2), (640,480), camera, math.pi/2)
    assert rotated == pytest.approx(points)


def test_world_pose_stream_accepts_omitted_zero_components(monkeypatch):
    import io
    from sant_vla_pkg import gz_pose
    stream = gz_pose.WorldPoseStream("gz", "ego_vehicle")
    output = 'pose {\n name: "ego_vehicle"\n position {\n y: 2\n }\n orientation {\n w: 1\n }\n}\n'
    monkeypatch.setattr(gz_pose.subprocess, "Popen", lambda *a, **kw: SimpleNamespace(stdout=io.StringIO(output)))
    monkeypatch.setattr(gz_pose.time, "sleep", lambda _: setattr(stream, "_run", False))
    stream._loop()
    assert stream.latest == (0., 2., 0.)
    assert stream.seq == 1


def test_gazebo_negative_ack_is_an_error(monkeypatch):
    from sant_vla_pkg import gazebo_services
    monkeypatch.setattr(gazebo_services.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout="data: false", stderr=""))
    with pytest.raises(RuntimeError, match="data: false"):
        gazebo_services.move_camera([0,0,60,0,math.pi/2,0])


def test_scene_assets_do_not_duplicate_ego_sensors_or_controllers():
    from sant_vla_pkg.race_scenarios import load_scenarios, static_model
    scenes = load_scenarios()
    assert [len(scenes[key]["entities"]) for key in ("qualifying","tournament","mission1","mission2")] == [0,1,4,4]
    obstacle = static_model("prius_hybrid", "obstacle1")
    assert not obstacle.findall(".//sensor")
    assert not obstacle.findall(".//plugin")
    assert obstacle.findtext("model/static") == "true"
    assert obstacle.findall(".//collision")


@pytest.fixture
def window():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    from sant_vla_pkg.driving_dashboard import DashboardWindow
    app = QApplication.instance() or QApplication([])
    sent = []
    node = SimpleNamespace(
        _track_lanes={"lane1": [(0, 0), (10, 0), (10, 10), (0, 10)]},
        zones={}, current_lane="lane1", control_backend="smolvla", _vla_mode="idle",
        _avoid_obstacles=[], latest_pose=None, latest_pose_time=None,
        event_q=queue.Queue(), status_q=queue.Queue(),
        dispatch_smolvla_instruction=lambda text, **kw: sent.append(text) or "전송 완료",
    )
    ui = DashboardWindow(node, Telemetry(), launch_gazebo=False)
    yield ui, sent, app
    ui.close()
    app.processEvents()


def test_stop_discards_pending_parser_result(window):
    ui, sent, _ = window
    ui.generation = 1
    ui.stop_driving()
    result = ({"steps": [{"action": "start"}]}, 0.1, None)
    ui.on_parsed(1, "출발", result)
    assert sent == [""]  # slow parser must not restart the stopped vehicle
    ui.on_parsed(2, "출발", result)
    assert sent == ["", "출발"]


def test_unsupported_command_is_not_forwarded_to_policy(window):
    ui, sent, _ = window
    ui.on_parsed(0, "do anything", ({"steps": [{"action": "none"}]}, 0., None))
    assert sent == []


def test_disconnected_start_and_cancelled_voice_are_not_sent(window):
    ui, sent, _ = window
    ui.require_connection = True
    ui.send("출발")
    assert sent == []
    assert "아직 준비되지" in ui.chat.toPlainText()
    generation = ui.voice.generation
    ui.stop_driving()
    ui.on_voice_text(generation, "출발")
    assert ui.entry.text() == ""
    assert sent == [""]


def test_live_panels_and_resize_render(window, tmp_path):
    ui, _, app = window
    from PySide6.QtGui import QImage, QColor
    ui.telemetry.put("pose", (2, 3, 0))
    ui.telemetry.put("plan", [(2, 3), (4, 3)])
    ui.telemetry.put("reasoning", "차선을 유지하며 주행합니다.")
    ui.telemetry.put("status", {"latency_ms": 125.})
    image = QImage(320, 240, QImage.Format_RGB888)
    image.fill(QColor("#20334c"))
    ui.telemetry.put("image", image)
    ui.refresh()
    assert ui.bev.pose == (2, 3, 0)
    assert len(ui.bev.prediction) == 2
    assert "차선을 유지" in ui.reasoning.toPlainText()
    assert ui.metrics["latency"].text() == "125 ms"
    ui.show()
    app.processEvents()
    assert ui.grab().save(str(tmp_path / "dashboard.png"))
    ui.resize(1080, 740)
    app.processEvents()
    assert ui.entry.isVisible()
    assert ui.gazebo.isVisible()
    assert ui.bev.geometry().bottom() < ui.bev_status.geometry().top()


def test_pausing_keeps_the_last_pose_visible_until_resume(window, monkeypatch):
    from sant_vla_pkg import driving_dashboard
    ui, _, _ = window
    ui.telemetry.put("pose", (2,3,0))
    ui.show_service_result("시뮬레이션 일시정지")
    later = ui.pause_time+10
    monkeypatch.setattr(driving_dashboard.time, "monotonic", lambda: later)
    ui.refresh()
    assert ui.bev.pose == (2,3,0)
    ui.show_service_result("시뮬레이션 재개")
    ui.refresh()
    assert ui.bev.pose is None  # a live pose must be received again


def test_simulation_has_priority_and_controls_are_on_the_right(window):
    ui, _, app = window
    ui.resize(1540, 960)
    ui.show()
    app.processEvents()
    from PySide6.QtCore import QPoint
    assert ui.gazebo.height() >= 500
    assert ui.gazebo.width() >= 900
    scene_right = ui.gazebo.mapTo(ui, QPoint(ui.gazebo.width(), 0)).x()
    assert all(widget.mapTo(ui, QPoint()).x() > scene_right
               for widget in [*ui.metrics.values(), ui.race_selector, ui.reset_button])


def test_fresh_preview_uses_observation_pose_and_stop_clears_it(monkeypatch):
    import json
    from sant_vla_pkg import driving_dashboard
    callbacks = {}
    stream = SimpleNamespace(latest=None, seq=0, stop=lambda: None)
    stream.start = lambda: stream
    monkeypatch.setattr(driving_dashboard, "WorldPoseStream", lambda *a: stream)
    def subscribe(_type, topic, callback, _qos):
        callbacks[topic] = callback
        return topic
    node = SimpleNamespace(create_subscription=subscribe, destroy_subscription=lambda _: None,
                           alpamayo_image_topic="/camera/image_raw", vla_status_topic="/vla/status")
    telemetry, cleanup = driving_dashboard.attach_telemetry(node)
    try:
        telemetry.put("pose", (100, 200, 0))  # car has moved since the request
        msg = SimpleNamespace(data=json.dumps({"actions":[[1,0,0]],
                    "origin":[0,0,0], "yaw_to_heading":0, "rate_hz":10}))
        callbacks["/vla/preview"](msg)
        assert telemetry.snapshot()["plan"][1] == [(0,0), (1,0)]
        msg.data = json.dumps({"actions":[[9,0,0]]})
        callbacks["/vla/plan"](msg)
        assert telemetry.snapshot()["plan"][1] == [(0,0), (1,0)]
        msg.data = '{"actions": []}'
        callbacks["/vla/preview"](msg)
        assert "plan" not in telemetry.snapshot()
    finally:
        cleanup()

"""Regressions for adjacent-lane false stops and the detour pause lifecycle."""
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from std_msgs.msg import String
from sant_vla_pkg.chat_gui_node import ChatGuiNode
from sant_vla_pkg.vla_bridge_node import VlaBridge


@pytest.fixture
def supervisor(monkeypatch):
    monkeypatch.setattr("sant_vla_pkg.chat_gui_node.time.monotonic", lambda: 100.)
    node = ChatGuiNode.__new__(ChatGuiNode)
    values = dict(
        avoid_enable=True, avoid_source="vision", avoid_trigger_px=48.,
        avoid_coord_trigger_m=17., avoid_stop_m=7., avoid_vlm_period=.6,
        avoid_commit_s=4., avoid_cooldown_s=6., avoid_min_hold_s=8., avoid_clear_s=4.,
        _avoid_lock=threading.RLock(), _avoid_block_reason="clear", _avoid_log_last=None,
        _avoid_home_lane="lane2", _avoid_stopped=False, _avoid_started_t=90.,
        _avoid_last_switch_t=90., _avoid_clear_since=None, _avoid_kicks=0,
        _vla_mode="cruise", _vla_lane="lane1", _vla_speed_raw=110,
        _vla_direct_zone=None, _vla_watch_lock=threading.Lock(), _vla_watch_preslow=False,
        current_lane="lane1", _ego_actual_lane="lane1", _ego_standstill_since=None,
        _obstacle_ahead_time=100., _obstacle_ahead_lane="lane2", _obstacle_ahead_s=2.,
        _obstacle_lanes_ahead={"lane2"}, _obstacle_lane_s={"lane2": 2.},
        _avoid_obstacles=[{"lane": "lane2"}],
        _vlm_blocked=False, _vlm_blocked_time=100., _vlm_distance="far",
        _lidar_obstacle=True, _lidar_obstacle_time=100., _lidar_obstacle_dist=1.97,
        latest_detections=[{"class": "lane1_car", "h": 151., "score": .85}],
        latest_detection_time=100., event_q=queue.Queue(),
        vla_instruction_topic="/vla/instruction", last_dispatch="original inner instruction",
        vla_instruction_pub=Mock(), avoid_hold_pub=Mock(),
        _update_obstacle_ahead=Mock(), _cancel_vla_zone_watch=Mock(),
        _signal_check=Mock(return_value=False), _signal_stopped=False,
        get_logger=lambda: Mock(),
    )
    for name, value in values.items():
        setattr(node, name, value)
    return node


def test_adjacent_car_mislabeled_by_yolo_does_not_stop_detour(supervisor):
    # Sept 10 capture: ego=lane1, registry=lane2 only, YOLO=lane1_car,
    # VLM=false/far, LiDAR=true (vision mode). This used to publish STOP.
    supervisor._avoid_check()
    assert not supervisor._path_blocked()
    assert not supervisor._avoid_stopped
    assert supervisor._avoid_home_lane == "lane2"
    supervisor.vla_instruction_pub.publish.assert_not_called()
    supervisor.avoid_hold_pub.publish.assert_not_called()


def test_same_lane_blocker_is_not_hidden_by_closer_adjacent_car(supervisor):
    supervisor._avoid_home_lane = None
    supervisor._obstacle_lane_s["lane1"] = 6.
    supervisor._obstacle_lanes_ahead.add("lane1")
    supervisor.latest_detections = []
    supervisor._avoid_check()
    assert supervisor._avoid_block_reason == "coordinates:lane1"
    assert supervisor._avoid_home_lane == "lane1"
    assert supervisor._vla_lane == "lane2"


def test_sensor_fallbacks_remain_active_when_coordinates_unavailable(supervisor):
    supervisor._obstacle_ahead_time = 90.
    assert supervisor._path_blocked()
    assert supervisor._avoid_block_reason == "yolo:lane1_car"
    supervisor.latest_detections = []
    supervisor._avoid_obstacles = []
    supervisor._vlm_blocked = True
    supervisor._vlm_distance = "near"
    assert supervisor._path_blocked()
    supervisor._vlm_blocked_time = 90.
    assert not supervisor._path_blocked()


def test_opt_in_lidar_stop_is_independent_of_camera_lane_labels(supervisor):
    supervisor.avoid_source = "any"
    assert supervisor._path_blocked()
    assert supervisor._avoid_block_reason == "lidar:front_sector"
    supervisor._lidar_obstacle_time = 90.
    assert not supervisor._path_blocked()


def test_dead_pose_stream_invalidates_all_cached_lane_data(supervisor):
    supervisor._load_avoid_obstacles = Mock()
    supervisor._ego_pose_stream = SimpleNamespace(latest=(1., 2., 0.), received_at=90.)
    ChatGuiNode._update_obstacle_ahead(supervisor)
    assert supervisor._obstacle_ahead_time is None
    assert supervisor._obstacle_lane_s == {}
    assert supervisor._obstacle_lanes_ahead == set()
    assert supervisor._ego_actual_lane is None


def block_both_lanes(node):
    node._obstacle_lane_s["lane1"] = 6.
    node._obstacle_lanes_ahead.add("lane1")
    node._avoid_check()
    assert node._avoid_stopped
    assert node._vla_mode in {"cruise", "zone"}
    node.avoid_hold_pub.publish.assert_called_once_with(String(data="1"))
    node.vla_instruction_pub.publish.assert_not_called()


def test_temporary_obstacle_stop_preserves_detour_and_resumes_when_clear(supervisor):
    block_both_lanes(supervisor)
    # Avoiding the original lane2 car remains valid after the new lane1
    # obstruction clears. Repeated misleading camera labels cannot wedge it.
    del supervisor._obstacle_lane_s["lane1"]
    supervisor._obstacle_lanes_ahead.remove("lane1")
    supervisor._avoid_check()
    assert not supervisor._avoid_stopped
    assert supervisor._avoid_home_lane == "lane2"
    assert supervisor._vla_lane == "lane1"
    supervisor.avoid_hold_pub.publish.assert_called_with(String(data="0"))
    assert "inner lane" in supervisor.vla_instruction_pub.publish.call_args[0][0].data


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mode", ["cruise", "zone"])
def test_explicit_stop_cancels_automatic_restart(supervisor, external, mode):
    supervisor._vla_mode = mode
    block_both_lanes(supervisor)
    if external:
        supervisor._external_instr_cb(String(data=""))
    else:
        supervisor.dispatch_smolvla_instruction("")
    supervisor._obstacle_lane_s = {}
    supervisor._avoid_check()
    assert supervisor._vla_mode == "idle"
    assert supervisor._avoid_home_lane is None
    assert not supervisor._avoid_stopped
    assert all(call.args[0].data == "" for call in supervisor.vla_instruction_pub.publish.call_args_list)


def test_far_second_blocker_does_not_stop_early(supervisor):
    supervisor._obstacle_lane_s["lane1"] = 10.
    supervisor._obstacle_lanes_ahead.add("lane1")
    supervisor._avoid_check()
    assert not supervisor._avoid_stopped


def test_bridge_hold_keeps_instruction_and_does_not_release_navigator_hold():
    bridge = VlaBridge.__new__(VlaBridge)
    bridge._hold, bridge._avoid_hold = False, False
    bridge._task_lock = threading.Lock()
    bridge.task = "Start driving in the inner lane, slowly."
    bridge.queue = Mock()
    bridge._publish = Mock()
    bridge.get_logger = lambda: Mock()
    bridge._avoid_hold_cb(String(data="1"))
    bridge._control()
    bridge._publish.assert_called_with(0., 0., override="hold")
    bridge.queue.pop.assert_not_called()
    assert bridge.task
    bridge._hold_cb(String(data="1"))
    bridge._avoid_hold_cb(String(data="0"))
    bridge.queue.clear.assert_called_once()
    bridge._control()
    bridge.queue.pop.assert_not_called()
    assert bridge._hold

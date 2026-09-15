"""Extra display inference must leave control commitment and priority intact."""
import pytest

pytest.importorskip("rclpy")
from sant_vla_pkg.vla_bridge_node import inference_request_kind


def test_default_inference_schedule_preserves_control_refills():
    for queued in range(31):
        result = inference_request_kind(queued, 9, 100., 0., 0., 10., .1)
        assert result == ("control" if queued < 9 else None)


def test_preview_is_rate_limited_and_yields_time_for_control():
    assert inference_request_kind(30, 9, 1., 0., .4, 10., .1) == "preview"
    assert inference_request_kind(30, 9, .2, 0., .4, 10., .1) is None
    assert inference_request_kind(10, 9, 1., 0., .4, 10., .1) is None
    assert inference_request_kind(8, 9, .1, 0., .4, 10., .1) == "control"
    # Slower responses reserve a larger margin before the control refill.
    assert inference_request_kind(15, 9, 1., 0., .4, 10., .4) is None

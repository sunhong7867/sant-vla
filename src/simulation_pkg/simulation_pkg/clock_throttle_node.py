"""Throttle the simulation clock for the ROS graph.

The gz world steps at 1 kHz and the ros_gz clock bridge forwards every step:
/clock at ~940 Hz was measured on 2026-08-28. Every use_sim_time node's
executor wakes per /clock message, so the whole stack burned CPU idling —
one of the two legs (with RAM exhaustion) of the desktop-freeze incident.

This node subscribes to the raw bridged clock and republishes it at a bounded
rate (default 100 Hz — 10 ms sim-time resolution, ample for 10-20 Hz control
timers). driving_sim.launch remaps the bridge to /clock_raw and runs this in
between.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import (QoSDurabilityPolicy, QoSHistoryPolicy, QoSProfile,
                       QoSReliabilityPolicy)
from rosgraph_msgs.msg import Clock


class ClockThrottleNode(Node):
    def __init__(self):
        super().__init__("clock_throttle")
        rate = float(self.declare_parameter("rate_hz", 100.0).value)
        self._min_period = 1.0 / max(1.0, rate)
        self._last_pub = -1.0
        qos = QoSProfile(
            reliability=QoSReliabilityPolicy.BEST_EFFORT,
            history=QoSHistoryPolicy.KEEP_LAST,
            durability=QoSDurabilityPolicy.VOLATILE, depth=1)
        self._pub = self.create_publisher(Clock, "/clock", qos)
        self.create_subscription(Clock, "/clock_raw", self._cb, qos)
        self.get_logger().info(f"clock throttle: /clock_raw -> /clock @ {rate:.0f} Hz")

    def _cb(self, msg):
        t = msg.clock.sec + msg.clock.nanosec * 1e-9
        if t - self._last_pub >= self._min_period or t < self._last_pub:
            self._last_pub = t
            self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = ClockThrottleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

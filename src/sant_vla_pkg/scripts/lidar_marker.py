#!/usr/bin/env python3
"""Draw the ego LiDAR as blue rays in the Gazebo 3D view (2026-10-13, lecture GUI).

gz's VisualizeLidar GUI plugin only starts drawing once its topic combo box is on
screen, so it cannot live hidden inside the Driving Studio's embedded 3D view.
This script draws the same picture through the GUI's MarkerManager instead:

    /scan (gz.msgs.LaserScan) + /model/ego_vehicle/pose (gz.msgs.Pose)
      -> a filled TRIANGLE_FAN (sensor -> hit, misses out to max range) + its edge + hit POINTS
      -> /marker_array service of the connected GUI (MarkerManager plugin). The
         single /marker service answers gz.msgs.Empty (one-way), which the Python
         binding's request() never sees back, so the two-way array service is used.

Sensor frame (prius_hybrid lidar_link, measured 2026-10-12/13): ray angle a is in
the MODEL frame, direction (cos a, sin a); the car's forward is model -y (a = 270
deg); the sensor sits at model (0, -1.80, 0.70). Run in the stack's GZ_PARTITION:
    python3 src/sant_vla_pkg/scripts/lidar_marker.py [--hz 5] [--max-range 12]
"""
import argparse
import math
import threading
import time

from gz.msgs10.laserscan_pb2 import LaserScan
from gz.msgs10.marker_pb2 import Marker
from gz.msgs10.marker_v_pb2 import Marker_V
from gz.msgs10.boolean_pb2 import Boolean
from gz.msgs10.pose_pb2 import Pose
from gz.transport13 import Node

SENSOR = (0.0, -1.80, 0.70)       # lidar_link origin in the model frame
FWD = math.radians(270.0)         # scan angle of the car's forward (model -y)


def quat_rotate(q, v):   # kept for tools that need world points
    x, y, z, w = q
    vx, vy, vz = v
    # v' = v + 2w(q x v) + 2 q x (q x v)
    cx, cy, cz = y * vz - z * vy, z * vx - x * vz, x * vy - y * vx
    ccx, ccy, ccz = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (vx + 2 * (w * cx + ccx), vy + 2 * (w * cy + ccy), vz + 2 * (w * cz + ccz))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=20.0)
    ap.add_argument("--max-range", type=float, default=12.0)
    ap.add_argument("--stride", type=int, default=1, help="draw every Nth ray")
    args = ap.parse_args()

    node = Node()
    lock = threading.Lock()
    state = {"scan": None, "pose": None}

    def on_scan(msg):
        with lock:
            state["scan"] = msg

    def on_pose(msg):
        with lock:
            state["pose"] = msg

    node.subscribe(LaserScan, "/scan", on_scan)
    node.subscribe(Pose, "/model/ego_vehicle/pose", on_pose)

    period = 1.0 / args.hz
    warned = False
    while True:
        time.sleep(period)
        with lock:
            scan, pose = state["scan"], state["pose"]
        if scan is None or pose is None:
            continue
        # Geometry stays in the MODEL frame and the marker pose is the car's latest pose, so the
        # fan rides with the car between scans (5-10 Hz) instead of jumping (GUI test 10-13).
        # Thin LINE_LIST rays vanished at shallow view angles; a filled translucent fan does not.
        def style(m, mid, mtype, rgba):
            m.ns, m.id, m.action, m.type = "ego_lidar", mid, Marker.ADD_MODIFY, mtype
            m.pose.position.CopyFrom(pose.position)
            m.pose.orientation.CopyFrom(pose.orientation)
            for c in (m.material.ambient, m.material.diffuse, m.material.emissive):
                c.r, c.g, c.b, c.a = rgba
        fan, edge, hits = Marker(), Marker(), Marker()
        style(fan, 1, Marker.TRIANGLE_FAN, (0.62, 0.82, 1.0, 0.30))
        style(edge, 2, Marker.LINE_STRIP, (0.45, 0.70, 1.0, 0.85))
        style(hits, 3, Marker.POINTS, (0.25, 0.55, 1.0, 1.0))
        o = fan.point.add()
        o.x, o.y, o.z = SENSOR
        far = min(scan.range_max, args.max_range)
        a = scan.angle_min
        for i, r in enumerate(scan.ranges):
            # rays pointing backwards only hit the car's own body (0.1-0.5 m): skip them
            if i % args.stride == 0 and math.cos(a - FWD) > -0.05:
                hit = scan.range_min <= r < far
                rr = r if hit else far
                end = (SENSOR[0] + rr * math.cos(a), SENSOR[1] + rr * math.sin(a), SENSOR[2])
                for m in (fan, edge) + ((hits,) if hit else ()):
                    pt = m.point.add()
                    pt.x, pt.y, pt.z = end
            a += scan.angle_step
        if not hits.point:
            hits.action = Marker.DELETE_MARKER
        batch = Marker_V()
        for m in (fan, edge, hits):
            batch.marker.add().CopyFrom(m)
        ok = node.request("/marker_array", batch, Marker_V, Boolean, 500)
        if not ok[0] and not warned:
            print("lidar_marker: /marker_array not answering (no GUI with MarkerManager yet?) — retrying", flush=True)
            warned = True


if __name__ == "__main__":
    main()

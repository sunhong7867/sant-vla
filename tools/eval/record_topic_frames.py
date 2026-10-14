#!/usr/bin/env python3
"""Save a ROS image topic to numbered JPEGs until SIGINT/SIGTERM (2026-09-30).

Used by tools/eval/record_clip.sh to film avoidance trials from the world's
top_camera (moved over the obstacle). Handles rgb8/bgr8 sensor_msgs/Image
without cv_bridge.

    python3 tools/eval/record_topic_frames.py /top_camera/image_raw /tmp/frames
"""
import os, signal, sys, time

import rclpy
from PIL import Image as PILImage
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

topic, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
rclpy.init()
node = rclpy.create_node("clip_recorder")
n = [0]
t0 = [None]


def cb(msg):
    mode = {"rgb8": "RGB", "bgr8": "RGB"}.get(msg.encoding)
    if mode is None:
        return
    im = PILImage.frombuffer("RGB", (msg.width, msg.height), bytes(msg.data), "raw", "RGB", msg.step, 1)
    if msg.encoding == "bgr8":
        b, g, r = im.split()
        im = PILImage.merge("RGB", (r, g, b))
    im.save(os.path.join(out, f"{n[0]:05d}.jpg"), quality=90)
    if t0[0] is None:
        t0[0] = time.time()
    n[0] += 1


node.create_subscription(Image, topic, cb, qos_profile_sensor_data)
stop = [False]
signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
while not stop[0]:
    rclpy.spin_once(node, timeout_sec=0.1)
dt = time.time() - t0[0] if t0[0] else 0.0
print(f"saved {n[0]} frames in {dt:.1f} s ({n[0] / dt if dt else 0:.1f} fps)", flush=True)
with open(os.path.join(out, "fps.txt"), "w") as f:
    f.write(f"{n[0] / dt if dt else 10:.2f}\n")
node.destroy_node()
rclpy.shutdown()

"""Acknowledged Gazebo requests used by the dashboard and scene presets."""
import math
import re
import subprocess

from sant_vla_pkg.gz_pose import resolve_gz_bin


def request(service, message_type, payload, timeout=5):
    result = subprocess.run(
        [resolve_gz_bin(), "service", "-s", service, "--reqtype", message_type,
         "--reptype", "gz.msgs.Boolean", "--timeout", str(int(timeout*1000)),
         "--req", payload], capture_output=True, text=True, timeout=timeout+2)
    if result.returncode or not re.search(r"\bdata:\s*true\b", result.stdout):
        raise RuntimeError(f"{service}: {result.stderr.strip() or result.stdout.strip() or '응답 없음'}")
    return result.stdout


def pose_message(pose):
    x, y, z, roll, pitch, yaw = pose
    cr, sr = math.cos(roll/2), math.sin(roll/2)
    cp, sp = math.cos(pitch/2), math.sin(pitch/2)
    cy, sy = math.cos(yaw/2), math.sin(yaw/2)
    qx, qy = sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy
    qz, qw = cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy
    return (f"position: {{x: {x} y: {y} z: {z}}} "
            f"orientation: {{x: {qx} y: {qy} z: {qz} w: {qw}}}")


def move_camera(pose):
    # /gui/camera/pose is telemetry, not a camera command topic.
    return request("/gui/move_to/pose", "gz.msgs.GUICamera",
                   "pose: {" + pose_message(pose) + "}")


def top_camera_pose(aspect=1.5):
    # Same orientation as the original Gazebo top view. Fit the entire
    # 58.14 x 43.71 m track even in a short, wide split panel. MinimalScene
    # uses a 90° horizontal field of view (verified against camera telemetry).
    height = max(58.14, 43.71 * max(aspect, 0.5)) / 2 * 1.06
    # The ground plane is centered at the world origin. The previous
    # hand-adjusted offset displaced the track from the viewport center.
    return [0.0, 0.0, height, -math.pi, math.pi/2, 0.0]

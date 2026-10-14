#!/usr/bin/env python3
"""Trim a recorded frame folder to "car enters view .. car leaves/stops" and
encode it without any text (2026-10-01).

Start = first frame whose change against the frame 5 earlier exceeds a small
threshold (the ego entering from the left edge; the scene is static before),
end = last such frame + `--tail-s`. The bottom off-track band is cropped and
the image scaled 1.5x, as in the earlier clips.

    python3 tools/eval/trim_clip.py eval_out/course/clips/frames_avoid \\
        eval_out/course/clips/r40_box_avoid.mp4
"""
import argparse, os, subprocess

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("frames"); ap.add_argument("out")
ap.add_argument("--thresh", type=float, default=0.3, help="mean abs grey change (0-255) at 160x120")
ap.add_argument("--lead-s", type=float, default=0.0)
ap.add_argument("--tail-s", type=float, default=1.5)
ap.add_argument("--crop", default="640:384:0:0")
ap.add_argument("--scale", default="960:576")
a = ap.parse_args()

fs = sorted(f for f in os.listdir(a.frames) if f.endswith(".jpg"))
fps = float(open(os.path.join(a.frames, "fps.txt")).read().strip()) if os.path.exists(
    os.path.join(a.frames, "fps.txt")) else 28.0


def grey(i):
    return np.asarray(Image.open(os.path.join(a.frames, fs[i])).convert("L").resize((160, 120)), dtype=np.float32)


moving = []
prev = grey(0)
for i in range(5, len(fs), 5):
    cur = grey(i)
    if np.abs(cur - prev).mean() > a.thresh:
        moving.append(i)
    prev = cur
# keep only sustained motion (>= 3 consecutive samples = 15 frames): the obstacle
# spawning/removal is a one-sample jump, the driving car is a run
runs, cur = [], []
for i in moving:
    if cur and i - cur[-1] > 5:
        runs.append(cur); cur = []
    cur.append(i)
if cur:
    runs.append(cur)
runs = [r for r in runs if len(r) >= 3]
if not runs:
    raise SystemExit("no sustained motion found")
start = max(0, runs[0][0] - 5 - int(a.lead_s * fps))
end = min(len(fs) - 1, runs[-1][-1] + int(a.tail_s * fps))
n = end - start + 1
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", f"{fps:.2f}",
                "-start_number", str(start), "-i", os.path.join(a.frames, "%05d.jpg"),
                "-frames:v", str(n),
                "-vf", f"crop={a.crop},scale={a.scale}:flags=lanczos",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", a.out], check=True)
print(f"{a.out}: frames {start}..{end} ({n / fps:.1f} s @ {fps:.1f} fps)")

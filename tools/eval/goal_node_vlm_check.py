#!/usr/bin/env python3
"""Offline check of goal_from_scene_node's perception half (2026-10-12).

Sends ONE saved camera frame + a request to the same VLM with the node's prompt,
parses relation + boxes with the node's parser, converts box centres to bearings
(hfov 62.2 deg, /camera/image_raw) and prints the composed goal. Writes an
annotated copy (boxes, goal column) for the lecture material.

  python3 tools/eval/goal_node_vlm_check.py --host http://127.0.0.1:11502 \
      eval_out/course/goto_eval/r26_sec_SEC_frames/trial_000.jpg "Go to the horse." --out /tmp/x.jpg
"""
import argparse
import base64
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "src/sant_vla_pkg"))
from sant_vla_pkg import goal_from_scene_node as N          # noqa: E402  (needs ROS env for rclpy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image"); ap.add_argument("request")
    ap.add_argument("--host", default="http://127.0.0.1:11501")
    ap.add_argument("--model", default="qwen2.5vl:7b")
    ap.add_argument("--hfov", type=float, default=62.2)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    from PIL import Image, ImageDraw
    img = Image.open(a.image).convert("RGB")
    w, h = img.size
    data = base64.b64encode(open(a.image, "rb").read()).decode("ascii")
    payload = {"model": a.model, "stream": False, "options": {"temperature": 0.1, "num_predict": 200},
               "messages": [{"role": "user", "content": N.PROMPT.format(req=a.request, w=w, h=h),
                             "images": [data]}]}
    t0 = time.monotonic()
    req = urllib.request.Request(f"{a.host}/api/chat", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        reply = (json.loads(r.read().decode()).get("message") or {}).get("content", "")
    dt = time.monotonic() - t0
    print(f"[{dt:.1f}s] reply: {reply.strip()[:300]}")
    rel, boxes = N.GoalFromScene._parse(None, reply, a.request, w, h)
    f = (w / 2) / math.tan(math.radians(a.hfov) / 2)
    print(f"relation={rel} boxes={[[round(v) for v in b] for b in boxes]}  f={f:.0f}px")
    pts = []
    for b in boxes:
        u = (b[0] + b[2]) / 2
        bearing = math.degrees(math.atan((w / 2 - u) / f))
        v = b[3] - h / 2
        ang = math.atan(v / f)
        mono = 1.4 / math.tan(ang) if ang > 0.02 else float("nan")
        pts.append((bearing, mono))
        print(f"  box {[round(x) for x in b]} -> bearing {bearing:+.1f} deg, monocular dist ~{mono:.1f} m (cam 1.4 m)")
    if a.out:
        d = ImageDraw.Draw(img)
        for b in boxes:
            d.rectangle(b, outline=(255, 40, 40), width=3)
        if pts:
            if rel == "between" and len(pts) >= 2:
                u = (((boxes[0][0] + boxes[0][2]) / 2) + ((boxes[1][0] + boxes[1][2]) / 2)) / 2
            else:
                u = (boxes[0][0] + boxes[0][2]) / 2
                if rel in ("left_of", "right_of"):
                    u += (-1 if rel == "left_of" else 1) * 60
            d.line([(u, 0), (u, h)], fill=(40, 220, 40), width=3)
            d.text((10, 10), f"{a.request} -> {rel}", fill=(255, 255, 0))
        img.save(a.out, quality=90)
        print("annotated ->", a.out)


if __name__ == "__main__":
    main()

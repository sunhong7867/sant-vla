#!/usr/bin/env python3
"""Location prior or averaging? (2026-09-30)

r38/r39 predict a +0.65 m swerve on EMPTY-lane (v0) frames 10-14 m before the
fixed obstacle spot (lane2 70). Two readings:
  A) location memorisation — "this background = swerve here"
  B) can't tell obstacle/no-obstacle at that range -> weighted average of v0/v1
This feeds frames from a corpus that NEVER had an obstacle (Stanley cruise,
lane2 only) at several track points and compares predicted vs demonstrated
3 s lateral end. A excess (PRED - DEMO) that appears only at the training spot
(70) and not at a control spot on the same straight (45) or elsewhere (142)
supports A; ~0 everywhere supports B.

    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_bg.py \\
        runs/course/navvla_reasoning_r38/checkpoints/last/pretrained_model data/packed_stanley
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")
# lane2 indices (track_paths.json). 70 = training spot, 45 = same left straight,
# 142 = bottom straight end (10-14 m before it is the curve exit -> compare err, not raw)
POINTS = {"70": (-15.9940, -12.8414), "45": (-16.9814, -4.3967), "142": (3.9117, -24.5726),
          # 250/330: packed_ramp70 episodes (start idx 4-13, end idx 112-211) never drove here
          "250": (16.7415, 5.2367), "330": (2.0144, 24.5478)}
WINDOWS = [(14, 20), (10, 14), (6, 10)]

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("packed")
ap.add_argument("--stride", type=int, default=3)
ap.add_argument("--zero-state", action="store_true")
ap.add_argument("--points", default=None, help="comma list of POINTS keys (default all)")
a = ap.parse_args()
if a.points:
    POINTS = {k: POINTS[k] for k in a.points.split(",")}

p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]


def predict(img_path, state, instr):
    img = np.array(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [instr]}
    b = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in pre(b).items()}
    torch.manual_seed(20260929)
    with torch.inference_mode():
        out = p.predict_action_chunk(b)
    ch = post(out)[0].float().cpu().numpy()[:, :3]
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return y


def demo_lat(rows, k):
    x0, y0, h0 = rows[k]["x"], rows[k]["y"], rows[k]["heading"]
    j = min(k + 30, len(rows) - 1)
    return -math.sin(h0) * (rows[j]["x"] - x0) + math.cos(h0) * (rows[j]["y"] - y0)


res = {}
n_ep = 0
for d in sorted(os.listdir(a.packed)):
    ep = os.path.join(a.packed, d)
    mp = os.path.join(ep, "meta.json")
    if not os.path.exists(mp):
        continue
    m = json.load(open(mp))
    slots = m.get("intent_slots") or {}
    if slots.get("lane") != "lane2" or (slots.get("obstacle") or {}).get("present"):
        continue
    n_ep += 1
    rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
    for name, (px, py) in POINTS.items():
        for k in range(10, len(rows) - 31, a.stride):
            r = rows[k]
            if (r["state"] or [0])[0] < 0.8:
                continue
            dx, dy = px - r["x"], py - r["y"]
            along = dx * math.cos(r["heading"]) + dy * math.sin(r["heading"])
            if abs(-dx * math.sin(r["heading"]) + dy * math.cos(r["heading"])) > 2.5:
                continue   # point must be (roughly) in our lane ahead
            for lo, hi in WINDOWS:
                if lo <= along < hi:
                    st = list(r["state"])
                    if a.zero_state:
                        st[1] = st[2] = 0.0
                    res.setdefault((name, (lo, hi)), []).append(
                        (predict(os.path.join(ep, r["frame"]), st, m.get("instruction", "")),
                         demo_lat(rows, k)))

ck = "/".join(a.checkpoint.split("/")[1:4])
print(f"[{ck}] {a.packed}  lane2 no-obstacle episodes={n_ep}  zero_state={a.zero_state}")
print("  lateral end of 3 s chunk (m, + = left = swerve side at 70); EXCESS = PRED - DEMO")
for name in POINTS:
    for w in WINDOWS:
        v = res.get((name, w))
        if not v:
            print(f"  idx {name:>3s} {w[0]:2d}-{w[1]:2d} m  n=  0"); continue
        pr = np.array([x[0] for x in v]); de = np.array([x[1] for x in v])
        print(f"  idx {name:>3s} {w[0]:2d}-{w[1]:2d} m  n={len(v):3d}  DEMO {de.mean():+.2f}  "
              f"PRED {pr.mean():+.2f}  EXCESS {np.mean(pr - de):+.2f} (sd {np.std(pr - de):.2f})")

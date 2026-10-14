#!/usr/bin/env python3
"""Replay a closed-loop capture through a checkpoint, next to the training
frames at the same place (2026-09-29).

capture.jsonl (tools/eval/closed_loop_capture.py) holds the live frame, pose
and the exact bridge state. For each live frame on the approach (obstacle
along 3-14 m ahead, |across| < 3 m) this predicts the 3 s lateral end under:
  live      the bridge's state as recorded
  v216      same, speed replaced by 2.16 m/s (the training 'normal' tier)
  zero_yw   same, yaw_rate/steer set to 0
and, for comparison, the nearest TRAINING v1 frame (packed corpus, <= 0.5 m,
<= 5 deg) predicted with its own state and instruction, plus its demo lateral.

    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_capture.py \\
        runs/course/navvla_reasoning_r37/checkpoints/last/pretrained_model \\
        data/course/capture/r37_box_1 data/course/packed_ramp
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("capture"); ap.add_argument("packed")
a = ap.parse_args()
p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]


def lat(img_path, state, instr):
    img = np.asarray(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    st = list(state)[:want] + [0.0] * max(0, want - len(state))
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [instr]}
    b = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in pre(b).items()}
    torch.manual_seed(20260929)
    with torch.inference_mode():
        ch = post(p.predict_action_chunk(b))[0].float().cpu().numpy()[:, :3]
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


meta = json.load(open(os.path.join(a.capture, "meta.json")))
instr = meta["instruction"]
cap = [json.loads(l) for l in open(os.path.join(a.capture, "capture.jsonl"))]

train = []   # (x, y, heading, ep, rows, k, instr)
for d in sorted(os.listdir(a.packed)):
    ep = os.path.join(a.packed, d)
    if not os.path.exists(os.path.join(ep, "meta.json")):
        continue
    m = json.load(open(os.path.join(ep, "meta.json")))
    if m.get("cf_variant_id") != "v1":
        continue
    rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
    for k, r in enumerate(rows[:-31]):
        if (r["state"] or [0])[0] > 0.8:
            train.append((r["x"], r["y"], r["heading"], ep, rows, k, m.get("instruction", "")))
T = np.array([(t[0], t[1]) for t in train])

print(f"[{'/'.join(a.checkpoint.split('/')[1:4])}] capture {a.capture}  instr {instr!r}")
swaps = []
print(" along  across   v    steer |  live   v216  zero_yw |  train_v1: pos_err  pred   demo  (train state v/steer)")
for r in cap:
    o = r["obstacles"][0]
    if not (3.0 <= o["along_m"] <= 14.0 and abs(o["across_m"]) < 3.0) or r["k"] % 2:
        continue
    img = os.path.join(a.capture, r["frame"])
    st = r["state"]
    live = lat(img, st, instr)
    v216 = lat(img, [2.16] + st[1:], instr)
    zyw = lat(img, [st[0], 0.0, 0.0] + st[3:], instr)
    dd = np.hypot(T[:, 0] - r["x"], T[:, 1] - r["y"])
    j = int(np.argmin(dd))
    tx, ty, th, ep, rows, k, tinstr = train[j]
    dyaw = abs(math.degrees(math.atan2(math.sin(th - r["heading"]), math.cos(th - r["heading"]))))
    if dd[j] <= 0.5 and dyaw <= 5.0:
        timg = os.path.join(ep, rows[k]["frame"])
        tp = lat(timg, rows[k]["state"], tinstr)
        tr = f"{dd[j]:5.2f}m  {tp:+.2f}  {demo_lat(rows, k):+.2f}  ({rows[k]['state'][0]:.2f}/{rows[k]['state'][2]:+.2f})"
        # 2x2 swap, state held at the LIVE value: which input carries the gap?
        swaps.append((o["along_m"], dyaw, live, lat(img, st, tinstr), lat(timg, st, instr), lat(timg, st, tinstr), tinstr))
    else:
        tr = f"no match ({dd[j]:.2f} m, {dyaw:.0f} deg)"
    print(f" {o['along_m']:5.1f}  {o['across_m']:+5.2f}  {st[0]:.2f} {st[2]:+.2f} | {live:+.2f}  {v216:+.2f}  {zyw:+.2f}  |  {tr}")

if swaps:
    print("\n2x2 swap at matched positions (state = live):")
    print(" along  dyaw |  liveImg+liveInstr  liveImg+trainInstr  trainImg+liveInstr  trainImg+trainInstr | train instr")
    for al, dy, a1, a2, a3, a4, ti in swaps:
        print(f" {al:5.1f}  {dy:4.1f} |  {a1:+.2f}              {a2:+.2f}              {a3:+.2f}              {a4:+.2f}   | {ti[:50]!r}")

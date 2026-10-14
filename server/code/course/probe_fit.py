#!/usr/bin/env python3
"""Does the policy reproduce its OWN training demos? (2026-09-29)

For v1 (swerve) and v0 (empty lane) episodes of a packed corpus, frames on the
approach (before closest point to the fixed obstacle spot), grouped by centre
distance window: feed each frame with its OWN state + instruction and compare
the predicted 3 s lateral end with the demonstrated one (next 30 rows).
Signed toward the swerve side (demo v1 lateral is +). v1 error ~ -demo means
the head outputs cruise where it was trained to swerve = underfit.

    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_fit.py \\
        runs/course/navvla_reasoning_r37/checkpoints/last/pretrained_model \\
        data/course/packed_ramp
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")
OB = (3.9116529410275507, -24.572617837995033)   # lane2 index 142 (fixed spot)
WINDOWS = [(10, 14), (6, 10), (3, 6)]

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("packed")
ap.add_argument("--stride", type=int, default=3)
ap.add_argument("--zero-state", action="store_true", help="feed normalized-mean yaw_rate/steer (0 raw)")
ap.add_argument("--ob", default=None, help="x,y of the fixed obstacle spot (default lane2 142; "
                "lane2 70 = -15.99,-12.84)")
a = ap.parse_args()
if a.ob:
    OB = tuple(float(v) for v in a.ob.split(","))

p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]


def predict(img_path, state, instr):
    img = np.asarray(Image.open(img_path).convert("RGB"))
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


res = {}   # (variant, window) -> list of (pred, demo)
for d in sorted(os.listdir(a.packed)):
    ep = os.path.join(a.packed, d)
    if not os.path.exists(os.path.join(ep, "meta.json")):
        continue
    m = json.load(open(os.path.join(ep, "meta.json")))
    var = m.get("cf_variant_id")
    rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
    dist = [math.hypot(r["x"] - OB[0], r["y"] - OB[1]) for r in rows]
    kmin = int(np.argmin(dist))
    for k in range(10, min(kmin, len(rows) - 31), a.stride):
        if (rows[k]["state"] or [0])[0] < 0.8:
            continue
        for lo, hi in WINDOWS:
            if lo <= dist[k] < hi:
                st = list(rows[k]["state"])
                if a.zero_state:
                    st[1] = st[2] = 0.0
                res.setdefault((var, (lo, hi)), []).append(
                    (predict(os.path.join(ep, rows[k]["frame"]), st, m.get("instruction", "")),
                     demo_lat(rows, k)))
ck = "/".join(a.checkpoint.split("/")[1:4])
print(f"[{ck}] {a.packed}  zero_state={a.zero_state}  (lateral end of 3 s chunk, m; + = swerve side)")
for var in ("v1", "v0"):
    for w in WINDOWS:
        v = res.get((var, w))
        if not v:
            continue
        pr = np.array([x[0] for x in v]); de = np.array([x[1] for x in v])
        print(f"  {var} {w[0]:2d}-{w[1]:2d} m  n={len(v):3d}  DEMO {de.mean():+.2f}  PRED {pr.mean():+.2f}  "
              f"err {np.mean(pr - de):+.2f}  |err| {np.mean(np.abs(pr - de)):.2f}  corr {np.corrcoef(pr, de)[0, 1]:+.2f}")

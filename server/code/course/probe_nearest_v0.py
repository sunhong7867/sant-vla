#!/usr/bin/env python3
"""Counterfactual probe for v1 episodes WITHOUT a v0 sibling (2026-09-29).

packed_ramp_heldout kept only 1 v0/v1 pair after finalize, so the paired
probe (probe_obstacle_counterfactual.py) has n=1 there. The swerve spot is
fixed on a static track, so an empty-lane image from ANY v0 episode at the
same pose is a valid counterfactual: for every v1 frame in the distance
window, take the nearest v0 frame (position <= --max-pos-m, heading <=
--max-yaw-deg) from the v0 pool, and feed BOTH images with the v1 frame's
state and instruction — only the obstacle pixels differ.

Frames of one episode are strongly correlated: report episodes, not frames.

SIGNED metric (v1 - v0 lateral end, sign of the demo's swerve = +): noise
from small pose/viewpoint differences is symmetric and averages out; |diff|
does not. On packed_ramp at 10-14 m the paired |diff| probe gave r26 — a
model that never saw an avoidance demo — 0.389 m (curve-exit viewpoint
mismatch between v0/v1 at the same frame index), i.e. no usable floor.

    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_nearest_v0.py \\
        runs/course/navvla_reasoning_r36/checkpoints/last/pretrained_model \\
        --v1 data/course/packed_ramp_heldout --v0 data/course/packed_ramp \\
        --near 10 --far 14
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")


def load(ck):
    p = ReasoningSmolVLAPolicy.from_pretrained(ck).to(device).eval()
    pre, post = make_pre_post_processors(p.config, ck)
    cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
    return p, pre, post, cam


def chunk(policy, pre, post, cam, img_path, instruction, state):
    img = np.asarray(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    want = policy.config.input_features["observation.state"].shape[0]
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0),
         "task": [instruction]}
    b = {kk: (v.to(device) if torch.is_tensor(v) else v) for kk, v in pre(b).items()}
    torch.manual_seed(20260923)
    with torch.inference_mode():
        out = policy.predict_action_chunk(b)
    return post(out)[0].float().cpu().numpy()[:, :3]


def lat_end(ch):
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return y


def episodes(root):
    for d in sorted(os.listdir(root)):
        ep = os.path.join(root, d)
        if os.path.isdir(ep) and os.path.exists(os.path.join(ep, "meta.json")):
            m = json.load(open(os.path.join(ep, "meta.json")))
            rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
            yield ep, m, rows


def demo_lat(rows, k):
    x0, y0, h0 = rows[k]["x"], rows[k]["y"], rows[k]["heading"]
    j = min(k + 30, len(rows) - 1)
    dx, dy = rows[j]["x"] - x0, rows[j]["y"] - y0
    return -math.sin(h0) * dx + math.cos(h0) * dy


ap = argparse.ArgumentParser()
ap.add_argument("checkpoint")
ap.add_argument("--v1", nargs="+", required=True, help="packed dirs with v1 episodes to probe")
ap.add_argument("--v0", nargs="+", required=True, help="packed dirs forming the empty-lane pool")
ap.add_argument("--near", type=float, default=10.0)
ap.add_argument("--far", type=float, default=14.0)
ap.add_argument("--stride", type=int, default=2, help="use every Nth frame in the window")
ap.add_argument("--max-pos-m", type=float, default=0.3)
ap.add_argument("--max-yaw-deg", type=float, default=3.0)
a = ap.parse_args()

pool = []   # (x, y, heading, ep, rows, k)
for root in a.v0:
    for ep, m, rows in episodes(root):
        if m.get("cf_variant_id") != "v0":
            continue
        for k, r in enumerate(rows):
            if k + 30 < len(rows) and (r["state"] or [0])[0] > 0.8:
                pool.append((r["x"], r["y"], r["heading"], ep, rows, k))
P = np.array([(p[0], p[1]) for p in pool])
print(f"v0 pool: {len(pool)} frames")

p, pre, post, cam = load(a.checkpoint)
per_ep = []
for root in a.v1:
    for ep, m, rows in episodes(root):
        if m.get("cf_variant_id") != "v1":
            continue
        ob = m["intent_slots"]["obstacle"]
        instr = m.get("instruction", "")
        ks = [k for k in range(10, len(rows) - 31)
              if a.near <= math.hypot(rows[k]["x"] - ob["x"], rows[k]["y"] - ob["y"]) <= a.far
              and (rows[k]["state"] or [0])[0] > 0.8][::a.stride]
        pred, demo = [], []
        for k in ks:
            r = rows[k]
            d = np.hypot(P[:, 0] - r["x"], P[:, 1] - r["y"])
            j = int(np.argmin(d))
            dyaw = abs(math.degrees(math.atan2(math.sin(pool[j][2] - r["heading"]),
                                               math.cos(pool[j][2] - r["heading"]))))
            if d[j] > a.max_pos_m or dyaw > a.max_yaw_deg:
                continue
            _, _, _, ep0, rows0, k0 = pool[j]
            y1 = lat_end(chunk(p, pre, post, cam, os.path.join(ep, r["frame"]), instr, r["state"]))
            y0 = lat_end(chunk(p, pre, post, cam, os.path.join(ep0, rows0[k0]["frame"]), instr, r["state"]))
            pred.append(y1 - y0)
            demo.append(demo_lat(rows, k) - demo_lat(rows0, k0))
        if pred:
            sgn = 1.0 if np.mean(demo) >= 0 else -1.0   # swerve side = +
            pred = [sgn * v for v in pred]; demo = [sgn * v for v in demo]
            per_ep.append((ob.get("model"), len(pred), float(np.mean(pred)),
                           float(np.mean(demo)), float(np.mean(np.abs(pred)))))

ck = "/".join(a.checkpoint.split("/")[1:4])
print(f"[{ck}] nearest-v0 counterfactual, obstacle {a.near:.0f}-{a.far:.0f} m, same state+instruction")
print("  signed lateral end diff v1-v0 (+ = toward the demo's swerve side)")
for model, n, pr, de, ab in per_ep:
    print(f"  {model:16s} frames {n:3d}  PRED {pr:+.3f} m  DEMO {de:+.3f} m  ratio {pr / max(de, 1e-3):+.2f}  (|PRED| {ab:.3f})")
if per_ep:
    by = {}
    for e in per_ep:
        by.setdefault(e[0], []).append(e)
    print("  per object (episode means):")
    for model, es in sorted(by.items()):
        pr = np.mean([e[2] for e in es]); de = np.mean([e[3] for e in es])
        print(f"    {model:16s} n_ep {len(es):2d}  PRED {pr:+.3f}  DEMO {de:+.3f}  ratio {pr / max(de, 1e-3):+.2f}")
    pr = np.mean([e[2] for e in per_ep]); de = np.mean([e[3] for e in per_ep])
    sd = np.std([e[2] for e in per_ep])
    print(f"  ALL n_ep={len(per_ep)}: PRED {pr:+.3f} m (sd {sd:.3f})  DEMO {de:+.3f} m  ratio {pr / max(de, 1e-3):+.2f}")

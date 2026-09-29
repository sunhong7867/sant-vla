#!/usr/bin/env python3
"""Paired counterfactual: same start pose, same instruction, same state —
v0 (clear lane) vs v1 (obstacle in our lane) frames from ONE group at the
same k. If the predicted chunks are identical, the action expert is blind
to the obstacle (vision never reaches the action); if they differ but the
v1 chunk does not slow, it sees it and ignores it. (2026-09-23)

    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/probe_obstacle_counterfactual.py \
        runs/course/navvla_reasoning_r31/checkpoints/last/pretrained_model data/course/packed_multi --n 30
"""
import argparse, json, math, os, random, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # code/ (reasoning_vla)
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")


def load(ck):
    p = ReasoningSmolVLAPolicy.from_pretrained(ck).to(device).eval()
    pre, post = make_pre_post_processors(p.config, ck)
    cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
    return p, pre, post, cam


def chunk(policy, pre, post, cam, ep, meta, rows, k, state):
    img = np.asarray(Image.open(os.path.join(ep, rows[k]["frame"])).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    want = policy.config.input_features["observation.state"].shape[0]
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0),
         "task": [meta.get("instruction", "")]}
    b = {kk: (v.to(device) if torch.is_tensor(v) else v) for kk, v in pre(b).items()}
    torch.manual_seed(20260923)
    with torch.inference_mode():
        out = policy.predict_action_chunk(b)
    return post(out)[0].float().cpu().numpy()[:, :3]


def stats(ch):
    sp = [math.hypot(dx, dy) * 10.0 for dx, dy, _ in ch]
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return math.hypot(x, y), float(np.mean(sp[-10:]) - np.mean(sp[:10])), y


ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("packed", nargs="+"); ap.add_argument("--n", type=int, default=30)
ap.add_argument("--near", type=float, default=12.0, help="min obstacle distance (m) for sampled frames")
ap.add_argument("--far", type=float, default=25.0, help="max obstacle distance (m); swerve demos fire at 8 m -> use 3..10")
a = ap.parse_args()
rng = random.Random(20260923)
groups = {}
for packed in a.packed:
    for d in sorted(os.listdir(packed)):
        ep = os.path.join(packed, d)
        if not os.path.isdir(ep): continue
        m = json.load(open(os.path.join(ep, "meta.json")))
        groups.setdefault(m.get("cf_group_id"), {})[m.get("cf_variant_id")] = (ep, m)
pairs = [(g["v0"], g["v1"]) for g in groups.values() if "v0" in g and "v1" in g]
rng.shuffle(pairs)
p, pre, post, cam = load(a.checkpoint)
rows_cache = {}
def rows_of(ep):
    if ep not in rows_cache:
        rows_cache[ep] = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
    return rows_cache[ep]
d_prog, d_dv, d_lat, g_lat, n = [], [], [], [], 0
per_model = {}
for (ep0, m0), (ep1, m1) in pairs:
    r0, r1 = rows_of(ep0), rows_of(ep1)
    ob = m1["intent_slots"]["obstacle"]
    # frames where the obstacle is 12-25 m ahead along the lane (before the demo brakes)
    ks = [k for k in range(10, min(len(r0), len(r1)) - 31)
          if a.near <= math.hypot(r1[k]["x"] - ob["x"], r1[k]["y"] - ob["y"]) <= a.far
          and (r1[k]["state"] or [0])[0] > 0.8]
    if not ks: continue
    k = rng.choice(ks)
    state = r1[k]["state"]                     # SAME state for both images
    s0 = stats(chunk(p, pre, post, cam, ep0, m0, r0, k, state))
    s1 = stats(chunk(p, pre, post, cam, ep1, m1, r1, k, state))
    def gt_lat(rows):
        x0, y0, h0 = rows[k]["x"], rows[k]["y"], rows[k]["heading"]
        j = min(k + 30, len(rows) - 1)
        dx, dy = rows[j]["x"] - x0, rows[j]["y"] - y0
        return -math.sin(h0) * dx + math.cos(h0) * dy
    g_lat.append(abs(gt_lat(r1) - gt_lat(r0)))
    d_prog.append(s1[0] - s0[0]); d_dv.append(s1[1] - s0[1]); d_lat.append(abs(s1[2] - s0[2]))
    per_model.setdefault(ob.get("model"), []).append(s1[0] - s0[0])
    n += 1
    if n >= a.n: break
print(f"[{'/'.join(a.checkpoint.split('/')[1:4])}] paired v1-v0, same state, obstacle {a.near:.0f}-{a.far:.0f} m ahead, n={n}")
print(f"  progress(v1) - progress(v0): mean {np.mean(d_prog):+.3f} m  (sd {np.std(d_prog):.3f}); "
      f"dv(v1)-dv(v0): {np.mean(d_dv):+.3f} m/s")
print(f"  |lateral end diff| PRED mean {np.mean(d_lat):.3f} m   vs DEMO mean {np.mean(g_lat):.3f} m   "
      f"(ratio {np.mean(d_lat)/max(np.mean(g_lat),1e-3):.2f})")
for m, v in sorted(per_model.items()):
    print(f"    {m:16s} dprog {np.mean(v):+.3f} m (n={len(v)})")

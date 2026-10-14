#!/usr/bin/env python3
"""Situation-conditioned action, offline checks (2026-09-30, r40).

At lane2 70 (fixed obstacle spot of packed_ramp70), per distance window and
variant (v1 obstacle / v0 empty lane / heldout v1):

  1. phrase counterfactual — same image + state, task + phrase for each fixed
     phrase: does "obstacle ahead" swerve on an EMPTY-lane image and does
     "road clear" hold the lane on an OBSTACLE image? (r38's problem was a
     +0.65 m swerve on v0 frames with no text difference at all.)
  2. detector path (what the server does) — decode a short narration from the
     RAW task, map it with situation_of, predict with that phrase.

Lateral = y at the end of the 3 s chunk, + = left = swerve side at 70.

    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_situation.py \\
        runs/course/navvla_reasoning_r40/checkpoints/last/pretrained_model
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from reasoning_vla.reasoning_dataset import (                # noqa: E402
    SITUATION_AHEAD, SITUATION_CLEAR, SITUATION_PASSING, situation_of)
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")
OB = (-15.9940, -12.8414)   # lane2 index 70
WINDOWS = [(14, 20), (10, 14), (6, 10)]
PHRASES = [("clear", SITUATION_CLEAR), ("ahead", SITUATION_AHEAD), ("passing", SITUATION_PASSING)]

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint")
ap.add_argument("--packed", default="data/course/packed_ramp70")
ap.add_argument("--heldout", default="data/course/packed_ramp70_heldout")
ap.add_argument("--per-cell", type=int, default=30)
ap.add_argument("--tokens", type=int, default=12, help="decode length, as the server")
a = ap.parse_args()

p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]


def batch_of(img_path, state, task):
    img = np.array(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [task]}
    return {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in pre(b).items()}


def lateral(b):
    torch.manual_seed(20260929)
    with torch.inference_mode():
        ch = post(p.predict_action_chunk(b))[0].float().cpu().numpy()[:, :3]
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return y


def frames(base, want_var):
    if not os.path.isdir(base):
        return
    for d in sorted(os.listdir(base)):
        ep = os.path.join(base, d)
        mp = os.path.join(ep, "meta.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        if m.get("cf_variant_id") != want_var:
            continue
        rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
        dist = [math.hypot(r["x"] - OB[0], r["y"] - OB[1]) for r in rows]
        kmin = int(np.argmin(dist))
        for lo, hi in WINDOWS:
            ks = [k for k in range(kmin) if lo <= dist[k] < hi and (rows[k]["state"] or [0])[0] >= 0.8]
            if ks:
                k = ks[len(ks) // 2]
                yield (lo, hi), os.path.join(ep, rows[k]["frame"]), rows[k]["state"], m.get("instruction", "")


ck = "/".join(a.checkpoint.split("/")[1:4])
print(f"[{ck}] situation probe at lane2 70 (lateral end of 3 s chunk, m; + = swerve side)")
for name, gen in [("v1 obstacle (trained objects)", frames(a.packed, "v1")),
                  ("v0 empty lane (same spot)", frames(a.packed, "v0")),
                  ("heldout v1 (barrel/person)", frames(a.heldout, "v1"))]:
    cells = {}
    for w, fp, st, instr in gen:
        c = cells.setdefault(w, [])
        if len(c) >= a.per_cell:
            continue
        row = {ph: lateral(batch_of(fp, st, f"{instr} {text}")) for ph, text in PHRASES}
        raw = batch_of(fp, st, instr)                      # detector reads the RAW task
        with torch.inference_mode():
            narr = p.generate_reasoning(raw, max_new_tokens=a.tokens)[0]
        sit = situation_of(narr)
        row["det"] = sit
        row["served"] = lateral(batch_of(fp, st, f"{instr} {sit}"))
        c.append(row)
    print(f"== {name}")
    for w in WINDOWS:
        c = cells.get(w, [])
        if not c:
            print(f"   {w[0]:2d}-{w[1]:2d} m  n= 0"); continue
        mean = {k: np.mean([r[k] for r in c]) for k in ("clear", "ahead", "passing", "served")}
        det = sum(r["det"] != SITUATION_CLEAR for r in c)
        print(f"   {w[0]:2d}-{w[1]:2d} m  n={len(c):2d}  phrase clear {mean['clear']:+.2f}  ahead {mean['ahead']:+.2f}  "
              f"passing {mean['passing']:+.2f}  | detector non-clear {det:2d}/{len(c)}  served {mean['served']:+.2f}")

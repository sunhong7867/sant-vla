#!/usr/bin/env python3
"""Open-loop braking probe for the multi-object avoidance axis (2026-09-23).

Closed-loop trials only say COLLISION / SUCCESS. This asks the graded
question: on frames where the demonstrator was braking for an obstacle in
OUR lane (label phase "ahead", 6-14 m arc, visible), how much forward
progress does the checkpoint's 3 s chunk predict, compared with (a) the
demonstrated future and (b) its own prediction on obstacle-free frames of
the same corpus at the same speed tier?

    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/probe_obstacle_brake.py \
        runs/course/navvla_reasoning_r29/checkpoints/012500/pretrained_model \
        data/course/packed_multi_heldout [data/course/packed_multi ...] --n 40

Prints, per checkpoint: mean predicted progress on 'ahead' frames vs demo
progress, and the same on clear frames. Braking learned <=> ahead ratio
well below clear ratio. Checkpoints are loaded one at a time (the 4070Ti
shares memory with a training run).
"""
import argparse
import json
import math
import os
import random
import sys

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # code/ (reasoning_vla)
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402

device = torch.device("cuda")


def load(ck):
    p = ReasoningSmolVLAPolicy.from_pretrained(ck).to(device).eval()
    pre, post = make_pre_post_processors(p.config, ck)
    cam = [k for k in p.config.input_features
           if k.startswith("observation.images.")][0]
    return p, pre, post, cam


def progress(deltas):
    """Forward distance travelled by a chunk of (dx, dy, dyaw) ego steps."""
    x = y = yaw = 0.0
    for dx, dy, dyaw in deltas:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return math.hypot(x, y)


def decel(deltas):
    """Speed change inside the chunk (m/s): mean of last 10 steps minus
    first 10 steps, at 10 Hz. Negative = the chunk itself brakes. This is the
    quantity 'progress' cannot see: on frames where the demonstrator is
    already slow, matching progress just means 'keep the current speed'."""
    sp = [math.hypot(dx, dy) * 10.0 for dx, dy, _ in deltas]
    return float(np.mean(sp[-10:]) - np.mean(sp[:10]))


def gt_progress(rows, k):
    a, b = rows[k], rows[min(k + 30, len(rows) - 1)]
    return math.hypot(b["x"] - a["x"], b["y"] - a["y"])


def gt_decel(rows, k):
    def v(i):
        st = rows[min(i, len(rows) - 1)]["state"] or [0.0]
        return float(st[0])
    return float(np.mean([v(k + j) for j in range(20, 30)])
                 - np.mean([v(k + j) for j in range(0, 10)]))


def chunk_for(policy, pre, post, cam, ep, meta, rows, k):
    img = np.asarray(Image.open(os.path.join(ep, rows[k]["frame"])).convert("RGB"))
    t_img = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    state = list(rows[k]["state"])
    want = policy.config.input_features["observation.state"].shape[0]
    if want == len(state) + 1:
        still, j = 0.0, k
        while j >= 0 and (rows[j]["state"] or [9])[0] < 0.15 and still < 3.5:
            still += 0.1
            j -= 1
        state = state + [min(3.5, still)]
    batch = {cam: t_img,
             "observation.state": torch.tensor(state, dtype=torch.float32).unsqueeze(0),
             "task": [meta.get("instruction", "")]}
    batch = {kk: (v.to(device) if torch.is_tensor(v) else v) for kk, v in pre(batch).items()}
    torch.manual_seed(20260923)
    with torch.inference_mode():
        out = policy.predict_action_chunk(batch)
    out = post(out)
    return out[0].float().cpu().numpy()[:, :3]


def collect(packed_dirs, n, rng):
    ahead, clear = [], []
    for packed in packed_dirs:
        for d in sorted(os.listdir(packed)):
            ep = os.path.join(packed, d)
            if not os.path.isdir(ep) or not os.path.exists(os.path.join(ep, "reasoning.jsonl")):
                continue
            meta = json.load(open(os.path.join(ep, "meta.json")))
            ob = (meta.get("intent_slots") or {}).get("obstacle") or {}
            rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
            rl = [json.loads(l) for l in open(os.path.join(ep, "reasoning.jsonl"))]
            for r in rl[1:]:
                k, f = r["k"], r["facts"]
                if k + 31 >= len(rows) or (rows[k]["state"] or [0])[0] < 0.8:
                    continue          # need a moving ego with a real 3 s future
                o = f.get("obstacle")
                if ob.get("present") and ob.get("in_our_lane") and o and o["rel"] == "ours" \
                        and 6.0 <= o["arc_m"] <= 22.0 and o.get("visible", True):
                    ahead.append((ep, meta, rows, k, ob.get("model"), ob.get("noun")))
                elif not ob.get("present"):
                    clear.append((ep, meta, rows, k, None, None))
    rng.shuffle(ahead); rng.shuffle(clear)
    return ahead[:n], clear[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkpoints", nargs="+")
    ap.add_argument("--packed", nargs="+", required=True)
    ap.add_argument("--n", type=int, default=40)
    args = ap.parse_args()
    rng = random.Random(20260923)
    ahead, clear = collect(args.packed, args.n, rng)
    print(f"frames: ahead={len(ahead)} clear={len(clear)}  from {args.packed}")
    for ck in args.checkpoints:
        p, pre, post, cam = load(ck)
        res = {}
        for name, picks in (("ahead", ahead), ("clear", clear)):
            pr, gt, dp, dg, per_model = [], [], [], [], {}
            for ep, meta, rows, k, model, noun in picks:
                ch = chunk_for(p, pre, post, cam, ep, meta, rows, k)
                a, g = progress(ch), gt_progress(rows, k)
                da, dgk = decel(ch), gt_decel(rows, k)
                pr.append(a); gt.append(g); dp.append(da); dg.append(dgk)
                if model:
                    per_model.setdefault(model, []).append((da, dgk))
            res[name] = (float(np.mean(pr)), float(np.mean(gt)),
                         float(np.mean(dp)), float(np.mean(dg)), per_model)
        (pa, ga, dpa, dga, pm), (pc, gc, dpc, dgc, _) = res["ahead"], res["clear"]
        tag = "/".join(ck.split("/")[1:3])
        print(f"\n[{tag}]")
        print(f"  ahead : progress pred {pa:5.2f} / demo {ga:5.2f} m ; "
              f"in-chunk dv pred {dpa:+5.2f} / demo {dga:+5.2f} m/s")
        print(f"  clear : progress pred {pc:5.2f} / demo {gc:5.2f} m ; "
              f"in-chunk dv pred {dpc:+5.2f} / demo {dgc:+5.2f} m/s")
        print(f"  braking index (ahead/clear progress): {pa/max(pc,0.1):.2f} (demo {ga/max(gc,0.1):.2f}); "
              f"ahead dv gap pred-demo {dpa-dga:+.2f} m/s")
        for m, v in sorted(pm.items()):
            print(f"    {m:16s} dv pred {np.mean([a for a,_ in v]):+.2f} / demo "
                  f"{np.mean([b for _,b in v]):+.2f}  (n={len(v)})")
        del p, pre, post
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()

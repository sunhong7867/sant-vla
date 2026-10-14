#!/usr/bin/env python3
"""Does the reasoning head SEE the obstacle? (2026-09-30)

The action head swerves on empty-lane frames at the fixed training spot
(probe_bg: +0.76 m at lane2 70, 10-14 m). If the vision path carried the
obstacle, the reasoning head — trained on labels that say "A box ahead in our
outer lane" on v1 frames from ~10-14 m and NEVER on v0 — should mention an
obstacle on v1 frames and not on v0 frames at the same spot.

  v0 mentions an obstacle too  -> narration is also read off the background:
                                  the obstacle signal is weak upstream (vision)
  v1 yes / v0 no, action still averages -> obstacle is seen but does not reach
                                  the action expert

Groups: packed v1 / v0 (same fixed spot), heldout v1 (unseen objects), and a
never-had-an-obstacle cruise corpus passing the same spot.

    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_narr.py \\
        runs/course/navvla_reasoning_r38/checkpoints/last/pretrained_model
"""
import argparse, json, math, os, re, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")
OB = (-15.9940, -12.8414)   # lane2 index 70
WINDOWS = [(14, 20), (10, 14), (6, 10)]
NOUNS = r"\b(box|cone|barrier|barrel|person|car|hatchback|obstacle|vehicle)\b"

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint")
ap.add_argument("--packed", default="data/course/packed_ramp70")
ap.add_argument("--heldout", default="data/course/packed_ramp70_heldout")
ap.add_argument("--cruise", default="data/packed_stanley")
ap.add_argument("--per-cell", type=int, default=30, help="max frames per (group, window)")
ap.add_argument("--show", type=int, default=3, help="example decodes printed per cell")
ap.add_argument("--zero-state", action="store_true", help="yaw_rate/steer = 0 (rule out the steering-state shortcut)")
ap.add_argument("--groups", default="v1,v0,heldout,cruise")
a = ap.parse_args()

p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]


def narrate(img_path, state, instr):
    state = list(state)
    if a.zero_state:
        state[1] = state[2] = 0.0
    img = np.array(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [instr]}
    b = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in pre(b).items()}
    return p.generate_reasoning(b)[0]


def frames(base, want_var=None, need_lane2_clean=False):
    """yield (window, frame_path, state, instruction) — one frame per episode per window."""
    if not os.path.isdir(base):
        return
    for d in sorted(os.listdir(base)):
        ep = os.path.join(base, d)
        mp = os.path.join(ep, "meta.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp))
        slots = m.get("intent_slots") or {}
        if want_var and m.get("cf_variant_id") != want_var:
            continue
        if need_lane2_clean and (slots.get("lane") != "lane2" or (slots.get("obstacle") or {}).get("present")):
            continue
        rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
        dist = [math.hypot(r["x"] - OB[0], r["y"] - OB[1]) for r in rows]
        kmin = int(np.argmin(dist))
        for lo, hi in WINDOWS:
            ks = [k for k in range(kmin) if lo <= dist[k] < hi and (rows[k]["state"] or [0])[0] >= 0.8]
            if ks:
                k = ks[len(ks) // 2]
                yield (lo, hi), os.path.join(ep, rows[k]["frame"]), rows[k]["state"], m.get("instruction", "")


groups = [g for g in [("v1", "v1 (obstacle, trained objects)", lambda: frames(a.packed, "v1")),
                      ("v0", "v0 (empty lane, same spot)", lambda: frames(a.packed, "v0")),
                      ("heldout", "heldout v1 (barrel/person)", lambda: frames(a.heldout, "v1")),
                      ("cruise", "cruise corpus (never an obstacle)", lambda: frames(a.cruise, None, True))]
          if g[0] in a.groups.split(",")]
groups = [(name, make()) for _, name, make in groups]
ck = "/".join(a.checkpoint.split("/")[1:4])
print(f"[{ck}] narration probe at lane2 70 — share of decodes that mention an obstacle  zero_state={a.zero_state}")
for name, gen in groups:
    cells = {}
    for w, fp, st, instr in gen:
        c = cells.setdefault(w, [])
        if len(c) < a.per_cell:
            c.append(narrate(fp, st, instr))
    print(f"== {name}")
    for w in WINDOWS:
        c = cells.get(w, [])
        if not c:
            print(f"   {w[0]:2d}-{w[1]:2d} m  n= 0"); continue
        hit = [s for s in c if re.search(NOUNS, s, re.I) and re.search(r"ahead|passing the|past the", s, re.I)]
        print(f"   {w[0]:2d}-{w[1]:2d} m  n={len(c):2d}  mentions obstacle {len(hit):2d}/{len(c)} ({100*len(hit)/len(c):.0f}%)")
        for s in c[:a.show]:
            print(f"      - {s}")

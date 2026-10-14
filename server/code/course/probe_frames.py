#!/usr/bin/env python3
"""Offline chunk on closed-loop start frames (2026-10-05, goto E split).

Closed loop, r52 went to the LEFT object for both sentences of every E pair,
even with guidance w=3. Here each saved E start frame is fed "left" / "right" /
the null sentence; lateral end of the chunk (m, + = left) per sentence and
per guidance weight. State = a training episode's start state at k=3.

    ./venv/bin/python code/course/probe_frames.py <ckpt> data/course/probe_E --guide 1 3 6
"""
import argparse, json, math, os, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")

ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("dir")
ap.add_argument("--guide", type=float, nargs="*", default=[1.0, 3.0])
ap.add_argument("--state-from", default="data/course/packed_goto_pos")
ap.add_argument("--seeds", type=int, nargs="*", default=[20261004],
                help="noise seeds; lateral ends are averaged over them (2026-10-05: one "
                     "fixed seed gave the SAME +0.6 m left offset on every frame, even "
                     "mirrored ones and training frames whose demos average +0.05 m)")
ap.add_argument("--state", type=float, nargs="*", default=None, help="explicit state (overrides --state-from)")
a = ap.parse_args()
p = ReasoningSmolVLAPolicy.from_pretrained(a.checkpoint).to(device).eval()
pre, post = make_pre_post_processors(p.config, a.checkpoint)
cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
want = p.config.input_features["observation.state"].shape[0]
ep = json.loads(open(os.path.join(a.state_from, "index.jsonl")).readline())["episode"]
state = json.loads(open(os.path.join(a.state_from, ep, "resampled_10hz.jsonl")).readlines()[3])["state"]
state = a.state if a.state is not None else state
state = list(state) + [0.0] * (want - len(state))


def chunk(img_path, task):
    return np.mean([chunk1(img_path, task, sd) for sd in a.seeds], axis=0) if len(a.seeds) > 1 \
        else chunk1(img_path, task, a.seeds[0])


def chunk1(img_path, task, seed):
    img = np.asarray(Image.open(img_path).convert("RGB").resize((640, 480)))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    b = {cam: t, "observation.state": torch.tensor(state, dtype=torch.float32).unsqueeze(0), "task": [task]}
    b = {k: (v.to(device) if torch.is_tensor(v) else v) for k, v in pre(b).items()}
    torch.manual_seed(seed)
    with torch.inference_mode():
        return post(p.predict_action_chunk(b))[0].float().cpu().numpy()[:, :3]


def lat_end(ch):
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return y


rows = [json.loads(l) for l in open(os.path.join(a.dir, "rows.jsonl"))]
tally = {w: [0, 0, 0] for w in a.guide}   # left-sentence end > right-sentence end, n, both on own side
print(f"[{a.checkpoint}] state {np.round(state, 2).tolist()}")
for r in rows:
    f = os.path.join(a.dir, r["frame"])
    cl, cr, cn = chunk(f, "Go to the object on the left."), chunk(f, "Go to the object on the right."), chunk(f, "Go to the object.")
    yn = lat_end(cn)
    line = f"  {r['frame']:16s} L{r['b_left']:+3.0f} R{r['b_right']:+3.0f}  null {yn:+.2f}"
    for w in a.guide:
        yl, yr = lat_end(cn + w * (cl - cn)), lat_end(cn + w * (cr - cn))
        tally[w][0] += yl > yr; tally[w][1] += 1; tally[w][2] += (yl > 0) and (yr < 0)
        line += f" | w{w:g} L {yl:+.2f} R {yr:+.2f}"
    print(line)
for w, (k, n, both) in tally.items():
    print(f"  w={w:g}: left-sentence ends left of right-sentence {k}/{n}; left>0 and right<0 {both}/{n}")

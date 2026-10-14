#!/usr/bin/env python3
"""Goal-channel counterfactual for the point-goal primitive (2026-10-12, g5d).

Same frame, same [v, w, steer], same seed; only the state's goal_bearing is
changed (+-delta rad). If the policy reads the channel, the predicted chunk's
lateral end moves with the sign of the change. Reports sign agreement and the
size of the move against the demos' own 3 s lateral motion. Diagnostic only —
the pre-registered decision is the closed-loop P2 (docs/experiments/goto_object/
20261012_1850_point-goal-primitive-prereg.md).

  CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goal_channel.py \
      runs/course/navvla_reasoning_g5d/checkpoints/015000/pretrained_model \
      data/course/packed_gv2b data/course/packed_sec --n 60 --delta 0.3
"""
import argparse, json, math, os, random, sys
import numpy as np, torch
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # code/ (reasoning_vla)
from reasoning_vla import ReasoningSmolVLAPolicy            # noqa: E402
from lerobot.policies.factory import make_pre_post_processors  # noqa: E402
device = torch.device("cuda")


# (copied from probe_goto_language.py — importing it runs its CLI)
def load(ck):
    p = ReasoningSmolVLAPolicy.from_pretrained(ck).to(device).eval()
    pre, post = make_pre_post_processors(p.config, ck)
    cam = [k for k in p.config.input_features if k.startswith("observation.images.")][0]
    return p, pre, post, cam


def chunk(policy, pre, post, cam, img_path, state, task):
    img = np.asarray(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    want = policy.config.input_features["observation.state"].shape[0]
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
    assert len(st) == want, (len(st), want)
    b = {cam: t, "observation.state": torch.tensor(st, dtype=torch.float32).unsqueeze(0), "task": [task]}
    b = {kk: (v.to(device) if torch.is_tensor(v) else v) for kk, v in pre(b).items()}
    torch.manual_seed(20261004)
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


def demo_lat(rows, k, h=30):
    x0, y0, h0 = rows[k]["x"], rows[k]["y"], rows[k]["heading"]
    j = min(k + h, len(rows) - 1)
    dx, dy = rows[j]["x"] - x0, rows[j]["y"] - y0
    return -math.sin(h0) * dx + math.cos(h0) * dy


def goal_of(meta, row):
    g = (meta.get("intent_slots") or {}).get("goto") or {}
    o = g["objects"][g["target"]]
    dx, dy = o["x"] - row["x"], o["y"] - row["y"]
    b = (math.atan2(dy, dx) - row["heading"] + math.pi) % (2 * math.pi) - math.pi
    return b, math.hypot(dx, dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ckpt"); ap.add_argument("packed", nargs="+")
    ap.add_argument("--n", type=int, default=60); ap.add_argument("--delta", type=float, default=0.3)
    ap.add_argument("--task", default="Target."); ap.add_argument("--seed", type=int, default=20261012)
    a = ap.parse_args()
    eps = []
    for p in a.packed:
        for d in sorted(os.listdir(p)):
            mp, rp = os.path.join(p, d, "meta.json"), os.path.join(p, d, "resampled_10hz.jsonl")
            if os.path.exists(mp) and os.path.exists(rp):
                eps.append((os.path.join(p, d), mp, rp))
    rng = random.Random(a.seed); rng.shuffle(eps); eps = eps[:a.n]
    policy, pre, post, cam = load(a.ckpt)
    agree = n = 0; dys = []; base_err = []; dy_true = []
    for base, mp, rp in eps:
        meta = json.load(open(mp)); rows = [json.loads(l) for l in open(rp) if l.strip()]
        rows = [r for r in rows if isinstance(r.get("action"), list)]
        if len(rows) < 45:
            continue
        k = rng.randint(3, min(25, len(rows) - 35))
        r = rows[k]; b, dist = goal_of(meta, r)
        st = list(r["state"][:3]) + [b, dist, 0.0]
        img = os.path.join(base, r["frame"])
        y0 = lat_end(chunk(policy, pre, post, cam, img, st, a.task))
        yp = lat_end(chunk(policy, pre, post, cam, img, st[:3] + [b + a.delta, dist, 0.0], a.task))
        ym = lat_end(chunk(policy, pre, post, cam, img, st[:3] + [b - a.delta, dist, 0.0], a.task))
        d_demo = demo_lat(rows, k)
        n += 1; agree += int(yp > y0 and ym < y0); dys.append(abs(yp - ym) / 2.0)
        dy_true.append(abs(y0 - d_demo)); base_err.append(abs(d_demo))
        print(f"{os.path.basename(base)[-12:]} k={k:2d} b={math.degrees(b):+6.1f} d={dist:4.1f}  "
              f"y(b)={y0:+.2f} y(b+)={yp:+.2f} y(b-)={ym:+.2f}  demo3s={d_demo:+.2f}")
    import statistics as s
    print(f"\nN={n}  sign agreement (y(b+)>y(b)>y(b-)): {agree}/{n} = {agree/max(n,1):.2f}")
    print(f"mean |dy| per {a.delta} rad: {s.mean(dys):.3f} m   (demo 3 s |lat| mean {s.mean(base_err):.3f} m)")
    print(f"mean |y(b) - demo3s|: {s.mean(dy_true):.3f} m")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Language counterfactual for go-to-object (2026-10-04, r50 diagnosis).

Each goto group = two variants from the SAME start pose and layout that differ
only in the instruction (target noun: cf_axis goto_target, or direct vs lane:
goto_mode). Take one early frame + state of v0 and predict the action chunk
twice: with v0's sentence and with v1's sentence. Same pixels, same state,
same noise seed -> any difference in the chunk comes from the words alone.

  * |lateral end diff| PRED vs DEMO: how much the words move the predicted path,
    against how much the two demos actually diverge 3 s later.
  * toward-target: the predicted lateral end lies on the instructed target's
    side (sign of its bearing) — only pairs whose targets are on opposite sides.

    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py \
        runs/course/navvla_reasoning_r50/checkpoints/020000/pretrained_model data/course/packed_goto --n 60
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


def chunk(policy, pre, post, cam, img_path, state, task):
    img = np.asarray(Image.open(img_path).convert("RGB"))
    t = (torch.from_numpy(img).permute(2, 0, 1).float() / 255.0).unsqueeze(0)
    want = policy.config.input_features["observation.state"].shape[0]
    st = list(state) + ([0.0] if want == len(state) + 1 else [])
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


ap = argparse.ArgumentParser()
ap.add_argument("checkpoint"); ap.add_argument("packed"); ap.add_argument("--n", type=int, default=60)
ap.add_argument("--k", type=int, default=3, help="frame index (same start pose -> near-identical images)")
# 2026-10-04 (r52 closed loop = sentence-blind): amplify the words' effect.
# chunk = null + w * (cond - null), same noise seed, null = a side-free sentence.
ap.add_argument("--guide", type=float, nargs="*", default=[1.0], help="guidance weights w")
ap.add_argument("--null", default="Go to the object.", help="side-free sentence for guidance")
# 2026-10-09 (조합 일반화 홀드아웃): v3/v3y 는 cf_axis="lane" 이고 goto 슬롯이 없다.
# --slot 은 짝의 BOTH 멤버가 만족해야 하는 intent_slots/meta 조건이다. cf_axis=lane 인 짝에서는
# lane 만 변이하므로 speed_level·intent_id 로 홀드아웃 칸(예: ring_goal x fast)만 고를 수 있다.
ap.add_argument("--dump", default="", help="write per-pair rows as JSONL (for paired tests across checkpoints)")
ap.add_argument("--slot", action="append", default=[], metavar="KEY=VAL",
                help="filter pairs by intent_slots[KEY]==VAL (or meta[KEY]); repeatable")
a = ap.parse_args()
rng = random.Random(20261004)
groups = {}
for d in sorted(os.listdir(a.packed)):
    ep = os.path.join(a.packed, d)
    if not os.path.isdir(ep): continue
    m = json.load(open(os.path.join(ep, "meta.json")))
    groups.setdefault(m.get("cf_group_id"), {})[m.get("cf_variant_id")] = (ep, m)
def _pick_pair(g):
    """Two variants of one group to compare.

    2026-10-07: sector groups carry THREE variants (left / ahead / right), so
    a fixed v0,v1 pair lands on a random pair — sometimes ahead-vs-left, whose
    chance baseline is not 50%. Pick the opposite-side pair (largest signed
    bearing gap) when one exists, which is the left-vs-right discrimination,
    and fall back to v0,v1 for the two-variant corpora.
    """
    vs = [v for v in g.values()]
    if len(vs) < 2:
        return None
    best, gap = None, -1.0
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            try:
                gi = vs[i][1]["intent_slots"]["goto"]
                gj = vs[j][1]["intent_slots"]["goto"]
                bi = gi["objects"][gi["target"]]["bearing"]
                bj = gj["objects"][gj["target"]]["bearing"]
            except Exception:                     # noqa: BLE001
                continue
            if bi * bj < 0 and abs(bi - bj) > gap:
                best, gap = (vs[i], vs[j]), abs(bi - bj)
    if best:
        return best
    return (g["v0"], g["v1"]) if "v0" in g and "v1" in g else None


SLOTS = [kv.split("=", 1) for kv in a.slot]


def _slot_ok(m):
    sl = m.get("intent_slots") or {}
    for k, v in SLOTS:
        got = sl.get(k, m.get(k))
        if str(got) != v:
            return False
    return True


pairs = [q for q in (_pick_pair(g) for g in groups.values()) if q]
if SLOTS:
    n_all = len(pairs)
    pairs = [q for q in pairs if _slot_ok(q[0][1]) and _slot_ok(q[1][1])]
    print(f"[slot] {' '.join(a.slot)} -> pairs {len(pairs)}/{n_all}")
rng.shuffle(pairs)
p, pre, post, cam = load(a.checkpoint)
res = {"goto_target": [], "goto_mode": [], "goto_sector": [], "lane": []}
for (ep0, m0), (ep1, m1) in pairs:
    axis = m1.get("cf_axis") or m0.get("cf_axis")
    if axis not in res or len(res[axis]) >= a.n: continue
    r0 = [json.loads(l) for l in open(os.path.join(ep0, "resampled_10hz.jsonl"))]
    r1 = [json.loads(l) for l in open(os.path.join(ep1, "resampled_10hz.jsonl"))]
    k = min(a.k, len(r0) - 1, len(r1) - 1)
    img, state = os.path.join(ep0, r0[k]["frame"]), r0[k]["state"]
    c0 = chunk(p, pre, post, cam, img, state, m0["instruction"])
    c1 = chunk(p, pre, post, cam, img, state, m1["instruction"])
    cn = chunk(p, pre, post, cam, img, state, a.null) if a.guide != [1.0] else c0
    gy = {w: (lat_end(cn + w * (c0 - cn)), lat_end(cn + w * (c1 - cn))) for w in a.guide}
    y0, y1 = gy[a.guide[0]]
    try:
        g0, g1 = m0["intent_slots"]["goto"], m1["intent_slots"]["goto"]
        b0 = g0["objects"][g0["target"]]["bearing"]; b1 = g1["objects"][g1["target"]]["bearing"]
    except KeyError:        # cf_axis="lane" (v3/v3y) 는 goto 슬롯이 없다
        b0 = b1 = 0.0
    res[axis].append(dict(key=os.path.basename(ep0.rstrip("/")), gy=gy, yn=lat_end(cn), pred=abs(y1 - y0), demo=abs(demo_lat(r1, k) - demo_lat(r0, k)),
                          y0=y0, y1=y1, b0=b0, b1=b1, s0=m0["instruction"], s1=m1["instruction"]))
    if all(len(v) >= a.n for v in res.values()): break

print(f"[{'/'.join(a.checkpoint.split('/')[2:5])}] same frame k={a.k} + same state, instruction swapped")
for axis, rs in res.items():
    if not rs: continue
    pr, de = np.mean([r["pred"] for r in rs]), np.mean([r["demo"] for r in rs])
    print(f"  {axis:11s} n={len(rs):3d}  |lateral end diff| PRED {pr:.3f} m  vs DEMO {de:.3f} m  (ratio {pr / max(de, 1e-3):.2f})")
    if axis in ("goto_target", "goto_sector"):
        opp = [r for r in rs if r["b0"] * r["b1"] < 0 and min(abs(r["b0"]), abs(r["b1"])) > 0.12]
        ok = sum((r["y1"] - r["y0"]) * (r["b1"] - r["b0"]) > 0 for r in opp)
        print(f"    opposite-side targets n={len(opp)}: predicted shift toward the instructed side {ok}/{len(opp)} (chance 50%)")
        if a.guide != [1.0]:
            for w in a.guide:
                d = np.mean([abs(r["gy"][w][1] - r["gy"][w][0]) for r in rs])
                okw = sum((r["gy"][w][1] - r["gy"][w][0]) * (r["b1"] - r["b0"]) > 0 for r in opp)
                # each sentence alone: lateral end on its own target's side
                own = sum(sum((r["gy"][w][i] - r["yn"]) * r[f"b{i}"] > 0 for i in (0, 1)) for r in opp)
                print(f"    guide w={w:<4} |diff| {d:.3f} m (ratio {d / max(de, 1e-3):.2f})  toward {okw}/{len(opp)}"
                      f"  each-vs-null own side {own}/{2 * len(opp)}")
    for r in rs[:4]:
        print(f"    {r['s0'][:34]:34s} y {r['y0']:+.2f} | {r['s1'][:34]:34s} y {r['y1']:+.2f}")

if a.dump:
    with open(a.dump, "w") as f:
        for axis, rs in res.items():
            for r in rs:
                f.write(json.dumps({"axis": axis, "key": r["key"], "pred": float(r["pred"]), "demo": float(r["demo"]),
                                    "y0": float(r["y0"]), "y1": float(r["y1"])}) + "\n")
    print(f"[dump] {a.dump}: {sum(len(v) for v in res.values())} rows")

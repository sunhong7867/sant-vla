#!/usr/bin/env python3
"""Counterfactual action labels for go-to-object (2026-10-05).

r50-r54: the demos need the sentence only for the first 1-2 s; after that the
image alone predicts the action, so the policy never had to read the words
(noun swap 21/42 = chance; direction words moved the chunk 0.1x the demo
spread). Here every sampled demo frame k also gets, for each OTHER object j
in view, the chunk the same teacher would drive toward j from that pose
(goto_kinematic.rollout, G-kin 3 s end error median 0.13-0.17 m) with j's
name as the sentence: same pixels + different name -> different action, at
every phase of the approach. Coordinates are used only here; the policy still
sees image + sentence + state.

Skipped: j outside +-27 deg, j closer than its standoff + 1 m, or the arc to
j's stop point passing within r + 1.9 m of another object (no labels that
drive through things). The narration is about the real target, so the trainer
zeroes the reasoning CE on these rows.

    python3 code/course/make_cf_sidecar.py data/course/lerobot/g4 data/course/packed_goto --every 5
"""
import argparse, json, math, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import goto_kinematic as K                     # noqa: E402
import goto_layout as G                        # noqa: E402  (copy of src/sant_vla_pkg/sant_vla_pkg/goto_layout.py)

HALF_FOV = math.radians(27.0)


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset"); ap.add_argument("packed", nargs="+")
    ap.add_argument("--every", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rng = random.Random(20261005)
    out_path = a.out or os.path.join(a.dataset, "cf_sidecar.jsonl")
    dirs = {}
    for p in a.packed:
        for d in os.listdir(p):
            dirs.setdefault(d, os.path.join(p, d))
    n_rows = n_ep = n_skip_fov = n_skip_near = n_skip_block = 0
    with open(out_path, "w") as out:
        for line in open(os.path.join(a.dataset, "nav_vla_index.jsonl")):
            r = json.loads(line)
            if r.get("intent_id") != "goto_object":
                continue
            d = dirs.get(r["packed_episode"])
            if d is None:
                continue
            m = json.load(open(os.path.join(d, "meta.json")))
            g = m["intent_slots"]["goto"]
            if g.get("mode") != "direct":
                continue
            objs, ti = g["objects"], g["target"]
            v = m["intent_slots"]["target_speed"]
            rows = [json.loads(l) for l in open(os.path.join(d, "resampled_10hz.jsonl"))]
            rows = [x for x in rows if isinstance(x.get("action"), list) and len(x["action"]) == 3]
            n_ep += 1
            t = objs[ti]
            for k in range(0, len(rows), a.every):
                x, y, h, s = rows[k]["x"], rows[k]["y"], rows[k]["heading"], rows[k]["state"][0]
                # stop sampling once the car is braking into the real target
                if math.hypot(t["x"] - x, t["y"] - y) - g["standoff_m"] < 1.0:
                    break
                for j, o in enumerate(objs):
                    if j == ti:
                        continue
                    b = wrap(math.atan2(o["y"] - y, o["x"] - x) - h)
                    dist = math.hypot(o["x"] - x, o["y"] - y)
                    sd = G.standoff(o["model"])
                    if abs(b) > HALF_FOV:
                        n_skip_fov += 1; continue
                    if dist < sd + 1.0:
                        n_skip_near += 1; continue
                    sx, sy = o["x"] - (o["x"] - x) / dist * sd, o["y"] - (o["y"] - y) / dist * sd
                    arc = G.arc_points(x, y, h, sx, sy)
                    if not all(min(math.hypot(q["x"] - px, q["y"] - py) for px, py in arc) > q["r"] + 1.9
                               for q_i, q in enumerate(objs) if q_i != j):
                        n_skip_block += 1; continue
                    ch = K.rollout(x, y, h, s, o["x"], o["y"], sd, v)
                    text = G.render("direct", o["model"], rng)[0]
                    out.write(json.dumps({"ep": r["lerobot_episode_index"], "frame": k, "task": text,
                                          "target": o["noun"],
                                          "action": [[round(c, 5) for c in st] for st in ch]},
                                         ensure_ascii=False) + "\n")
                    n_rows += 1
    print(f"cf rows {n_rows} over {n_ep} goto episodes -> {out_path}  "
          f"(skipped: out of view {n_skip_fov}, too near {n_skip_near}, path blocked {n_skip_block})")


if __name__ == "__main__":
    main()

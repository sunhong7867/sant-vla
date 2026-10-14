#!/usr/bin/env python3
"""Side-free copies of positional goto episodes (2026-10-04, r53).

r52 follows the direction words offline (34/42) but the chunk moves only 0.31x
the demo spread; amplifying cond - null by w=3 matches the demo, and the
policy server can do that at run time (vla_policy_server --guide). For the
null to be a real "no side" condition, the policy must have SEEN it: a share
of the episodes is copied with the side removed from the sentence —
"Go to the object." / "Follow the lane to the object." — so the null learns
the average go-to motion over sides (classifier-free guidance style dropout).

    python3 code/course/add_null_goto.py data/course/packed_goto_pos data/course/packed_goto_null --share 0.25
"""
import argparse, json, os, random

NULL_DIRECT, NULL_LANE = "Go to the object.", "Follow the lane to the object."

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst"); ap.add_argument("--share", type=float, default=0.25)
a = ap.parse_args()
rng = random.Random(20261005)
os.makedirs(a.dst, exist_ok=True)
rows = [json.loads(l) for l in open(os.path.join(a.src, "index.jsonl"))]
pick = rng.sample(rows, round(len(rows) * a.share))
out = open(os.path.join(a.dst, "index.jsonl"), "w")
for r in pick:
    sd = os.path.join(a.src, r["episode"])
    name = r["episode"] + "_null"
    dd = os.path.join(a.dst, name)
    os.makedirs(dd, exist_ok=True)
    for f in os.listdir(sd):
        if f != "meta.json" and not os.path.exists(os.path.join(dd, f)):
            os.symlink(os.path.realpath(os.path.join(sd, f)), os.path.join(dd, f))
    m = json.load(open(os.path.join(sd, "meta.json")))
    lane = m["intent_slots"]["goto"].get("mode") == "lane"
    m["instruction"] = NULL_LANE if lane else NULL_DIRECT
    m["cf_group_id"] = None; m["cf_variant_id"] = None
    if "episode_id" in m: m["episode_id"] = str(m["episode_id"]) + "_null"
    json.dump(m, open(os.path.join(dd, "meta.json"), "w"), ensure_ascii=False)
    r = dict(r, episode=name, instruction=m["instruction"], cf_group_id=None, cf_variant_id=None)
    out.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"null copies {len(pick)} -> {a.dst}")

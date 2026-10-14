#!/usr/bin/env python3
"""Positional relabel of the go-to-object corpus (2026-10-04, r52).

r50/r51 probe: with the frame and state fixed, swapping the target NOUN does not
move SmolVLA's predicted path toward the named object (20-21/42 opposite-side
pairs, chance 50 %), matching G0 (SmolVLM2-500M picks the named object's
side at chance, 10/26). So the end-to-end policy is given what it CAN ground —
a direction word, like the lane words r26 learned — and naming becomes the
System-2 (Qwen2.5-VL) job: "Go to the dinosaur" -> "Go to the object on the left."

Same episodes, same frames, same narration; only meta.json's instruction changes.
The side comes from the target's bearing at the start (+ = left, |b| < 10 deg =
straight ahead); if another object shares that side, nearer / farther is added.

    python3 code/course/relabel_goto_pos.py data/course/packed_goto data/course/packed_goto_pos
"""
import json, math, os, random, sys

SIDE_DEG = 10.0
EN_DIRECT = ["Go to {p}.", "Drive to {p} and stop.", "Head for {p}.", "Stop in front of {p}.",
             "Drive up to {p}.", "Take me to {p}."]
EN_LANE = ["Follow the lane to {p}.", "Keep to the lane and stop at {p}.",
           "Drive along the lane until {p}."]
KO_DIRECT = ["{k}로 가.", "{k} 앞에 세워 줘."]
KO_LANE = ["차선 따라 {k}로 가."]
SIDE_EN = {"left": "on the left", "right": "on the right", "ahead": "straight ahead"}
SIDE_KO = {"left": "왼쪽", "right": "오른쪽", "ahead": "정면"}


def side(b):
    d = math.degrees(b)
    return "left" if d > SIDE_DEG else "right" if d < -SIDE_DEG else "ahead"


def phrase(objs, ti):
    t = objs[ti]
    s = side(t["bearing"])
    same = [o for o in objs if side(o["bearing"]) == s]
    rank = ""
    if len(same) > 1:
        rank = "nearer" if t["dist"] <= min(o["dist"] for o in same) else "farther"
    en = f"the {rank + ' ' if rank else ''}object {SIDE_EN[s]}"
    ko = f"{SIDE_KO[s]} {({'nearer': '가까운 ', 'farther': '먼 '}).get(rank, '')}물체"
    return en, ko, s, rank


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    rng = random.Random(20261004)
    idx_out = open(os.path.join(dst, "index.jsonl"), "w")
    n = 0
    stats = {}
    for line in open(os.path.join(src, "index.jsonl")):
        r = json.loads(line)
        sd = os.path.join(src, r["episode"])
        m = json.load(open(os.path.join(sd, "meta.json")))
        g = m["intent_slots"]["goto"]
        en, ko, s, rank = phrase(g["objects"], g["target"])
        lane = g.get("mode") == "lane"
        if rng.random() < 0.2:
            sent = rng.choice(KO_LANE if lane else KO_DIRECT).format(k=ko)
        else:
            sent = rng.choice(EN_LANE if lane else EN_DIRECT).format(p=en)
        dd = os.path.join(dst, r["episode"])
        os.makedirs(dd, exist_ok=True)
        for f in os.listdir(sd):
            if f != "meta.json" and not os.path.exists(os.path.join(dd, f)):
                os.symlink(os.path.abspath(os.path.join(sd, f)), os.path.join(dd, f))
        m["instruction_noun"] = m["instruction"]
        m["instruction"] = sent
        g["position_words"] = {"side": s, "rank": rank}
        json.dump(m, open(os.path.join(dd, "meta.json"), "w"), ensure_ascii=False)
        r["instruction"] = sent
        idx_out.write(json.dumps(r, ensure_ascii=False) + "\n")
        key = f"{'lane' if lane else 'direct'}:{s}{'/' + rank if rank else ''}"
        stats[key] = stats.get(key, 0) + 1
        n += 1
    print(f"relabelled {n} episodes -> {dst}")
    print(json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

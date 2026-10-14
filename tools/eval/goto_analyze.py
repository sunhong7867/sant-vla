#!/usr/bin/env python3
"""Summarise goto_trial.py results (2026-10-03): success / right-object rate
with Wilson 95 % intervals against the chance rate (1 / objects in view);
T2 compares the lane deviation of 'go straight' vs 'follow the lane'.

  python3 tools/eval/goto_analyze.py eval_out/course/goto_eval r50_010000
"""
import glob
import json
import math
import os
import statistics
import sys


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, c - h), min(1.0, c + h)


def main():
    d, prefix = sys.argv[1], sys.argv[2]
    print(f"== {prefix}")
    for f in sorted(glob.glob(os.path.join(d, f"{prefix}_T*.jsonl")) + glob.glob(os.path.join(d, f"{prefix}_E*.jsonl"))
                    + glob.glob(os.path.join(d, f"{prefix}_S*.jsonl"))):
        tier = f[len(os.path.join(d, prefix)) + 1:-6]
        rows = [json.loads(l) for l in open(f) if l.strip()]
        if not rows:
            continue
        n = len(rows)
        ks = sum(r["success"] for r in rows)
        kc = sum(r["chosen_right"] for r in rows)
        chance = statistics.mean(1.0 / r["n_obj"] for r in rows)
        p, lo, hi = wilson(ks, n)
        q, qlo, qhi = wilson(kc, n)
        res = {}
        for r in rows:
            res[r["result"]] = res.get(r["result"], 0) + 1
        # 2026-10-08: the DEMO needs one scene in which the three commands reach
        # three different objects; the per-trial rate does not say that and is
        # contaminated by COLLISION terminations (`chosen` is whatever object the
        # car ended up beside). Lead with the per-scene number, keep the rate as
        # a secondary line. Also surface the serving health that `goto_trial.py`
        # now stamps — a watchdog hit is fatal to a run's validity.
        sets_all = {}
        for r in rows:
            if r.get("set") is not None:
                sets_all.setdefault(r["set"], []).append(r)
        full_sets = [v for v in sets_all.values() if len(v) >= 3]
        if full_sets:
            distinct = sum(len({x["chosen"] for x in v}) == len(v) for v in full_sets)
            allright = sum(all(x["chosen_right"] for x in v) for v in full_sets)
            print(f"{tier:8s} n={n:3d}  SCENES {len(full_sets)}: "
                  f"three commands -> three different objects {distinct}, "
                  f"all three right {allright}   <-- demo criterion")
        hb = [r["serving"] for r in rows if r.get("serving")]
        if hb:
            wdt = sum(h.get("watchdog_delta", 0) for h in hb)
            bad = sum(1 for h in hb if h.get("watchdog_delta", 0) > 0)
            lats = [h["lat_p90_ms"] for h in hb if h.get("lat_p90_ms")]
            print(f"         serving: watchdog hits {wdt} over {bad} trial(s), "
                  f"underrun max {max(h.get('underrun_max', 0) for h in hb):.0f}%, "
                  f"lat p90 median {statistics.median(lats):.0f} ms" if lats else "")
        cfg = next((r["cfg"] for r in rows if r.get("cfg")), None)
        if cfg:
            print(f"         cfg: guide={cfg.get('policy_guide')} seed={cfg.get('seed')} "
                  f"words={cfg.get('words')} ckpt={str(cfg.get('ckpt'))[-40:]}")
        print(f"{tier:8s} n={n:3d}  success {ks:3d} = {p:5.1%} [{lo:5.1%}, {hi:5.1%}]  "
              f"ended nearest the target {kc:3d} = {q:5.1%} [{qlo:5.1%}, {qhi:5.1%}]  "
              f"chance {chance:4.0%}  results {res}")
        if tier.startswith("T2"):
            for mode in ("direct", "lane"):
                dv = [r["lane_dev_max"] for r in rows if r["mode"] == mode and r.get("lane_dev_max") is not None]
                if dv:
                    print(f"      {mode:6s} max lane deviation median {statistics.median(dv):.2f} m "
                          f"(n={len(dv)}, >1.5 m: {sum(x > 1.5 for x in dv)})")
        if tier.startswith("S") and "success_strict" in rows[0]:
            # strict = right object + bumper gap 0.6-1.8 m + no contact
            k = sum(r["success_strict"] for r in rows)
            p2, lo2, hi2 = wilson(k, n)
            coll = sum(r["result"] == "COLLISION" for r in rows)
            gaps = [r["gap"] for r in rows if r["chosen_right"] and r["result"] == "STOPPED"]
            sets = {}
            for r in rows:
                sets.setdefault(r["set"], []).append(r)
            # SEC (2026-10-07) is a three-variant set like S3 but its name
            # has no digit — int(tier[1]) raised ValueError on it.
            k_set = 3 if tier.startswith("SEC") else int(tier[1])
            full = [v for v in sets.values() if len(v) == k_set]
            distinct = sum(len({r["chosen"] for r in v}) == len(v) for v in full)
            allright = sum(all(r["chosen_right"] for r in v) for v in full)
            print(f"      STRICT success {k}/{n} = {p2:5.1%} [{lo2:5.1%}, {hi2:5.1%}]  collisions {coll}  "
                  f"gap median {statistics.median(gaps) if gaps else float('nan'):.2f} m (right-object stops n={len(gaps)})")
            print(f"      sets {len(full)}: every sentence a different object {distinct}, all right {allright}")
        if tier.startswith("E") and not tier.startswith("SEC"):
            # consecutive rows = the same scene with "left" / "right"
            pr = [(rows[i], rows[i + 1]) for i in range(0, n - 1, 2)]
            both = sum(a["chosen_right"] and b["chosen_right"] for a, b in pr)
            diff = sum(a["chosen"] != b["chosen"] for a, b in pr)
            sep = [math.hypot(a["path"][-1][0] - b["path"][-1][0], a["path"][-1][1] - b["path"][-1][1])
                   for a, b in pr if a.get("path") and b.get("path")]
            print(f"      pairs {len(pr)}: both sentences right {both}  (chance 25%), "
                  f"ended at different objects {diff}, end-point gap median "
                  f"{statistics.median(sep) if sep else float('nan'):.2f} m")
        if tier.startswith("T4") and any(r.get("rewrite") for r in rows):
            names = [r["rewrite"]["to"] for r in rows if r.get("rewrite")]
            print(f"      rewrites: " + ", ".join(sorted(set(names)))[:200])


if __name__ == "__main__":
    main()

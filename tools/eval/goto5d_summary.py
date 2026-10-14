#!/usr/bin/env python3
"""Summarise point-goal trials (P2 / P3a / P3b jsonl from goto_trial.py --goal-mode rel|zero).

  python3 tools/eval/goto5d_summary.py eval_out/course/goto_eval/g5d_015000_P2.jsonl [...]

Per file and per arm: n, success, STOPPED/COLLISION/TIMEOUT counts, gate fired, median
speed at the gate, median final distance to the goal, touched-target count. Pre-registered
lines (docs/experiments/goto_object/20261012_1850): P2 main >= 14/20, P2 alt >= 14/20,
P2 zero floor < 10/20, P3a >= 14/20, P3b >= 14/20.
"""
import json
import statistics as st
import sys
from collections import Counter, defaultdict


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(st.median(xs), 2) if xs else None


def main(files):
    for f in files:
        rows = [json.loads(l) for l in open(f) if l.strip()]
        if not rows:
            print(f, "empty"); continue
        tier, mode = rows[0].get("tier"), rows[0].get("goal_mode")
        print(f"\n== {f}  tier={tier} goal_mode={mode} n={len(rows)}")
        by = defaultdict(list)
        for r in rows:
            by[r.get("arm") or "-"].append(r)
        for arm, rs in sorted(by.items()):
            res = Counter(r["result"] for r in rs)
            ok = sum(1 for r in rs if r["success"])
            print(f"  arm {arm:8s} n={len(rs):3d} success {ok}/{len(rs)}  "
                  f"results {dict(res)}  gate_fired {sum(1 for r in rs if r.get('gate_fired'))}  "
                  f"v_at_gate med {med([r.get('v_at_gate') for r in rs])}  "
                  f"fin_goal_d med {med([r.get('fin_goal_d') for r in rs])}  "
                  f"touched {sum(1 for r in rs if r.get('touched_target'))}")
            if tier == "P3a":
                print(f"           crossed {sum(1 for r in rs if r.get('crossed'))}  "
                      f"along med {med([r.get('along') for r in rs])}  |lat| med "
                      f"{med([abs(r['lat']) for r in rs if r.get('lat') is not None])}")
            if tier == "P3b":
                print(f"           lat_obj med {med([r.get('lat_obj') for r in rs])}  "
                      f"d_obj med {med([r.get('d_obj') for r in rs])}")
            if tier == "P2":
                print(f"           chosen_right {sum(1 for r in rs if r.get('chosen_right'))}  "
                      f"strict {sum(1 for r in rs if r.get('success_strict'))}")
        sv = [r.get("serving") for r in rows if r.get("serving")]
        if sv:
            print(f"  serving: watchdog_delta sum {sum(s['watchdog_delta'] for s in sv)}  "
                  f"underrun_max {max(s['underrun_max'] for s in sv)}  "
                  f"lat_p90 med {med([s['lat_p90_ms'] for s in sv])}")


if __name__ == "__main__":
    main(sys.argv[1:])

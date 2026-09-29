#!/usr/bin/env python3
"""v1 (swerve) demo quality on REAL packed episodes (2026-09-29).

Per v1 episode: largest steering change between 10 Hz frames, peak |steer|,
and body clearance with the evaluator's geometry (tools/eval/avoidance_trial.py
hit_geometric: ego-heading frame, EGO 2.4 x 0.95 half-extents). The first 3 s
are skipped: Stanley saturates the steering at standstill, which is not the
swerve.

    python3 tools/eval/swerve_demo_quality.py \\
        src/sant_vla_pkg/data_course_multiobj/packed_swerve \\
        src/sant_vla_pkg/data_course_multiobj/packed_ramppilot
"""
import json, math, os, sys
EGO_L, EGO_W = 2.4, 0.95
EXT = {"ob_box": (0.85, 0.85), "ob_barrel": (0.5, 0.5), "ob_cone": (0.6, 0.6),
       "ob_barrier": (0.3, 1.2), "ob_person": (0.3, 0.3)}
CAR_EXT = (2.2, 0.9)


def stats(ep):
    m = json.load(open(os.path.join(ep, "meta.json")))
    if m.get("cf_variant_id") != "v1":
        return None
    ob = m["intent_slots"]["obstacle"]
    ext = EXT.get(ob["model"], CAR_EXT)
    rows = [json.loads(l) for l in open(os.path.join(ep, "resampled_10hz.jsonl"))]
    marg, win = 9.9, []
    for k, r in enumerate(rows):
        h = r["heading"]
        dx, dy = ob["x"] - r["x"], ob["y"] - r["y"]
        along = dx * math.cos(h) + dy * math.sin(h)
        across = -dx * math.sin(h) + dy * math.cos(h)
        if abs(along) < EGO_L + ext[0]:
            marg = min(marg, abs(across) - (EGO_W + ext[1]))
        if -8 < along < 14 and k >= 30:
            win.append(k)
    st = [rows[k]["state"][2] for k in win]
    step = max(abs(st[i] - st[i - 1]) for i in range(1, len(st)))
    return ob["model"], m["intent_slots"]["target_speed"], step, max(map(abs, st)), marg


for base in sys.argv[1:]:
    print("==", base)
    out = [s for d in sorted(os.listdir(base)) if os.path.isdir(os.path.join(base, d))
           for s in [stats(os.path.join(base, d))] if s]
    for s in out:
        print("  %-15s v %.2f  steer step/0.1s %.2f  |steer|max %.2f  margin %+.2f" % s)
    if out:
        print("  mean step %.2f  mean peak %.2f  min margin %+.2f  overlaps %d/%d" % (
            sum(s[2] for s in out) / len(out), sum(s[3] for s in out) / len(out),
            min(s[4] for s in out), sum(s[4] < 0 for s in out), len(out)))

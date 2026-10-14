#!/usr/bin/env python3
"""Closed-loop swerve trace vs served situation phrase (2026-09-30).

For each avoidance_trial log (TRACE line), print the ego's signed lane offset
at fixed distances to the obstacle, with the situation phrase the server had
last decoded at that moment (server log rows carry "t", same wall clock).

    scp autolab_sw@115.145.211.157:~/sunhong/nav-vla/logs/situation_serve.jsonl /tmp/sit.jsonl
    python3 tools/eval/trace_view.py --situation /tmp/sit.jsonl \\
        eval_out/course/multiobj_eval/trials/r40_base_ob_box_*.log
"""
import argparse, bisect, json

ap = argparse.ArgumentParser()
ap.add_argument("logs", nargs="+")
ap.add_argument("--situation", default=None, help="server situation_serve.jsonl")
ap.add_argument("--marks", default="22,20,18,16,14,12,10,8,6,4,3")
a = ap.parse_args()
marks = [float(m) for m in a.marks.split(",")]

sit_t, sit_p = [], []
if a.situation:
    for l in open(a.situation):
        r = json.loads(l)
        if "t" in r:
            sit_t.append(r["t"])
            sit_p.append((r.get("situation") or "")[11:].split(" ")[0] or "-")


def phrase_at(t):
    i = bisect.bisect_right(sit_t, t) - 1
    return sit_p[i] if i >= 0 else "?"


SHORT = {"road": "clear", "obstacle": "AHEAD", "passing": "pass", "past": "past"}
for path in a.logs:
    trace, result = None, ""
    for line in open(path, errors="replace"):
        if line.startswith("TRACE "):
            trace = json.loads(line[6:])
        if '"result"' in line:
            result = line.split(":")[1].strip().strip('",')
    print(f"== {path.split('/')[-1]}  {result}")
    if not trace:
        print("   (no TRACE line — trial predates tracing)"); continue
    # first sample at or inside each mark while approaching (d decreasing)
    dmin_i = min(range(len(trace)), key=lambda k: trace[k][1])
    row = []
    for m in marks:
        k = next((k for k in range(dmin_i + 1) if trace[k][1] <= m), None)
        if k is None:
            row.append(f"{m:>4.0f}m    -    ")
            continue
        t, d, lat = trace[k][:3]
        if len(trace[k]) > 3:          # oracle phrase recorded by the harness
            ph = trace[k][3]
        else:
            ph = SHORT.get(phrase_at(t), phrase_at(t)) if sit_t else ""
        row.append(f"{m:>4.0f}m {lat:+.2f} {ph:5s}")
    for i in range(0, len(row), 4):
        print("   " + "  ".join(row[i:i + 4]))
    t, d, lat = trace[dmin_i][:3]
    print(f"   closest d={d:.2f} lat={lat:+.2f}   max lat on approach "
          f"{max(x[2] for x in trace[:dmin_i + 1]):+.2f}")

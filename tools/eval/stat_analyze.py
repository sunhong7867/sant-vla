#!/usr/bin/env python3
"""Analyse a stat_eval.sh run (2026-10-01): random positions x {ours, adj, empty}.

    python3 tools/eval/stat_analyze.py sw80

Per condition: rates with Wilson 95% intervals. Per position (paired):
max lateral offset on approach, ours - empty, i.e. how much more the policy
moves aside when the box is really there than it does at the same spot on an
empty road. "Lane change" = max offset on approach > half a lane (1.575 m).
"""
import glob, json, math, os, re, statistics, sys

RUN = sys.argv[1]
WS = "/home/sh/ROS2_project/sant-vla"
D = f"{WS}/eval_out/course/multiobj_eval"
HALF_LANE = 1.575


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, c - h), min(1.0, c + h)


def trace_of(path):
    tr = None
    try:
        for line in open(path, errors="replace"):
            if line.startswith("TRACE "):
                tr = json.loads(line[6:])
    except OSError:
        pass
    return tr


rows = {}   # cond -> frac -> row
for f in sorted(glob.glob(f"{D}/{RUN}_st_*_b*.jsonl")):
    cond = re.search(r"_st_(\w+?)_b\d+\.jsonl$", f).group(1)
    tag = os.path.basename(f)[:-6]
    # lane1-start conditions (ours1/adj1/...) swerve RIGHT into lane2: the
    # signed offset goes negative, so flip it to keep "max = toward the pass"
    sg = -1.0 if cond.endswith("1") else 1.0
    for line in open(f):
        r = json.loads(line)
        frac = r["spot"].split(":")[1]
        tr = trace_of(f"{D}/trials/{tag}_{r['model']}_{r['spot'].replace(':', '_')}_{r['trial']}.log")
        if tr:
            k = min(range(len(tr)), key=lambda i: tr[i][1])
            r["max_lat"] = max(sg * x[2] for x in tr[:k + 1])
            # signed offset when the (real or virtual) obstacle centre is 6 m away
            r["lat6"] = next((sg * x[2] for x in tr[:k + 1] if x[1] <= 6.0), None)
        if r.get("max_lat") is None and r.get("lat_at_min") is not None:
            # trial logs pruned (cleanup_artifacts KEEP_TRIALS): fall back to the
            # offset at closest approach, recorded in the jsonl row itself
            r["max_lat"] = sg * r["lat_at_min"]
            r["from_jsonl"] = True
        rows.setdefault(cond, {})[frac] = r

print(f"== {RUN}: positions per condition " + ", ".join(f"{c} {len(v)}" for c, v in rows.items()))
valid = lambda r: r.get("result") in ("SUCCESS", "COLLISION", "STUCK", "OFF_TRACK", "TIMEOUT")
for cond, want in (("ours", "회피 성공 (SUCCESS)"), ("adj", "충돌 없음 (SUCCESS)"), ("empty", "완주"),
                   ("held", "미학습 사람 회피"), ("heldcar", "미학습 초록 차 회피"),
                   ("ours1", "1차선 출발 회피"), ("adj1", "1차선 출발 옆 차선"),
                   ("empty1", "1차선 출발 빈 차선"), ("held1", "1차선 출발 미학습 사람")):
    rs = [r for r in rows.get(cond, {}).values() if valid(r)]
    if not rs:
        continue
    k = sum(r["result"] == "SUCCESS" for r in rs)
    p, lo, hi = wilson(k, len(rs))
    lc = [r for r in rs if r.get("max_lat") is not None]
    kc = sum(r["max_lat"] > HALF_LANE for r in lc)
    q, qlo, qhi = wilson(kc, len(lc))
    other = {x: sum(r["result"] == x for r in rs) for x in ("COLLISION", "STUCK", "OFF_TRACK", "TIMEOUT")}
    print(f"{cond:5s} {want:18s} {k:3d}/{len(rs):3d} = {p:5.1%} [{lo:5.1%}, {hi:5.1%}]  "
          f"차선 변경 {kc}/{len(lc)} = {q:5.1%} [{qlo:5.1%}, {qhi:5.1%}]  "
          f"최대 오프셋 중앙값 {statistics.median(r['max_lat'] for r in lc):+.2f}  기타 {other}")

ours, emp, adj = rows.get("ours", {}), rows.get("empty", {}), rows.get("adj", {})


def paired(a, b, key, label):
    common = [f for f in a if f in b and a[f].get(key) is not None and b[f].get(key) is not None]
    if len(common) < 3:
        return
    d = [a[f][key] - b[f][key] for f in common]
    m, s = statistics.mean(d), statistics.stdev(d)
    h = 1.96 * s / math.sqrt(len(d))
    pos = sum(x > 0.3 for x in d)
    print(f"{label:28s} n={len(d):3d}  평균 {m:+.2f} m [{m - h:+.2f}, {m + h:+.2f}]  "
          f"+0.3 m 넘는 위치 {pos}/{len(d)}")


print()
paired(ours, emp, "max_lat", "우리 차선 − 빈 차선 (최대)")
paired(adj, emp, "max_lat", "옆 차선 − 빈 차선 (최대)")
paired(ours, adj, "max_lat", "우리 차선 − 옆 차선 (최대)")
paired(ours, emp, "lat6", "우리 차선 − 빈 차선 (6 m)")
r1 = {c: rows.get(c, {}) for c in ("ours1", "adj1", "empty1", "held1")}
paired(r1["ours1"], r1["empty1"], "max_lat", "1차선: 우리 차선 − 빈 차선 (최대)")
paired(r1["adj1"], r1["empty1"], "max_lat", "1차선: 옆 차선 − 빈 차선 (최대)")
paired(r1["held1"], r1["empty1"], "max_lat", "1차선: 미학습 사람 − 빈 차선 (최대)")
for hc, hl in (("held", "미학습 사람"), ("heldcar", "미학습 초록 차")):
    paired(rows.get(hc, {}), emp, "max_lat", f"{hl} − 빈 차선 (최대)")
    paired(rows.get(hc, {}), ours, "max_lat", f"{hl} − 우리 차선 박스 (최대)")

# avoidance that is not explained by the spot itself
common = [f for f in ours if f in emp and emp[f].get("max_lat") is not None]
if common:
    succ = [f for f in common if ours[f].get("result") == "SUCCESS"]
    habit = [f for f in succ if emp[f]["max_lat"] > HALF_LANE]
    print(f"\n회피 성공 {len(succ)} 곳 중 빈 차선에서도 차선을 바꾼 곳(위치 습관으로 설명됨) {len(habit)}, "
          f"빈 차선에선 안 바꾼 곳(장애물 반응) {len(succ) - len(habit)}  (공통 {len(common)} 곳)")
    if adj:
        both = [f for f in common if f in adj and adj[f].get("max_lat") is not None]
        good = [f for f in both if ours[f].get("result") == "SUCCESS"
                and adj[f]["max_lat"] <= HALF_LANE and emp[f]["max_lat"] <= HALF_LANE]
        print(f"세 조건 모두 맞은 위치(우리 차선 회피 + 옆 차선 유지 + 빈 차선 유지): {len(good)}/{len(both)}")

#!/usr/bin/env python3
"""폐루프 궤적이 '명령한 차선'에 있었는가 — 기하 차선중심 기준.

D_shape 는 '갈렸는가'만 본다. cn 은 같은 문장에도 1.7 m 흔들리므로(c1 0.25 m)
갈림의 상당 부분이 재현 불가능성이다. 여기서는 각 롤아웃이 lane1/lane2 중
어느 쪽 중심선에 붙어 달렸는지를 세어 '맞는 차선'을 직접 판정한다.

사후 분석이다 — 사전 등록한 폐루프 기준은 D_shape 차의 CI 였고 그것은 통과하지 못했다.
"""
import glob, json, math, os, random, statistics as st, sys

REPO = "/home/sh/ROS2_project/sant-vla"
OUT = f"{REPO}/eval_out/course/comp_cl"
P = json.load(open(f"{REPO}/src/sant_vla_pkg/config/track_paths.json"))
L = {1: P["lane1"], 2: P["lane2"]}
SKIP_M = 6.0          # 출발 직후는 두 조건이 같은 자리에서 시작하므로 제외


def lane_of(pt):
    d = {k: min(math.hypot(pt[0] - q[0], pt[1] - q[1]) for q in v) for k, v in L.items()}
    k = min(d, key=d.get)
    return k, d[k]


def occupancy(track):
    """출발 6 m 이후 구간에서 lane2 에 붙어 있던 점의 비율."""
    pts, run = [], 0.0
    for a, b in zip(track, track[1:]):
        run += math.hypot(b[0] - a[0], b[1] - a[1])
        if run >= SKIP_M:
            pts.append(b)
    if len(pts) < 5:
        return None
    lanes = [lane_of(p)[0] for p in pts]
    return sum(1 for x in lanes if x == 2) / len(lanes)


def load(run):
    rows = {}
    for f in sorted(glob.glob(os.path.join(OUT, f"{run}_*.json"))):
        try:
            rs = json.load(open(f))
        except Exception:
            continue
        r = next((x for x in rs if x["case"].startswith("DIFFERENT")), None)
        if not r:
            continue
        oa, ob = occupancy(r["track_a"]), occupancy(r["track_b"])
        if oa is None or ob is None:
            continue
        rows[os.path.basename(f)[len(run) + 1:-5]] = {"a": oa, "b": ob}
    return rows


def boot(d, n=20000, seed=7):
    rng = random.Random(seed)
    N = len(d)
    o = sorted(sum(d[rng.randrange(N)] for _ in range(N)) / N for _ in range(n))
    return st.mean(d), o[int(.025 * n)], o[int(.975 * n)]


runs = sys.argv[1:] or ["c1", "cn"]
R = {r: load(r) for r in runs}
print("A = lane1 문장(분포 내), B = lane2 문장(홀드아웃 칸)")
print("값 = 출발 6 m 이후 구간에서 lane2 중심선에 붙어 있던 비율\n")
for r in runs:
    d = R[r]
    if not d:
        print(f"{r}: 자료 없음"); continue
    a = [v["a"] for v in d.values()]; b = [v["b"] for v in d.values()]
    sep = [v["b"] - v["a"] for v in d.values()]
    m, lo, hi = boot(sep)
    print(f"{r}  짝 {len(d)}")
    print(f"   A(lane1 명령) lane2 점유 {st.mean(a):.2f}   B(lane2 명령) lane2 점유 {st.mean(b):.2f}")
    print(f"   분리도 B-A  {m:+.3f}  95%CI [{lo:+.3f}, {hi:+.3f}]"
          f"   올바른 방향 짝 {sum(1 for x in sep if x > 0)}/{len(sep)}")

if len(runs) == 2:
    keys = sorted(set(R[runs[0]]) & set(R[runs[1]]))
    if keys:
        s1 = [R[runs[0]][k]["b"] - R[runs[0]][k]["a"] for k in keys]
        s2 = [R[runs[1]][k]["b"] - R[runs[1]][k]["a"] for k in keys]
        m, lo, hi = boot([x - y for x, y in zip(s1, s2)])
        print(f"\n공통 짝 {len(keys)}  {runs[0]} 분리도 − {runs[1]} 분리도 = {m:+.3f}"
              f"  95%CI [{lo:+.3f}, {hi:+.3f}]")

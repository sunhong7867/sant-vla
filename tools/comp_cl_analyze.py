#!/usr/bin/env python3
"""조합 일반화 폐루프 분석: 짝(start_pose)별로 c1 과 cn 의 D_shape 를 쌍체 비교.

지표는 오프라인 프로브와 같은 논리다 — "문장만 바꿨을 때 궤적이 갈리는가".
짝마다 SAME 문장 바닥이 같이 측정되므로 D_shape 를 그 바닥으로 나눠서도 본다.
"""
import glob, json, os, random, statistics as st, sys

OUT = "/home/sh/ROS2_project/sant-vla/eval_out/course/comp_cl"


def load(run):
    rows = {}
    for f in sorted(glob.glob(os.path.join(OUT, f"{run}_*.json"))):
        if f.endswith(("_bringup.log", "selected.json")):
            continue
        try:
            rs = json.load(open(f))
        except Exception:
            continue
        gid = os.path.basename(f)[len(run) + 1:-5]
        same = next((r["D_shape_m"] for r in rs if r["case"].startswith("SAME")), None)
        diff = next((r["D_shape_m"] for r in rs if r["case"].startswith("DIFFERENT")), None)
        if diff is None:
            continue
        rows[gid] = {"same": same, "diff": diff}
    return rows


def boot(d, n=20000, seed=7):
    rng = random.Random(seed)
    N = len(d)
    out = sorted(sum(d[rng.randrange(N)] for _ in range(N)) / N for _ in range(n))
    return st.mean(d), out[int(.025 * n)], out[int(.975 * n)]


runs = sys.argv[1:] or ["c1", "cn"]
R = {r: load(r) for r in runs}
for r in runs:
    print(f"{r}: {len(R[r])} 짝")
    if R[r]:
        print(f"   D_shape  평균 {st.mean([v['diff'] for v in R[r].values()]):.3f} m"
              f"  중앙 {st.median([v['diff'] for v in R[r].values()]):.3f} m")
        sm = [v["same"] for v in R[r].values() if v["same"] is not None]
        if sm:
            print(f"   SAME 바닥 평균 {st.mean(sm):.3f} m"
                  f"  ->  배수 {st.mean([v['diff'] for v in R[r].values()]) / max(st.mean(sm), 1e-6):.1f}x")

if len(runs) == 2:
    keys = sorted(set(R[runs[0]]) & set(R[runs[1]]))
    print(f"\n공통 짝 {len(keys)}")
    if keys:
        a = [R[runs[0]][k]["diff"] for k in keys]
        b = [R[runs[1]][k]["diff"] for k in keys]
        d = [x - y for x, y in zip(a, b)]
        m, lo, hi = boot(d)
        w = sum(1 for x in d if x > 0)
        print(f"{runs[0]} 평균 {st.mean(a):.3f} m  vs  {runs[1]} 평균 {st.mean(b):.3f} m")
        print(f"차 {m:+.3f} m  95%CI [{lo:+.3f}, {hi:+.3f}]"
              f"   {runs[0]}>{runs[1]} 인 짝 {w}/{len(keys)}")
        print("판정: CI 가 0 을 제외하면 폐루프에서도 조합 일반화가 언어에 귀속된다.")

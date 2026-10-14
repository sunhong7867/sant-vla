#!/usr/bin/env python3
"""startoff_probe.sh 결과 요약 — 출발 거리별로 빈 차선에서 언제 꺾기 시작하는지.

TRACE 항목 = [wall time, 기준점까지 직선거리 m, 차선 횡 오프셋 m].
"꺾기 시작" = 횡 오프셋이 ONSET_M 을 처음 넘은 시점. 그때의 기준점까지 거리(자리 기준)와
출발 후 이동 거리(= 출발 시 거리 − 그때 거리, 직선 근사; 굽이에서는 실제보다 짧게 나옴)를 같이 낸다.
    python3 tools/eval/startoff_analyze.py r44
"""
import glob
import json
import os
import re
import sys

ONSET_M = 0.8
WS = "/home/sh/ROS2_project/sant-vla"
run = sys.argv[1] if len(sys.argv) > 1 else "r44"
rows = []
for f in sorted(glob.glob(f"{WS}/eval_out/course/startoff/{run}/a*_o*.log")):
    m = re.search(r"a([\d.]+)_o([\d.]+)\.log$", f)
    txt = open(f, encoding="utf-8", errors="replace").read()
    tr = re.search(r"^TRACE (.*)$", txt, re.M)
    res = re.search(r'"result": "(\w+)"', txt)
    if not tr:
        rows.append((m[1], m[2], None, res[1] if res else "NO_REPORT"))
        continue
    pts = json.loads(tr[1])
    rows.append((m[1], m[2], pts, res[1] if res else "?"))

print(f"{'기준점':>7} {'출발(frac)':>9} {'출발 거리':>8} {'결과':>9} {'시작 시 기준점까지':>14} "
      f"{'시작까지 이동':>11} {'최대 횡':>7} {'기준점 10m 앞':>11} {'기준점 통과':>9}")
for a, o, pts, res in rows:
    if not pts:
        print(f"{a:>7} {o:>9} {'-':>8} {res:>9}")
        continue
    d0 = pts[0][1]
    # 기준점에 다가가는 구간만(통과 후 멀어지는 부분 제외)
    k_min = min(range(len(pts)), key=lambda k: pts[k][1])
    app = pts[:k_min + 1]
    onset = next((p for p in app if p[2] > ONSET_M), None)
    lat_max = max(p[2] for p in app)
    lat10 = next((p[2] for p in app if p[1] <= 10.0), float("nan"))
    lat0 = app[-1][2]
    on_d = f"{onset[1]:.1f} m" if onset else "안 꺾음"
    on_tr = f"{d0 - onset[1]:.1f} m" if onset else "-"
    print(f"{a:>7} {o:>9} {d0:7.1f}m {res:>9} {on_d:>14} {on_tr:>11} {lat_max:6.2f}m {lat10:10.2f}m {lat0:8.2f}m")
print(f"\n(꺾기 시작 = 횡 오프셋 > {ONSET_M} m. 자리 습관이면 '시작 시 기준점까지' 가 출발과 무관하게 비슷하고, "
      "거리 습관이면 '시작까지 이동' 이 비슷하다.)")

# 출발선 한 바퀴: TRACE 마지막 칸 = 트랙 frac (TRACE_FRAC=1)
LANE_M = 148.1
START = 0.7931
SPOTS = {0.8886: 2.14, 0.1713: 2.27, 0.5737: 1.53}   # r44 빈 차선, 22 m 앞 정지 출발 때 최대 횡 오프셋
laps = sorted(glob.glob(f"{WS}/eval_out/course/startoff/{run}/lap_*.log"))
if laps:
    print(f"\n출발선(frac {START}) 한 바퀴 — 기준점 18 m 앞~통과 구간의 최대 횡 오프셋 (비교: 22 m 앞 정지 출발)")
    print(f"{'회차':>4} {'결과':>9} " + " ".join(f"{a:.4f}(+{((a - START) % 1) * LANE_M:.0f}m)".rjust(18) for a in SPOTS))
for f in laps:
    txt = open(f, encoding="utf-8", errors="replace").read()
    tr = re.search(r"^TRACE (.*)$", txt, re.M)
    res = re.search(r'"result": "(\w+)"', txt)
    cells = []
    if tr:
        pts = [p for p in json.loads(tr[1]) if len(p) >= 4]
        for a, ref in SPOTS.items():
            win = [p[2] for p in pts if -0.12 <= ((p[-1] - a + 0.5) % 1 - 0.5) <= 0.01]
            cells.append(f"{max(win):.2f}m (정지출발 {ref:.2f})" if win else "구간 없음")
        segs, cur = [], None
        for p in pts:
            if p[2] > ONSET_M and cur is None:
                cur = p[-1]
            elif p[2] <= ONSET_M and cur is not None:
                segs.append((cur, p[-1])); cur = None
        if cur is not None:
            segs.append((cur, pts[-1][-1]))
    print(f"{os.path.basename(f)[4:-4]:>4} {res[1] if res else 'NO_REPORT':>9} " + " ".join(c.rjust(18) for c in cells))
    if tr:
        print("     횡 > %.1f m 구간(frac): " % ONSET_M
              + (", ".join(f"{s:.3f}~{e:.3f} (출발 후 {((s - START) % 1) * LANE_M:.0f} m)" for s, e in segs) or "없음"))

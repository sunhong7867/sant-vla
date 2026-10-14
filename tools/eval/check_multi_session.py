#!/usr/bin/env python3
"""다장애물 수집 세션 점검 (2026-10-12): 에피소드마다
  v1: 우리 차선 장애물 최소 중심거리·그 지점 횡 이동량, 옆 차선 장애물 최소 거리, 복귀 수
  v0: 빈 트랙에서 자기 차선 중심선 최대 이탈 (차선 변경 0 이어야 함)
  python3 tools/eval/check_multi_session.py src/sant_vla_pkg/data_course_multiobj/session_<...>
"""
import glob, json, math, os, sys

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
paths = json.load(open(glob.glob(os.path.join(WS, "src/sant_vla_pkg/config/track_paths.json"))[0]))


def lane_dist(lane, x, y):
    return min(math.hypot(px - x, py - y) for px, py in paths[lane])


def poses(ep_dir):
    out = []
    for ln in open(os.path.join(ep_dir, "poses.jsonl")):
        r = json.loads(ln)
        if r.get("src") == "cli":
            out.append((r["x"], r["y"]))
    return out[::5]


sess = sys.argv[1]
rows = [json.loads(l) for l in open(os.path.join(sess, "manifest.jsonl"))]
bad = 0
for r in rows:
    if r.get("group_summary") or not r.get("episode"):
        continue
    ep = os.path.join(sess, r["episode"])
    if not os.path.isdir(ep):
        continue
    s = r["intent_slots"]
    lane = s["lane"]; other = "lane2" if lane == "lane1" else "lane1"
    P = poses(ep)
    head = (f"{r['cf_group_id']} {r['cf_variant_id']} {lane} {s['speed_level']:6s} "
            f"valid={r['valid']} {r.get('detail', '')[:40]}")
    if r["cf_variant_id"] == "v0":
        dev = max(lane_dist(lane, x, y) for x, y in P)
        flag = "  <-- 빈 트랙 이탈" if dev > 0.8 else ""
        bad += bool(flag)
        print(f"{head}\n    빈 트랙 자기 차선 최대 이탈 {dev:.2f} m{flag}")
        continue
    print(head + f"  {r.get('avoid_phase_end', '')}")
    for o in s["obstacles"]:
        d = [math.hypot(x - o["x"], y - o["y"]) for x, y in P]
        i = min(range(len(d)), key=d.__getitem__)
        x, y = P[i]
        shift = lane_dist(lane, x, y)
        tag = "ours" if o["in_our_lane"] else "adj "
        warn = ""
        if o["in_our_lane"] and d[i] < 2.0:
            warn = "  <-- 너무 가까움"
        if not o["in_our_lane"] and d[i] < 2.0:
            warn = "  <-- 옆 차선 물체 근접"
        bad += bool(warn)
        extra = (f"trig {o['trigger_m']:.1f} ramp {o['ramp_m']:.1f}" if o["in_our_lane"] else "")
        print(f"    {tag} {o['noun']:8s} 최소거리 {d[i]:.2f} m, 그때 자기 차선에서 {shift:.2f} m {extra}{warn}")
print(f"\n경고 {bad}")

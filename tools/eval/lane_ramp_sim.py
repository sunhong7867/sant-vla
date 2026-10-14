#!/usr/bin/env python3
"""Offline harness: route_oracle lane swap vs lane ramp, no gz (2026-09-29).

Runs the REAL RouteOracle._goal_cb/_control (ROS publishers stubbed) against a
kinematic unicycle that integrates the published cmd_vel at 20 Hz. The swerve
goal is injected when the centre arc distance to the obstacle (lane2 index
142) drops under the trigger, as collect_corpus does.

Valid for RELATIVE comparisons only (steering step, saturation). The absolute
clearance is NOT trustworthy: real gz demos moved sideways ~1.5x faster than
this model, and the margin here is taken in the lane frame, not the ego body
frame the evaluator uses. Measure clearance on real demos with
tools/eval/swerve_demo_quality.py. See docs/experiments/avoidance/20260929_1131_lane-ramp-swerve.md.

    python3 tools/eval/lane_ramp_sim.py          # 3 schemes x 3 speeds
    python3 tools/eval/lane_ramp_sim.py --grid   # trigger x ramp grid
"""
import json, math, os, sys, types
WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(WS, "src/sant_vla_pkg"))
from sant_vla_pkg import route_oracle_node as R   # noqa: E402

P = json.load(open(R.DEFAULT_PATHS))
SP = P["meta"]["spacing_m"]
EGO_L, EGO_W = 2.4, 0.95   # tools/eval/avoidance_trial.py
EXT = {"car": (2.2, 0.9), "ob_box": (0.85, 0.85), "ob_barrier": (0.3, 1.2),
       "ob_cone": (0.6, 0.6), "ob_barrel": (0.5, 0.5), "ob_person": (0.3, 0.3)}


class Pub:
    def __init__(s): s.last = None
    def publish(s, m): s.last = m


def make(controller, lg):
    o = R.RouteOracle.__new__(R.RouteOracle)
    o.lanes = {k: R.LanePath([tuple(p) for p in P[k]], SP) for k in ("lane1", "lane2")}
    o.rate_hz, o.controller = 20.0, controller
    o.lookahead_base, o.lookahead_gain, o.lookahead_max = 2.1, lg, 5.0
    o.stanley_k, o.stanley_ksoft, o.accel_limit = 2.0, 0.6, 0.55
    o.brake_dist, o.max_offpath, o.arrive_tol = 6.0, 6.0, 1.0
    o.default_speed = 1.2
    o.goal, o.speed, o.clamped, o.path_i, o.ramp = None, 0.0, False, None, None
    o._ego_idx, o._last_log = 0, 1e18
    o.cmd_pub, o.act_pub, o.status_pub = Pub(), Pub(), Pub()
    o.get_logger = lambda: types.SimpleNamespace(info=lambda *a: None)
    return o


def run(controller, lg, v, ramp_m, trigger_m, ob_idx=142, ego_lane="lane2", to_lane="lane1"):
    """rows: (t, centre arc gap to obstacle, lateral offset from ego lane, steer, override)"""
    o = make(controller, lg)
    lane = o.lanes[ego_lane]
    start = ob_idx - int(25.0 / SP)
    x, y = lane.point_at(start)
    nx, ny = lane.point_at(start + 1)
    h = math.atan2(ny - y, nx - x)
    o.speed = v
    o._goal_cb(types.SimpleNamespace(data=json.dumps(
        {"goal": "cruise", "lane": ego_lane, "target_speed": v})))
    dt, fired, rows = 1.0 / 20.0, False, []
    for t in range(int(60 / dt)):
        o.pose = (x, y, h - R.YAW_OFFSET)
        i_e, _ = lane.nearest_index(x, y)
        fwd = ((ob_idx - i_e) % lane.n) * SP
        if fwd > lane.length / 2:
            fwd -= lane.length
        if not fired and 0 < fwd <= trigger_m:
            g = {"goal": "cruise", "lane": to_lane, "target_speed": v}
            if ramp_m:
                g["lane_ramp_m"] = ramp_m
            o._goal_cb(types.SimpleNamespace(data=json.dumps(g)))
            fired = True
        o._control()
        a = json.loads(o.act_pub.last.data)
        cmd = o.cmd_pub.last
        tx, ty = lane.point_at(i_e)
        ux, uy = lane.point_at(i_e + 1)
        th = math.atan2(uy - ty, ux - tx)
        lat = -math.sin(th) * (x - tx) + math.cos(th) * (y - ty)
        rows.append((t * dt, fwd, lat, a["steer_angle_rad"], a["override"]))
        x += cmd.linear.x * math.cos(h) * dt
        y += cmd.linear.x * math.sin(h) * dt
        h += cmd.angular.z * dt
        if fwd < -8:
            break
    return rows


def margin(rows, ext):
    """Lane-frame clearance (pessimistic, see module docstring)."""
    m = 9.9
    for _, fwd, lat, _, _ in rows:
        if abs(fwd) < EGO_L + ext[0]:
            m = min(m, abs(lat) - (EGO_W + ext[1]))
    return m


def summary(tag, rows):
    st = [r[3] for r in rows]
    dst = [abs(st[k] - st[k - 2]) for k in range(2, len(st))]   # per 0.1 s
    lat46 = min(rows, key=lambda r: abs(r[1] - 4.6))[2]
    lat0 = min(rows, key=lambda r: abs(r[1]))[2]
    nclamp = sum(r[4] != "none" for r in rows)
    print(f"{tag:38s} |steer|max {max(map(abs, st)):.2f}  max d(steer)/0.1s {max(dst):.2f}  "
          f"clamp ticks {nclamp:3d}  lat@4.6m {lat46:+.2f}  lat@0m {lat0:+.2f}")


if __name__ == "__main__":
    if "--grid" in sys.argv:
        cases = [("old pp swap 8", "pure_pursuit", 0.6, 0, 8.0)]
        for trig in (10.0, 11.0, 12.0):
            for ramp in (8.0, 9.0, 10.0):
                cases.append((f"stanley trig{trig:.0f} ramp{ramp:.0f}", "stanley", 0.9, ramp, trig))
        print("lane-frame margin (m), <0 = overlap — PESSIMISTIC, relative use only")
        print("%-24s %5s %6s | " % ("case", "v", "|st|") + " ".join(f"{k:>10s}" for k in EXT))
        for tag, ctl, lg, ramp, trig in cases:
            for v in (1.0, 2.16, 2.9):
                rows = run(ctl, lg, v, ramp, trig)
                stmax = max(abs(r[3]) for r in rows if r[1] < trig + 1)
                print("%-24s %5.2f %6.2f | " % (tag, v, stmax)
                      + " ".join(f"{margin(rows, e):+10.2f}" for e in EXT.values()))
    else:
        for v in (1.0, 2.16, 2.9):
            print(f"--- v = {v} m/s")
            summary("old: pure_pursuit lg0.6, 8 m, swap", run("pure_pursuit", 0.6, v, 0, 8.0))
            summary("new: stanley, 10 m, ramp 9 m", run("stanley", 0.9, v, 9.0, 10.0))
            summary("new: pure_pursuit lg0.6, 10 m, ramp 9 m", run("pure_pursuit", 0.6, v, 9.0, 10.0))

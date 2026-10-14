#!/usr/bin/env python3
"""Kinematic go-to-point teacher for counterfactual action labels (2026-10-05).

Same law as route_oracle_node._control_point (the teacher that drove every goto
demo): pure-pursuit curvature 2*local_y/d^2 clamped to MAX_CURVATURE, speed
slewed by accel_limit toward target_speed, linear brake inside brake_dist,
stop at standoff (centre distance). Integrated as a unicycle at the oracle's
20 Hz and emitted as the 10 Hz ego-frame SE(2) deltas the dataset uses
(to_lerobot.py: action = [dx, dy, dyaw] between consecutive 10 Hz poses).

    python3 code/course/goto_kinematic.py data/course/packed_goto   # G-kin check
"""
import json, math, os, statistics, sys

# route_oracle_node.py constants (SIM_WHEEL_BASE 2.86, SIM_MAX_STEER 0.6,
# rate_hz 20, accel_limit 0.55, brake_dist_m 6.0)
MAX_CURVATURE = math.tan(0.6) / 2.86
RATE_HZ, ACCEL, BRAKE = 20.0, 0.55, 6.0


def rollout(x, y, heading, speed, gx, gy, standoff, target_speed, steps=30, out_hz=10.0):
    """-> list of `steps` [dx, dy, dyaw] ego-frame deltas at out_hz."""
    sub = int(round(RATE_HZ / out_hz))
    dt = 1.0 / RATE_HZ
    out = []
    px, py, ph = x, y, heading
    done = False
    for _ in range(steps):
        x0, y0, h0 = px, py, ph
        for _ in range(sub):
            if done:
                break
            dx, dy = gx - px, gy - py
            dist = math.hypot(dx, dy)
            remaining = dist - standoff
            if remaining <= 0.05:
                speed, done = 0.0, True
                break
            tgt = target_speed
            if remaining < BRAKE:
                tgt *= max(0.0, remaining / BRAKE)
                tgt = max(tgt, 0.12) if remaining > 0.3 else tgt
            speed += max(-ACCEL * dt, min(ACCEL * dt, tgt - speed))
            c, s = math.cos(ph), math.sin(ph)
            lx, ly = dx * c + dy * s, -dx * s + dy * c
            k = max(-MAX_CURVATURE, min(MAX_CURVATURE, 2.0 * ly / max(lx * lx + ly * ly, 1e-6)))
            # exact arc step
            w = k * speed
            if abs(w) < 1e-9:
                px += speed * dt * math.cos(ph); py += speed * dt * math.sin(ph)
            else:
                px += speed / w * (math.sin(ph + w * dt) - math.sin(ph))
                py -= speed / w * (math.cos(ph + w * dt) - math.cos(ph))
            ph += w * dt
        c, s = math.cos(h0), math.sin(h0)
        ddx, ddy = px - x0, py - y0
        out.append([ddx * c + ddy * s, -ddx * s + ddy * c,
                    math.atan2(math.sin(ph - h0), math.cos(ph - h0))])
    return out


def lat_end(ch, n=None):
    x = y = yaw = 0.0
    for dx, dy, dyaw in ch[:n]:
        x += math.cos(yaw) * dx - math.sin(yaw) * dy
        y += math.sin(yaw) * dx + math.cos(yaw) * dy
        yaw += dyaw
    return x, y


def g_kin(packed, n_ep=200, ks=(3, 10, 20)):
    """Rollout toward the REAL target vs the recorded demo: 3 s end-point error."""
    errs = {k: [] for k in ks}
    for i, line in enumerate(open(os.path.join(packed, "index.jsonl"))):
        if i >= n_ep:
            break
        r = json.loads(line)
        d = os.path.join(packed, r["episode"])
        m = json.load(open(os.path.join(d, "meta.json")))
        g = m["intent_slots"]["goto"]
        if g.get("mode") != "direct":
            continue
        t = g["objects"][g["target"]]
        rows = [json.loads(l) for l in open(os.path.join(d, "resampled_10hz.jsonl"))]
        for k in ks:
            if k + 30 >= len(rows):
                continue
            a = rows[k]
            ch = rollout(a["x"], a["y"], a["heading"], a["state"][0], t["x"], t["y"],
                         g["standoff_m"], m["intent_slots"]["target_speed"])
            demo = [rw["action"] for rw in rows[k:k + 30]]
            (px, py), (qx, qy) = lat_end(ch), lat_end(demo)
            errs[k].append(math.hypot(px - qx, py - qy))
    for k, e in errs.items():
        if e:
            print(f"k={k:2d} n={len(e):3d}  3 s end-point error median {statistics.median(e):.3f} m"
                  f"  p90 {sorted(e)[int(0.9 * len(e))]:.3f} m")


if __name__ == "__main__":
    g_kin(sys.argv[1])

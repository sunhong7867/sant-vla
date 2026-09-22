#!/usr/bin/env python3
"""Oracle (v10, pure-pursuit) vs YOLO (v3y) teacher action-signal diagnostic.

Both teachers drive the same ring cleanly (open-loop), yet only the oracle's
imitation oscillates (r22-r25). This compares the CHARACTER of their action
signals on curve frames to find what a flow-matching policy finds hard to
imitate stably. Metrics per teacher, aggregated over curve frames of cruise
episodes:

  mag        mean |steering curvature| kappa_cmd = dyaw/ds  (speed-invariant)
  jerk       mean |kappa_cmd(t) - kappa_cmd(t-1)|           (roughness)
  det_std    within-(path-curvature)-bin std of kappa_cmd   (LOW = deterministic
             razor-sharp state->action map: brittle to imitate)
  acf(l)     autocorrelation of kappa_cmd at lag l; a sign flip / negative lobe
             at l=2..6 is an oscillatory (limit-cycle-prone) signature
  phase      lag (frames) of peak cross-correlation between path curvature and
             kappa_cmd; NEGATIVE = steering LEADS the curve (lookahead), which
             under closed-loop execution delay turns into destabilizing phase
"""
import glob
import json
import math
import os
import statistics as st

DIAG = os.path.dirname(os.path.abspath(__file__)) + "/diag"
KAPPA_CURVE = 0.06        # 1/m; curve frame if |path curvature| exceeds this
W = 3                     # geometric curvature window (frames each side)


def path_curvature(xs, ys, i):
    a, b, c = (xs[i-W], ys[i-W]), (xs[i], ys[i]), (xs[i+W], ys[i+W])
    v1 = (b[0]-a[0], b[1]-a[1]); v2 = (c[0]-b[0], c[1]-b[1])
    l1 = math.hypot(*v1); l2 = math.hypot(*v2)
    if l1 < 1e-6 or l2 < 1e-6:
        return 0.0
    ang = math.atan2(v2[1], v2[0]) - math.atan2(v1[1], v1[0])
    ang = (ang + math.pi) % (2*math.pi) - math.pi
    return ang / ((l1 + l2) / 2.0)


def load_corpus(name, limit=None):
    """Return list of episodes; each = dict of parallel arrays on curve mask."""
    eps = []
    dirs = sorted(glob.glob(f"{DIAG}/{name}/*/"))
    for d in dirs:
        rj = os.path.join(d, "resampled_10hz.jsonl")
        mj = os.path.join(d, "meta.json")
        if not (os.path.exists(rj) and os.path.exists(mj)):
            continue
        meta = json.load(open(mj))
        if (meta.get("intent_id") or meta.get("intent_slots", {}).get("intent_id")) not in (None, "cruise") \
           and meta.get("intent_slots", {}).get("lane") is None:
            pass
        rows = [json.loads(l) for l in open(rj)]
        if len(rows) < 2*W + 10:
            continue
        xs = [r["x"] for r in rows]; ys = [r["y"] for r in rows]
        kcmd = []       # steering curvature dyaw/ds
        kpath = []      # geometric path curvature
        for i, r in enumerate(rows):
            a = r.get("action")
            if not a:
                kcmd.append(None); kpath.append(None); continue
            ds = math.hypot(a[0], a[1])
            kcmd.append(a[2]/ds if ds > 1e-3 else None)
            kpath.append(path_curvature(xs, ys, i) if W <= i < len(rows)-W else None)
        eps.append({"kcmd": kcmd, "kpath": kpath})
        if limit and len(eps) >= limit:
            break
    return eps


def analyze(name):
    eps = load_corpus(name)
    mags, jerks, dets = [], [], []
    acf = {l: [] for l in range(1, 8)}
    phases = []
    # global curvature bins for determinism
    for ep in eps:
        kc, kp = ep["kcmd"], ep["kpath"]
        # curve-frame series (contiguous), speed-invariant steering curvature
        s = [(kc[i], kp[i]) for i in range(len(kc))
             if kc[i] is not None and kp[i] is not None and abs(kp[i]) > KAPPA_CURVE]
        if len(s) < 12:
            continue
        cs = [a for a, _ in s]
        mags.append(st.mean(abs(v) for v in cs))
        jerks.append(st.mean(abs(cs[i]-cs[i-1]) for i in range(1, len(cs))))
        # determinism: bin by path curvature, within-bin std of steering
        bins = {}
        for a, p in s:
            bins.setdefault(round(p, 2), []).append(a)
        bstd = [st.pstdev(v) for v in bins.values() if len(v) >= 4]
        if bstd:
            dets.append(st.mean(bstd))
        # autocorrelation of detrended steering curvature
        m = st.mean(cs); d = [v-m for v in cs]
        var = sum(v*v for v in d) or 1e-9
        for l in acf:
            if len(d) > l:
                acf[l].append(sum(d[i]*d[i-l] for i in range(l, len(d)))/var)
        # phase: cross-corr path-curvature vs steering over lags -4..+4
        pp = [p for _, p in s]; mp = st.mean(pp); dp = [v-mp for v in pp]
        best, blag = -9, 0
        for lag in range(-4, 5):
            num = 0; cnt = 0
            for i in range(len(d)):
                j = i - lag
                if 0 <= j < len(dp):
                    num += d[i]*dp[j]; cnt += 1
            c = num/cnt if cnt else 0
            if c > best:
                best, blag = c, lag
        phases.append(blag)
    def ms(x): return (st.mean(x), st.pstdev(x)) if x else (float('nan'), 0)
    return {
        "episodes": len(eps),
        "curve_mag": ms(mags),
        "jerk": ms(jerks),
        "det_std": ms(dets),
        "acf": {l: (st.mean(v) if v else float('nan')) for l, v in acf.items()},
        "phase_lag_frames": ms(phases),
    }


for name in ("packed_v3y", "packed_v10"):
    r = analyze(name)
    tag = "YOLO(v3y)" if "v3y" in name else "ORACLE(v10)"
    print(f"\n===== {tag} =====")
    print(f"  episodes analyzed : {r['episodes']}")
    print(f"  curve steer |kappa|: {r['curve_mag'][0]:.4f}  (sd {r['curve_mag'][1]:.4f})")
    print(f"  jerk |d kappa|     : {r['jerk'][0]:.4f}  (sd {r['jerk'][1]:.4f})")
    print(f"  det_std (state-cond): {r['det_std'][0]:.4f}  (sd {r['det_std'][1]:.4f})  [LOW=deterministic]")
    print(f"  phase lag (frames) : {r['phase_lag_frames'][0]:+.2f}  (sd {r['phase_lag_frames'][1]:.2f})  [<0 = steering leads curve]")
    print(f"  autocorr kappa_cmd : " + "  ".join(f"l{l}:{r['acf'][l]:+.2f}" for l in r['acf']))

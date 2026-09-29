#!/bin/bash
# v32r = v29r 스테이징 + packed_multi_hard (강한 제동 시연, v1 만, 학습 플릿).
# packed_multi_hard_heldout 은 평가 전용 — 절대 넣지 않는다.
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_multi_hard ] || { echo "data/course/packed_multi_hard 없음"; exit 2; }
rm -rf data/course/packed_v32r_staging data/course/lerobot/v32r
mkdir -p data/course/packed_v32r_staging
python3 - <<'PY'
import json, os, math
dst = "data/course/packed_v32r_staging"
def stop_audit_bad(d, min_gap=6.0):
    m = json.load(open(os.path.join(d, "meta.json")))
    ob = (m.get("intent_slots") or {}).get("obstacle") or {}
    if not ob.get("in_our_lane"):
        return False
    rows = [json.loads(l) for l in open(os.path.join(d, "resampled_10hz.jsonl"))]
    stand = [math.hypot(r["x"]-ob["x"], r["y"]-ob["y"])
             for r in rows if (r["state"] or [9])[0] < 0.1]
    return bool(stand) and min(stand) < min_gap
def link_all(src, skip_v1_ours=False, skip_bad=False, min_gap=6.0):
    n = 0
    if not os.path.isdir(src):
        print(src, "-> MISSING"); return
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d): continue
        if not os.path.exists(os.path.join(d, "reasoning.jsonl")): continue
        if skip_bad and stop_audit_bad(d, min_gap):
            print("  audit-excluded:", name); continue
        if skip_v1_ours:
            m = json.load(open(os.path.join(d, "meta.json")))
            ob = (m.get("intent_slots") or {}).get("obstacle") or {}
            if ob.get("in_our_lane"): continue
        os.symlink(os.path.abspath(d), os.path.join(dst, name)); n += 1
    print(src, "->", n)
link_all("data/packed_v3y")
link_all("data/packed_v9", skip_bad=True)
link_all("data/packed_v9_pilot", skip_v1_ours=True)
link_all("data/packed_v9_fix", skip_bad=True)
link_all("data/packed_stanley")
link_all("data/packed_signal")
link_all("data/course/packed_multi", skip_bad=True)
link_all("data/course/packed_multi_fix", skip_bad=True)
# hard demos: oracle overshoots the 9 m line (median standstill 6.4 m centre), so the
# 6 m audit floor would drop half of them. 4.8 m = car body contact (r10 rule) is the
# floor that still excludes taught contact for every model in the fleet.
link_all("data/course/packed_multi_hard", skip_bad=True, min_gap=4.8)
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v32r_staging \
  --repo-id navvla/v32r --out data/course/lerobot/v32r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v32r \
  data/packed_v3y data/packed_v9 data/packed_v9_pilot data/packed_v9_fix \
  data/packed_stanley data/packed_signal data/course/packed_multi data/course/packed_multi_fix \
  data/course/packed_multi_hard
echo CONVERT_V32R_OK

#!/bin/bash
# v29r = v28r 스테이징(v3y + v9 클린 + pilot + fix + Stanley + signal) + packed_multi
# (다중 물체 회피, 2026-09-22: prius/해치백 3색/박스/꼬깔/바리케이드 학습,
#  사람/드럼통/초록 해치백 홀드아웃 — packed_multi_heldout 은 절대 넣지 않는다).
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_multi ] || { echo "data/course/packed_multi 없음"; exit 2; }
rm -rf data/course/packed_v29r_staging data/course/lerobot/v29r
mkdir -p data/course/packed_v29r_staging
python3 - <<'PY'
import json, os, math
dst = "data/course/packed_v29r_staging"
def stop_audit_bad(d):
    m = json.load(open(os.path.join(d, "meta.json")))
    ob = (m.get("intent_slots") or {}).get("obstacle") or {}
    if not ob.get("in_our_lane"):
        return False
    rows = [json.loads(l) for l in open(os.path.join(d, "resampled_10hz.jsonl"))]
    stand = [math.hypot(r["x"]-ob["x"], r["y"]-ob["y"])
             for r in rows if (r["state"] or [9])[0] < 0.1]
    return bool(stand) and min(stand) < 6.0
def link_all(src, skip_v1_ours=False, skip_bad=False):
    n = 0
    if not os.path.isdir(src):
        print(src, "-> MISSING"); return
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d): continue
        if not os.path.exists(os.path.join(d, "reasoning.jsonl")): continue
        if skip_bad and stop_audit_bad(d):
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
link_all("data/packed_stanley")        # Stanley reactive dead-centre cruise
link_all("data/packed_signal")         # visual-grounded signal-stop
link_all("data/course/packed_multi", skip_bad=True)      # multi-object avoidance (train fleet only)
link_all("data/course/packed_multi_fix", skip_bad=True)  # v1-only repair batch (tf-gap drops)
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v29r_staging \
  --repo-id navvla/v29r --out data/course/lerobot/v29r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v29r \
  data/packed_v3y data/packed_v9 data/packed_v9_pilot data/packed_v9_fix \
  data/packed_stanley data/packed_signal data/course/packed_multi data/course/packed_multi_fix
echo CONVERT_V29R_OK

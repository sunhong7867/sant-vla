#!/bin/bash
# v36r = Stanley 순항(109) + packed_ramp (램프 차선변경 회피, 2026-09-29; 위치 고정
# lane2 142, 2차선 출발 → 1차선, Stanley 선생, 트리거 10 m / 램프 9 m, v0/v1 쌍,
# 물체 7종). packed_ramp_heldout(드럼통·사람)은 절대 넣지 않는다.
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_ramp ] || { echo "data/course/packed_ramp 없음"; exit 2; }
rm -rf data/course/packed_v36r_staging data/course/lerobot/v36r
mkdir -p data/course/packed_v36r_staging
python3 - <<'PY'
import os
dst = "data/course/packed_v36r_staging"
def link_all(src):
    n = 0
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            os.symlink(os.path.abspath(d), os.path.join(dst, name)); n += 1
    print(src, "->", n)
link_all("data/packed_stanley")
link_all("data/course/packed_ramp")
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v36r_staging \
  --repo-id navvla/v36r --out data/course/lerobot/v36r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v36r \
  data/packed_stanley data/course/packed_ramp
echo CONVERT_V36R_OK

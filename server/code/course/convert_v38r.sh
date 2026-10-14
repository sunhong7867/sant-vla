#!/bin/bash
# v38r = Stanley 순항(109) + packed_ramp70 (2026-09-29). v36r 과 같은 레시피에 장애물 위치만
# lane2 142(아래 직선 끝, 곡선 출구에서 트리거) → lane2 70(왼쪽 준직선, 출발 20~23 m 상류,
# 접근 전부 직선). Stanley, 트리거 10 m / 램프 9 m, v0/v1 쌍, 물체 7종.
# packed_ramp70_heldout(드럼통·사람)은 절대 넣지 않는다.
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_ramp70 ] || { echo "data/course/packed_ramp70 없음"; exit 2; }
rm -rf data/course/packed_v38r_staging data/course/lerobot/v38r
mkdir -p data/course/packed_v38r_staging
python3 - <<'PY'
import os
dst = "data/course/packed_v38r_staging"
def link_all(src):
    n = 0
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            os.symlink(os.path.abspath(d), os.path.join(dst, name)); n += 1
    print(src, "->", n)
link_all("data/packed_stanley")
link_all("data/course/packed_ramp70")
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v38r_staging \
  --repo-id navvla/v38r --out data/course/lerobot/v38r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v38r \
  data/packed_stanley data/course/packed_ramp70
echo CONVERT_V38R_OK

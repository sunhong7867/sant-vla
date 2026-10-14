#!/bin/bash
# v41r = Stanley 순항(109) + packed_div (2026-09-30). 장애물 위치를 에피소드마다 트랙 전체에서 무작위
# (출발 20~30 m 상류), v0/v1/v2(옆 차선 장애물 = 차선 유지) 전부, 물체 7종, Stanley, 트리거 10 m / 램프 9 m.
# r38~r40 의 고정 위치(인덱스 70) 위치 prior 를 끊기 위한 코퍼스. packed_div_heldout(드럼통·사람)은 넣지 않는다.
#
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_div ] || { echo "data/course/packed_div 없음"; exit 2; }
rm -rf data/course/packed_v41r_staging data/course/lerobot/v41r
mkdir -p data/course/packed_v41r_staging
python3 - <<'PY'
import os
dst = "data/course/packed_v41r_staging"
def link_all(src):
    n = 0
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            os.symlink(os.path.abspath(d), os.path.join(dst, name)); n += 1
    print(src, "->", n)
link_all("data/packed_stanley")
link_all("data/course/packed_div")
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v41r_staging \
  --repo-id navvla/v41r --out data/course/lerobot/v41r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v41r \
  data/packed_stanley data/course/packed_div
echo CONVERT_V41R_OK

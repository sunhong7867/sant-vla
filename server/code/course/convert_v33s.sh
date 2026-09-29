#!/bin/bash
# v33s = Stanley 순항(109) + packed_swerve (직접 차선변경 회피, 위치 고정, 물체 7종;
# v0 빈 차선 / v1 회피 / v2 옆 차선 대조 포함). 1 시간 resume 용 소형 스테이징.
# packed_swerve_heldout 은 절대 넣지 않는다.
set -e
cd ~/sunhong/nav-vla
[ -d data/course/packed_swerve ] || { echo "data/course/packed_swerve 없음"; exit 2; }
rm -rf data/course/packed_v33s_staging data/course/lerobot/v33s
mkdir -p data/course/packed_v33s_staging
python3 - <<'PY'
import os
dst = "data/course/packed_v33s_staging"
def link_all(src):
    n = 0
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            os.symlink(os.path.abspath(d), os.path.join(dst, name)); n += 1
    print(src, "->", n)
link_all("data/packed_stanley")
link_all("data/course/packed_swerve")
PY
./venv/bin/python code/to_lerobot.py data/course/packed_v33s_staging \
  --repo-id navvla/v33s --out data/course/lerobot/v33s \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v33s \
  data/packed_stanley data/course/packed_swerve
echo CONVERT_V33S_OK

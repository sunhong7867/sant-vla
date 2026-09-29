#!/bin/bash
# v35s = packed_swerve 만 (72 ep: v0 빈 차선 / v1 회피 / v2 옆 차선). 과적합 검사용:
# 순항 코퍼스를 빼고 회피 쌍만 주면 반사실 비가 1.0 에 가는가(혼합 문제) 아니면
# 여전히 0.35 에 걸리는가(모델 한계).
set -e
cd ~/sunhong/nav-vla
rm -rf data/course/packed_v35s_staging data/course/lerobot/v35s
mkdir -p data/course/packed_v35s_staging
for d in data/course/packed_swerve/session_*; do ln -s "$(readlink -f "$d")" data/course/packed_v35s_staging/; done
ls data/course/packed_v35s_staging | wc -l
./venv/bin/python code/to_lerobot.py data/course/packed_v35s_staging \
  --repo-id navvla/v35s --out data/course/lerobot/v35s --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v35s data/course/packed_swerve
echo CONVERT_V35S_OK

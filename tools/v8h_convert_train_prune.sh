#!/bin/bash
# v8h(목표 라벨 direct_zone 한정) 변환 + 60K 학습 + 실시간 체크포인트 프루닝.
# 가설: v8g의 ring_goal 모순 라벨 제거만으로 직행 그라운딩이 개선되는가
# (docs/ver/20260824_1138). 데이터 재수집 없음, packed_v8 재변환만.
#
# 용량 정책(사용자 지시 2026-08-24 "바로바로 지워라"):
#  - 학습 중 중간 체크포인트는 최신 2개만 유지하며 즉시 삭제
#  - 변환 전 이전 lerobot/v8h 잔재 삭제, 종료 후 060000만 남김
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
RUN=navvla_smolvla_v8h

step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }

step "ship label-filtered to_lerobot.py"
scp $WS/src/sant_vla_pkg/scripts/to_lerobot.py "$SRV":'~/sunhong/nav-vla/code/to_lerobot.py'

step "convert lerobot/v8h (goal labels: direct_zone only)"
ssh "$SRV" "cd ~/sunhong/nav-vla && rm -rf data/lerobot/v8h && \
  ./venv/bin/python code/to_lerobot.py data/packed_v8 \
    --repo-id sunhong/navvla_sim_v8h --out data/lerobot/v8h \
    --goal-zones code/track_paths.json && echo CONVERT_DONE" \
  || { echo CONVERT_FAIL; exit 5; }

step "sanity: goal episode count must be ~41 (direct only), state dim 5"
ssh "$SRV" "grep -o '\"observation.state\"[^}]*}' ~/sunhong/nav-vla/data/lerobot/v8h/meta/info.json | head -c 200; echo"

step "disk check + launch training (60K, GPU1/3090)"
ssh "$SRV" "df -h ~ | tail -1"
ssh "$SRV" "cd ~/sunhong/nav-vla && [ ! -d runs/$RUN ] || { echo RUN_DIR_EXISTS; exit 9; } && \
  setsid nohup env GPU=1 BATCH=8 STEPS=60000 WORKERS=8 SAVE_FREQ=5000 \
    bash code/train_smolvla.sh \
      /home/autolab_sw/sunhong/nav-vla/data/lerobot/v8h \
      sunhong/navvla_sim_v8h $RUN \
    > /dev/null 2>&1 < /dev/null & echo TRAIN_LAUNCHED" \
  || { echo TRAIN_LAUNCH_FAIL; exit 6; }

step "confirm steps are ticking (5 min)"
sleep 300
ssh "$SRV" "grep -oE 'step:[0-9.K]+ .*loss:[0-9.]+' ~/sunhong/nav-vla/logs/$RUN.log 2>/dev/null | tail -2; \
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader"

step "live checkpoint pruning until 060000 appears (~8.5h)"
# 최신 2개만 유지. last 심링크/060000은 보존.
ssh "$SRV" "for i in \$(seq 1 120); do
  d=~/sunhong/nav-vla/runs/$RUN/checkpoints
  if [ -d \$d ]; then
    ls -d \$d/0* 2>/dev/null | head -n -2 | grep -v 060000 | xargs -r rm -rf
  fi
  [ -f \$d/060000/pretrained_model/model.safetensors ] && { echo TRAIN_DONE; break; }
  grep -qiE 'Traceback|CUDA out of memory|RuntimeError' ~/sunhong/nav-vla/logs/$RUN.log 2>/dev/null \
    && { echo TRAIN_ERROR; tail -5 ~/sunhong/nav-vla/logs/$RUN.log; exit 7; }
  sleep 300
done
[ -f \$d/060000/pretrained_model/model.safetensors ] || { echo TRAIN_TIMEOUT; exit 8; }" \
  || exit $?

step "final prune (keep 060000 only) + fetch to laptop"
ssh "$SRV" "d=~/sunhong/nav-vla/runs/$RUN/checkpoints; \
  for c in \$d/0*; do [ \"\$(basename \$c)\" = 060000 ] || rm -rf \"\$c\"; done; \
  du -sh ~/sunhong/nav-vla/runs/$RUN; df -h ~ | tail -1"
mkdir -p $WS/models/ckpt_v8h_60k
rsync -a "$SRV":"~/sunhong/nav-vla/runs/$RUN/checkpoints/060000/pretrained_model/" \
  $WS/models/ckpt_v8h_60k/ || { echo FETCH_FAIL; exit 10; }
ls -la $WS/models/ckpt_v8h_60k/ | head -5

echo "V8H_TRAIN_CHAIN_DONE $(date +%H:%M)"

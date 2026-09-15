#!/bin/bash
# v8g(목표 조건화, 상태 5차원) 변환 + 60K 학습 개시 — 서버 원격 실행 체인
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla

step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }

step "ship updated to_lerobot.py + zones"
scp $WS/src/sant_vla_pkg/scripts/to_lerobot.py "$SRV":'~/sunhong/nav-vla/code/to_lerobot.py'
scp $WS/src/sant_vla_pkg/config/track_paths.json "$SRV":'~/sunhong/nav-vla/code/track_paths.json'

step "convert lerobot/v8g (goal-conditioned)"
ssh "$SRV" "cd ~/sunhong/nav-vla && rm -rf data/lerobot/v8g && \
  ./venv/bin/python code/to_lerobot.py data/packed_v8 \
    --repo-id sunhong/navvla_sim_v8g --out data/lerobot/v8g \
    --goal-zones code/track_paths.json && echo CONVERT_DONE" \
  || { echo CONVERT_FAIL; exit 5; }

step "sanity: state dim=5 in dataset meta"
ssh "$SRV" "grep -o '\"observation.state\"[^}]*}' ~/sunhong/nav-vla/data/lerobot/v8g/meta/info.json | head -c 300; echo"

step "disk check + launch training (60K, GPU1/3090)"
ssh "$SRV" "df -h ~ | tail -1"
ssh "$SRV" "cd ~/sunhong/nav-vla && [ ! -d runs/navvla_smolvla_v8g ] || { echo RUN_DIR_EXISTS; exit 9; } && \
  setsid nohup env GPU=1 BATCH=8 STEPS=60000 WORKERS=8 SAVE_FREQ=5000 \
    bash code/train_smolvla.sh \
      /home/autolab_sw/sunhong/nav-vla/data/lerobot/v8g \
      sunhong/navvla_sim_v8g navvla_smolvla_v8g \
    > /dev/null 2>&1 < /dev/null & echo TRAIN_LAUNCHED" \
  || { echo TRAIN_LAUNCH_FAIL; exit 6; }

step "confirm steps are ticking"
sleep 300
ssh "$SRV" "grep -oE 'step:[0-9.K]+ .*loss:[0-9.]+' ~/sunhong/nav-vla/logs/navvla_smolvla_v8g.log 2>/dev/null | tail -2; \
  tail -c 400 ~/sunhong/nav-vla/logs/navvla_smolvla_v8g.log 2>/dev/null | tr '\r' '\n' | tail -3; \
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader"
echo "[v8g] 개시 완료 $(date +%H:%M)"

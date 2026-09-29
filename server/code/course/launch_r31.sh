#!/bin/bash
# r31 = r30 와 같은 v29r, 부스트 방식만 r8~r11 시절의 `sampler` (가중 리샘플링이
# 액션·CE 양쪽에 걸림). 그 레시피는 폐루프에서 "차 앞에 서서 안 떠남"까지는 갔다
# (제동은 배웠다는 뜻). resample-comp 계열(r29/r30)은 제동 자체가 안 나옴
# (probe_obstacle_brake v2: ahead dv pred -0.10 vs demo -0.28, 2026-09-23 04:30).
# 차선중심 회귀 비용은 감수 — 지금 질문은 "회피가 배워지나"다. 3090(GPU1).
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r31 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v29r \
  --base-checkpoint runs/navvla_smolvla_v3y/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r31 --steps 25000 --log-freq 200 --save-freq 6250 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  > logs/course/navvla_reasoning_r31.log 2>&1 < /dev/null &
echo LAUNCHED

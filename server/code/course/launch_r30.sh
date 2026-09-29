#!/bin/bash
# r30 = r29 + 다중물체 회피 액션 가중치를 ABSOLUTE 8.0 으로 (r29 는 1/w 보상 위에
# 곱해서 실효 0.17~1.0 — 12.5k 체크포인트가 학습 물체(박스)도 들이받음, 2026-09-23).
# 4070Ti(GPU0)에서 r29 와 병렬. 데이터셋은 v29r 그대로.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r30 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v29r \
  --base-checkpoint runs/navvla_smolvla_v3y/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r30 --steps 25000 --log-freq 200 --save-freq 12500 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target resample-comp \
  --action-v9-weight 0.0 --action-v3y-cruise-weight 0.0 --action-signal-weight 5.0 \
  --action-multiobj-weight 8.0 --sample-decode \
  > logs/course/navvla_reasoning_r30.log 2>&1 < /dev/null &
echo LAUNCHED

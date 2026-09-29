#!/bin/bash
# r29 = r28 레시피 + 다중 물체 회피 액션 부스트 (--action-multiobj-weight).
# v9 액션 0, v3y-cruise 0(멀티 v0/v2 도 여기에 묶임), signal x5 는 r28 그대로.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r29 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v29r \
  --base-checkpoint runs/navvla_smolvla_v3y/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r29 --steps 25000 --log-freq 200 --save-freq 12500 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target resample-comp \
  --action-v9-weight 0.0 --action-v3y-cruise-weight 0.0 --action-signal-weight 5.0 \
  --action-multiobj-weight 4.0 --sample-decode \
  > logs/course/navvla_reasoning_r29.log 2>&1 < /dev/null &
echo LAUNCHED

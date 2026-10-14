#!/bin/bash
# r39 = r38 + state 드롭아웃 0.5 (yaw_rate, steer) — r37 레시피를 v38r 에.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r39 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v38r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r39 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --state-dropout ${DROP:-0.5} \
  > logs/course/navvla_reasoning_r39.log 2>&1 < /dev/null &
echo LAUNCHED

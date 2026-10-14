#!/bin/bash
# r37 = r36 + state 드롭아웃 0.5 (yaw_rate, steer). 회피 중 프레임을 조향 state 만으로
# 맞추는 지름길을 막아 영상이 설명하게 한다. r36 과 비교.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r37 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v36r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r37 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --state-dropout ${DROP:-0.5} \
  > logs/course/navvla_reasoning_r37.log 2>&1 < /dev/null &
echo LAUNCHED

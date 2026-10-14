#!/bin/bash
# r36 = r26(데모 기본)에서 1 h resume, v36r(Stanley + 램프 회피). r33 과 같은 레시피
# (8000 steps, sampler 부스트 x4)에 v0 짝 부스트만 추가 — 시연 모양(램프)과
# 짝 대조의 효과를 r33 과 비교한다.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r36 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v36r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r36 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost \
  > logs/course/navvla_reasoning_r36.log 2>&1 < /dev/null &
echo LAUNCHED

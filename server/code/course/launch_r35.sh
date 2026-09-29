#!/bin/bash
# r35 = 과적합 검사: v35s(회피 쌍만) 로 r26 에서 4000 steps, 부스트 ×4.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r35 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v35s \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r35 --steps ${STEPS:-4000} --log-freq 200 --save-freq 2000 \
  --ce-weight 0.2 --obstacle-boost ${BOOST:-4.0} --boost-target sampler \
  > logs/course/navvla_reasoning_r35.log 2>&1 < /dev/null &
echo LAUNCHED

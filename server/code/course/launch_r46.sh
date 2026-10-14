#!/bin/bash
# r46 (2026-10-02) = r45 레시피 그대로, 데이터만 v46r(boxpair2 포함, 짝 약 137). r45 는 boxpair2 finalize 실패로 짝 60.

cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r46 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v46r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r46 --steps ${STEPS:-8000} --log-freq 200 --save-freq 8000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --contrast-twin-variants v0,v2 \
  > logs/course/navvla_reasoning_r46.log 2>&1 < /dev/null &
echo LAUNCHED

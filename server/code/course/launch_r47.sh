#!/bin/bash
# r47 (2026-10-02 R2) = r46 레시피 그대로, 데이터만 v47r(박스 짝 137 + 다물체 짝 packed_mpair).

cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r47 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v47r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r47 --steps ${STEPS:-8000} --log-freq 200 --save-freq 8000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --contrast-twin-variants v0,v2 \
  > logs/course/navvla_reasoning_r47.log 2>&1 < /dev/null &
echo LAUNCHED

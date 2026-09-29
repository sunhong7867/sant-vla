#!/bin/bash
# r32 = v32r(강한 제동 시연 포함) + sampler 부스트(r31 방식). GPU 는 인자.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r32 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v32r \
  --base-checkpoint runs/navvla_smolvla_v3y/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r32 --steps 25000 --log-freq 200 --save-freq 6250 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  > logs/course/navvla_reasoning_r32.log 2>&1 < /dev/null &
echo LAUNCHED

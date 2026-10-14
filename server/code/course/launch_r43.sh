#!/bin/bash
# r43 (2026-10-01) = r42 레시피(문구 없음, 모델 스스로 인지)를 v43r(박스 v0/v1/v2 묶음)에.
# 짝 부스트(--contrast-twin-boost)가 이번엔 실제로 작동한다(같은 묶음 v0 이 v1 과 같은 가중치).
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r43 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v43r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r43 --steps ${STEPS:-8000} --log-freq 200 --save-freq 8000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost \
  > logs/course/navvla_reasoning_r43.log 2>&1 < /dev/null &
echo LAUNCHED

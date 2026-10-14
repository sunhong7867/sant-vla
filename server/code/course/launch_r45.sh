#!/bin/bash
# r45 (2026-10-02) = r42 레시피(문구 없음)를 v45r(박스 v1+v2 짝 + boxtri + 빈 차선)에. 짝 부스트를 v2 에도(같은 출발의 옆 차선 직진).

cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r45 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v45r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r45 --steps ${STEPS:-8000} --log-freq 200 --save-freq 8000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --contrast-twin-variants v0,v2 \
  > logs/course/navvla_reasoning_r45.log 2>&1 < /dev/null &
echo LAUNCHED

#!/bin/bash
# r38 = r36 레시피(r26 에서 8000 steps, sampler 부스트 x4, v0 짝 부스트)를 v38r 에.
# 바뀐 것은 장애물 위치(142 → 70, 직선 접근)뿐 — r36 폐루프 충돌과 비교한다.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r38 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v38r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r38 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost \
  > logs/course/navvla_reasoning_r38.log 2>&1 < /dev/null &
echo LAUNCHED

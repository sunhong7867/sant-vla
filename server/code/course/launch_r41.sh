#!/bin/bash
# r41 = r40 레시피(r26 에서 8000 steps, sampler 부스트 x4, 짝 부스트, --situation-prompt)를 v41r 에.
# 바뀐 것은 코퍼스: 장애물 위치 무작위 + v2(옆 차선 장애물, 문구 clear, 차선 유지).
# 판정: 좌표 정답 문구 폐루프에서 우리 차선 회피 + 옆 차선 유지 (docs/experiments/avoidance/20260930_2107).
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r41 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v41r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r41 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --situation-prompt \
  > logs/course/navvla_reasoning_r41.log 2>&1 < /dev/null &
echo LAUNCHED

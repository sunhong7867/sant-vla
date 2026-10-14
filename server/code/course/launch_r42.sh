#!/bin/bash
# r42 = 순수 end-to-end. r38 레시피(r26 에서 8000 steps, sampler 부스트 x4, 짝 부스트, 상황 문구 없음)를 v41r 에.
# r38 과 차이는 코퍼스뿐(위치 무작위 + v2 옆 차선 유지) — 위치 지름길을 막으면 모델이 장애물을 스스로 보고 피하는가.
# r41 과 차이는 --situation-prompt 없음. 판정: 문구 없이 우리 차선 회피 + 옆 차선 유지 (docs/experiments/log/20261001_*).
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r42 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v41r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r42 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost \
  > logs/course/navvla_reasoning_r42.log 2>&1 < /dev/null &
echo LAUNCHED

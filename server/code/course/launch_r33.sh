#!/bin/bash
# r33 = r26(데모 기본, 주행 완성) 에서 1 시간 resume: v33s(Stanley + 직접 회피).
# 8000 steps ≈ 1 h(3090). sampler 부스트로 회피 프레임 노출 ↑. 학생 조건과 동일한 예산.
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r33 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v33s \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r33 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  > logs/course/navvla_reasoning_r33.log 2>&1 < /dev/null &
echo LAUNCHED

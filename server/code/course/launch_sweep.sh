#!/bin/bash
# 박스 회피 시연 수 스윕 학습 (2026-10-01). r42 레시피(문구 없음 = 모델 스스로 인지) 를 sw<N> 코퍼스에.
#   GPU=1 bash code/course/launch_sweep.sh 80   → runs/course/navvla_reasoning_sw80
N=${1:?N}
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_sw${N} ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/sw${N} \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_sw${N} --steps ${STEPS:-8000} --log-freq 200 --save-freq ${SAVE_FREQ:-8000} \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost \
  > logs/course/navvla_reasoning_sw${N}.log 2>&1 < /dev/null &
echo LAUNCHED

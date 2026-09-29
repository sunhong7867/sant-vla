#!/bin/bash
# r34 = r33 와 같은 v33s·r26 resume, 부스트 ×8 / 16000 steps (≈1.5 h).
# r33(×4, 8k)는 발동 직전 창에서 시연의 35% 에서 정체 → 노출·스텝을 올려 비가
# 올라가는지 본다. 수치는 ×4 → ×8, 8k → 16k 한 번에 (변수 하나씩 바꿀 시간이 없다).
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r34 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v33s \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r34 --steps ${STEPS:-16000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost ${BOOST:-8.0} --boost-target sampler --sample-decode \
  > logs/course/navvla_reasoning_r34.log 2>&1 < /dev/null &
echo LAUNCHED

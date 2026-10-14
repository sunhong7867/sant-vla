#!/bin/bash
# 말로 지정한 물체로 가기 학습 (2026-10-03): r26 베이스, 30 000 step, 10 000 마다 저장. 부스트 없음
# (goto 프레임이 순항보다 훨씬 많아 비율 보정 불필요).  RUN=r50 DATA=g1 GPU=1 bash code/course/launch_goto.sh
RUN=${RUN:?RUN=r50}; DATA=${DATA:?DATA=g1}
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_${RUN} ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-1} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/${DATA} \
  --base-checkpoint ${BASE:-runs/navvla_reasoning_r26/checkpoints/last/pretrained_model} \
  ${BASE_CONFIG:+--base-config "$BASE_CONFIG"} \
  --out runs/course/navvla_reasoning_${RUN} --steps ${STEPS:-30000} --log-freq 200 --save-freq ${SAVE:-10000} \
  --ce-weight 0.2 --sample-decode ${EXTRA:-} \
  > logs/course/navvla_reasoning_${RUN}.log 2>&1 < /dev/null &
echo LAUNCHED

#!/bin/bash
# r40 = r38 레시피(r26 에서 8000 steps, sampler 부스트 x4, 짝 부스트, v38r) + --situation-prompt.
# 해설 skeleton 에서 만든 고정 상황 문구를 동작 패스의 task 뒤에 붙인다(해설 패스는 원래 task).
# r38 과 차이는 이것 하나. 서빙: vla_policy_server.py --situation-from-reasoning.
# 설계: docs/experiments/log/*_situation-conditioned-action-design.md
cd ~/sunhong/nav-vla || exit 1
[ ! -d runs/course/navvla_reasoning_r40 ] || { echo RUN_DIR_EXISTS; exit 9; }
CUDA_VISIBLE_DEVICES=${GPU:-0} PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
setsid nohup ./venv/bin/python code/train_reasoning.py \
  --dataset data/course/lerobot/v38r \
  --base-checkpoint runs/navvla_reasoning_r26/checkpoints/last/pretrained_model \
  --out runs/course/navvla_reasoning_r40 --steps ${STEPS:-8000} --log-freq 200 --save-freq 4000 \
  --ce-weight 0.2 --obstacle-boost 4.0 --boost-target sampler --sample-decode \
  --contrast-twin-boost --situation-prompt \
  > logs/course/navvla_reasoning_r40.log 2>&1 < /dev/null &
echo LAUNCHED

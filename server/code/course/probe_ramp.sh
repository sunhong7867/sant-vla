#!/bin/bash
# 램프 회피 판정 프로브 (2026-09-29): 체크포인트 하나를 학습 물체(packed_ramp v1)와
# 미학습 물체(packed_ramp_heldout v1: 드럼통·사람)에 대해 위치 매칭 v0 대비 부호 있는
# 횡 반응으로 잰다. 창: 10-14 m(트리거 전, 아직 차선 안) / 6-10 m(발동 직후).
#   GPU=1 bash code/course/probe_ramp.sh r36 runs/course/navvla_reasoning_r36
cd ~/sunhong/nav-vla || exit 1
TAG=$1; RUN=$2; CK=$RUN/checkpoints/${STEP:-last}/pretrained_model
OUT=logs/course/probe_ramp_${TAG}.txt
: > "$OUT"
for W in "10 14" "6 10"; do
  set -- $W
  for SET in train heldout; do
    if [ $SET = train ]; then V1=data/course/packed_ramp; else V1=data/course/packed_ramp_heldout; fi
    echo "### $TAG $SET window $1-$2 m" >> "$OUT"
    CUDA_VISIBLE_DEVICES=${GPU:-1} ./venv/bin/python code/course/probe_nearest_v0.py "$CK" \
      --v1 $V1 --v0 data/course/packed_ramp data/course/packed_ramp_heldout \
      --near $1 --far $2 2>&1 | grep -E "^\[|signed|per object|^    |ALL|v0 pool|Traceback|Error" >> "$OUT"
  done
done
echo "PROBE_DONE $TAG"

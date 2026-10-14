#!/bin/bash
# packed_ramp70 → 라벨 → 서버 전송 → v38r 변환 → r38 → r39 학습 → 프로브.
# 장애물 lane2 70(왼쪽 준직선) 위치판. 142 판은 tools/ramp_train_chain.sh (r36/r37).
#   bash tools/ramp70_train_chain.sh
#   SKIP_TRAIN=1 bash tools/ramp70_train_chain.sh     # 변환까지만
# GPU1 은 다른 작업(ollama, 프로브)이 쓰는 날이 있어 기본은 GPU0 에서 r38 → r39 순차.
# 시작 시 GPU1 이 비어 있으면(<2 GB) r39 를 GPU1 에서 동시에 돌린다.
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }
[ -f "$D/packed_ramp70/index.jsonl" ] || { echo "packed_ramp70 없음"; exit 2; }
step "labels"
HELD=""; [ -f "$D/packed_ramp70_heldout/index.jsonl" ] && HELD="$D/packed_ramp70_heldout"
python3 $WS/src/sant_vla_pkg/scripts/label_reasoning.py "$D/packed_ramp70" $HELD || exit 3
step "ship"
rsync -a --info=progress2 "$D/packed_ramp70/" "$SRV":'~/sunhong/nav-vla/data/course/packed_ramp70/' || exit 4
[ -n "$HELD" ] && rsync -a --info=progress2 "$D/packed_ramp70_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_ramp70_heldout/'
scp -q $WS/server/code/train_reasoning.py "$SRV":'~/sunhong/nav-vla/code/' || exit 4
scp -q $WS/server/code/course/convert_v38r.sh $WS/server/code/course/launch_r38.sh \
  $WS/server/code/course/launch_r39.sh $WS/server/code/course/probe_ramp70.sh \
  $WS/server/code/course/probe_nearest_v0.py $WS/server/code/course/probe_fit.py \
  "$SRV":'~/sunhong/nav-vla/code/course/' || exit 4
step "convert v38r"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v38r.sh 2>&1 | grep -v "Svt\|mp4 @\|Map:" | tail -8' || { echo CONVERT_FAIL; exit 5; }
[ "${SKIP_TRAIN:-0}" = 1 ] && exit 0

running() {  # $1=run tag → 0 이면 아직 학습 중. 대괄호 = pgrep 자기매치 방지
  local t=$1
  ssh "$SRV" "pgrep -f 'navvla_reasoning_${t%?}[${t: -1}] --steps' >/dev/null"
}
wait_done() {
  sleep 120
  while running "$1"; do sleep 120; done
  ssh "$SRV" "tail -c 400 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log | tr '\r' '\n' | tail -3"
}
G1=$(ssh "$SRV" 'nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 1')
if [ "${G1:-99999}" -lt 2000 ]; then
  step "launch r38 (GPU0) + r39 (GPU1) — GPU1 비어 있음 (${G1} MiB)"
  ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/launch_r38.sh && GPU=1 bash code/course/launch_r39.sh" || exit 6
  wait_done r38; wait_done r39
else
  step "launch r38 (GPU0) — GPU1 사용 중 (${G1} MiB), r39 는 r38 뒤에"
  ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/launch_r38.sh" || exit 6
  sleep 240
  ssh "$SRV" "cd ~/sunhong/nav-vla; grep -E 'reasoning checkpoint|obstacle boost|contrast twin|dataset:|Traceback|Error' logs/course/navvla_reasoning_r38.log | head -6"
  wait_done r38
  step "launch r39 (GPU0)"
  ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/launch_r39.sh" || exit 6
  wait_done r39
fi
step "probes (GPU0)"
OBXY=-15.99,-12.84
for r in r38 r39; do
  ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/probe_ramp70.sh $r runs/course/navvla_reasoning_$r && \
    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_fit.py runs/course/navvla_reasoning_$r/checkpoints/last/pretrained_model \
      data/course/packed_ramp70 --ob=$OBXY > logs/course/probe_fit70_$r.txt 2>&1; tail -12 logs/course/probe_fit70_$r.txt"
done
echo "[chain] DONE $(date +%H:%M)"

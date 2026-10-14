#!/bin/bash
# packed_ramp → 라벨 → 서버 전송 → v36r 변환 → r36(GPU1) + r37(GPU0) 동시 학습.
#   bash tools/ramp_train_chain.sh
#   SKIP_TRAIN=1 bash tools/ramp_train_chain.sh     # 변환까지만
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }
[ -f "$D/packed_ramp/index.jsonl" ] || { echo "packed_ramp 없음"; exit 2; }
step "labels"
HELD=""; [ -f "$D/packed_ramp_heldout/index.jsonl" ] && HELD="$D/packed_ramp_heldout"
python3 $WS/src/sant_vla_pkg/scripts/label_reasoning.py "$D/packed_ramp" $HELD || exit 3
step "ship"
rsync -a --info=progress2 "$D/packed_ramp/" "$SRV":'~/sunhong/nav-vla/data/course/packed_ramp/' || exit 4
[ -n "$HELD" ] && rsync -a --info=progress2 "$D/packed_ramp_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_ramp_heldout/'
scp -q $WS/server/code/train_reasoning.py "$SRV":'~/sunhong/nav-vla/code/' || exit 4
scp -q $WS/server/code/course/convert_v36r.sh $WS/server/code/course/launch_r36.sh \
  $WS/server/code/course/launch_r37.sh $WS/server/code/course/probe_obstacle_counterfactual.py \
  "$SRV":'~/sunhong/nav-vla/code/course/' || exit 4
step "convert v36r"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v36r.sh 2>&1 | grep -v "Svt\|mp4 @\|Map:" | tail -8' || { echo CONVERT_FAIL; exit 5; }
[ "${SKIP_TRAIN:-0}" = 1 ] && exit 0
step "launch r36 (GPU1) + r37 (GPU0)"
ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=1 bash code/course/launch_r36.sh && GPU=0 bash code/course/launch_r37.sh" || exit 6
sleep 240
for r in r36 r37; do
  echo "--- $r"
  ssh "$SRV" "cd ~/sunhong/nav-vla; grep -E 'reasoning checkpoint|obstacle boost|contrast twin|state dropout|GO-transition|dataset:|Traceback|Error' logs/course/navvla_reasoning_$r.log | head -8; tail -c 300 logs/course/navvla_reasoning_$r.log | tr '\r' '\n' | tail -2"
done

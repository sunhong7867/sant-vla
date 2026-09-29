#!/bin/bash
# multi_hard 코퍼스 → 라벨 → 서버 전송 → v32r 변환 → r32 학습 개시.
#   bash tools/multiobj_hard_chain.sh            # GPU0 기본
#   GPU=1 SKIP_TRAIN=1 bash tools/multiobj_hard_chain.sh
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }
[ -f "$D/packed_multi_hard/index.jsonl" ] || { echo "packed_multi_hard 없음"; exit 2; }
step "labels"
python3 $WS/src/sant_vla_pkg/scripts/label_reasoning.py "$D/packed_multi_hard" "$D/packed_multi_hard_heldout" || exit 3
step "ship"
rsync -a --info=progress2 "$D/packed_multi_hard/" "$SRV":'~/sunhong/nav-vla/data/course/packed_multi_hard/' || exit 4
[ -d "$D/packed_multi_hard_heldout" ] && rsync -a --info=progress2 "$D/packed_multi_hard_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_multi_hard_heldout/'
scp -q $WS/server/code/course/convert_v32r.sh $WS/server/code/course/launch_r32.sh "$SRV":'~/sunhong/nav-vla/code/course/' || exit 4
step "convert v32r"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v32r.sh 2>&1 | grep -v "Svt\|mp4 @" | tail -14' || { echo CONVERT_FAIL; exit 5; }
[ "${SKIP_TRAIN:-0}" = 1 ] && exit 0
step "launch r32 (GPU${GPU:-0})"
ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=${GPU:-0} bash code/course/launch_r32.sh" || exit 6
sleep 200
ssh "$SRV" 'cd ~/sunhong/nav-vla; grep -E "obstacle boost|GO-transition|dataset:|Traceback" logs/course/navvla_reasoning_r32.log | head -4; tail -c 300 logs/course/navvla_reasoning_r32.log | tr "\r" "\n" | tail -2'

step "정리 (로컬 캐시·로그 + 서버 스테이징/완료 런 중간 체크포인트)"
bash $WS/tools/cleanup_artifacts.sh --server | tail -6

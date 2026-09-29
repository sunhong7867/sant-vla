#!/bin/bash
# packed_swerve → 라벨 → 서버 전송 → v33s 변환 → r33 (r26 에서 1 h resume).
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }
[ -f "$D/packed_swerve/index.jsonl" ] || { echo "packed_swerve 없음"; exit 2; }
step "labels"
HELD=""; [ -f "$D/packed_swerve_heldout/index.jsonl" ] && HELD="$D/packed_swerve_heldout"
python3 $WS/src/sant_vla_pkg/scripts/label_reasoning.py "$D/packed_swerve" $HELD || exit 3
step "ship"
rsync -a --info=progress2 "$D/packed_swerve/" "$SRV":'~/sunhong/nav-vla/data/course/packed_swerve/' || exit 4
[ -d "$D/packed_swerve_heldout" ] && rsync -a --info=progress2 "$D/packed_swerve_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_swerve_heldout/'
scp -q $WS/server/code/train_reasoning.py "$SRV":'~/sunhong/nav-vla/code/' || exit 4
scp -q $WS/server/code/course/convert_v33s.sh $WS/server/code/course/launch_r33.sh "$SRV":'~/sunhong/nav-vla/code/course/' || exit 4
step "convert v33s"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v33s.sh 2>&1 | grep -v "Svt\|mp4 @\|Map:" | tail -8' || { echo CONVERT_FAIL; exit 5; }
[ "${SKIP_TRAIN:-0}" = 1 ] && exit 0
step "launch r33 (GPU${GPU:-1})"
ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=${GPU:-1} STEPS=${STEPS:-8000} bash code/course/launch_r33.sh" || exit 6
sleep 180
ssh "$SRV" 'cd ~/sunhong/nav-vla; grep -E "reasoning checkpoint|obstacle boost|GO-transition|dataset:|Traceback" logs/course/navvla_reasoning_r33.log | head -5; tail -c 300 logs/course/navvla_reasoning_r33.log | tr "\r" "\n" | tail -2'

step "정리 (로컬 캐시·로그 + 서버 스테이징/완료 런 중간 체크포인트)"
bash $WS/tools/cleanup_artifacts.sh --server | tail -6

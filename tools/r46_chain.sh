#!/bin/bash
# boxpair2(재처리 155 ep) 라벨·전송 → v46r 변환 → r46 학습(GPU1) → r45 평가 끝나면 같은 20 곳 평가 (2026-10-02)
#   bash tools/r46_chain.sh ; tail -f eval_out/course/r46_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r46_chain.log
if [ "${R46_CHILD:-0}" != 1 ]; then
  R46_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
D=$WS/src/sant_vla_pkg/data_course_multiobj

step "label + ship packed_boxpair2"
[ -f "$D/packed_boxpair2/index.jsonl" ] || { echo "[r46] packed_boxpair2 없음"; exit 1; }
python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D/packed_boxpair2" || exit 1
rsync -a "$D/packed_boxpair2/" "$SRV":"~/sunhong/nav-vla/data/course/packed_boxpair2/" || exit 1

step "ship code + convert v46r"
scp -q "$WS/server/code/course/convert_v46r.sh" "$WS/server/code/course/launch_r46.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
ssh "$SRV" 'df -h ~ | tail -1; cd ~/sunhong/nav-vla && bash code/course/convert_v46r.sh 2>&1 | grep -E "stanley|packed_|segment rows|CONVERT|Error|Traceback" | tail -8' || exit 3

step "train r46 (GPU1)"
ssh -n "$SRV" "cd ~/sunhong/nav-vla && GPU=1 bash code/course/launch_r46.sh" || exit 4
sleep 240
ssh "$SRV" "grep -E 'dataset:|twin|sampled share|obstacle boost|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r46.log | head -6"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r46.log" 2>/dev/null; do sleep 120; done
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r46.log" || { echo "[r46] train fail"; exit 5; }
ssh "$SRV" "grep 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r46.log"

step "wait r45 eval"
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r45.log" 2>/dev/null; do sleep 60; done
sleep 30
pgrep -af 'gz si[m]|avoidance_tria[l]' && { echo "[r46] stack still running"; sleep 120; }

step "stat eval r46 (20 positions)"
RUN=r46 NPOS=20 BATCH=20 bash "$WS/tools/eval/stat_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r46.log" 2>/dev/null; do sleep 30; done
sed -n '/collected/,$p' "$WS/eval_out/course/stat_r46.log"
echo "[r46] END $(date '+%F %T')"

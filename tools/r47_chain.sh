#!/bin/bash
# R2 (2026-10-02): 다물체 짝(packed_mpair) 수집·전송 대기 → v47r 변환 → r47 학습(GPU1)
# → r41 정답 문구 빈 차선 재평가 끝나면 같은 20 곳 × 5 조건(박스 / 미학습 사람 / 미학습 초록 차 / 옆 차선 / 빈 차선) 평가.
#   bash tools/r47_chain.sh ; tail -f eval_out/course/r47_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r47_chain.log
if [ "${R47_CHILD:-0}" != 1 ]; then
  R47_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
step() { echo; echo "======== [$(date +%T)] $1 ========"; }

step "wait mpair collection + ship"
until grep -qE '^\[pair\] (END|no packed|stack running)' "$WS/eval_out/course/mpair_collect_chain.log" 2>/dev/null; do sleep 60; done
grep -q '^\[pair\] shipped' "$WS/eval_out/course/mpair_collect_chain.log" || { echo "[r47] mpair not shipped"; tail -5 "$WS/eval_out/course/mpair_collect_chain.log"; exit 1; }

step "ship code + convert v47r"
scp -q "$WS/server/code/course/convert_v47r.sh" "$WS/server/code/course/launch_r47.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
ssh "$SRV" 'df -h ~ | tail -1; cd ~/sunhong/nav-vla && bash code/course/convert_v47r.sh 2>&1 | grep -E "stanley|packed_|segment rows|CONVERT|Error|Traceback" | tail -9' || exit 3

step "train r47 (GPU1)"
ssh -n "$SRV" "cd ~/sunhong/nav-vla && GPU=1 bash code/course/launch_r47.sh" || exit 4
sleep 240
ssh "$SRV" "grep -E 'dataset:|twin|sampled share|obstacle boost|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r47.log | head -6"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r47.log" 2>/dev/null; do sleep 120; done
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r47.log" || { echo "[r47] train fail"; exit 5; }
ssh "$SRV" "grep 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r47.log; df -h ~ | tail -1"

step "wait r41or empty rerun"
until grep -qE '^\[rr\] (END|stack running)' "$WS/eval_out/course/r41or_empty_rerun.log" 2>/dev/null; do sleep 60; done
sleep 30
pgrep -af 'gz si[m]|avoidance_tria[l]' && { echo "[r47] stack still running"; sleep 120; }

step "stat eval r47 (20 positions x 5)"
RUN=r47 NPOS=20 BATCH=20 CONDS="ours held heldcar adj empty" bash "$WS/tools/eval/stat_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r47.log" 2>/dev/null; do sleep 30; done
sed -n '/collected/,$p' "$WS/eval_out/course/stat_r47.log"
echo "[r47] END $(date '+%F %T')"

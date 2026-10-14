#!/bin/bash
# r44 학습 완료 대기 → 무작위 20 곳 × 우리 차선/옆 차선/빈 차선 (2026-10-02, 13 시 전 확인용 축소 평가)
#   bash tools/r44_chain.sh ; tail -f eval_out/course/r44_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r44_chain.log
if [ "${R44_CHILD:-0}" != 1 ]; then
  R44_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
echo "[r44] $(date +%T) wait for training"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r44.log" 2>/dev/null; do sleep 60; done
ssh "$SRV" "grep -E 'dataset:|twin|obstacle boost|done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r44.log"
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r44.log" || { echo "[r44] train fail"; exit 1; }
until ! pgrep -f 'div_ru[n].sh' >/dev/null; do echo "[r44] 수집 중 — 대기"; sleep 30; done
RUN=r44 NPOS=20 BATCH=20 bash "$WS/tools/eval/stat_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r44.log" 2>/dev/null; do sleep 30; done
sed -n '/collected/,$p' "$WS/eval_out/course/stat_r44.log"
echo "[r44] END $(date +%T)"

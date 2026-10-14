#!/bin/bash
# r41 정답 문구 빈 차선 재평가 (오라클 none 버그 수정 후). 다물체 짝 수집이 끝난 뒤(시뮬 공유 금지).
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r41or_empty_rerun.log
if [ "${RR_CHILD:-0}" != 1 ]; then
  RR_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
echo "[rr] $(date +%T) wait for mpair collection"
until grep -qE '^\[pair\] (END|no packed|stack running)' "$WS/eval_out/course/mpair_collect_chain.log" 2>/dev/null; do sleep 60; done
sleep 30
pgrep -af 'gz si[m]|episode_recorde[r]|avoidance_tria[l]' && { echo "[rr] stack running — stop"; exit 2; }
cd "$WS" && RUN=r41or CKPT_RUN=r41 TRIAL_EXTRA=--oracle-situation NPOS=20 BATCH=20 CONDS=empty ST_CHILD=1 \
  bash tools/eval/stat_eval.sh
echo "[rr] END $(date '+%F %T')"

#!/bin/bash
# r47 평가가 끝나면 다장애물 시범 6 바퀴(장애물 있음 v1 + 같은 자리 빈 트랙 v0) 자동 시작 (2026-10-02 사용자 승인).
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/mpilot_after_r47.log
if [ "${MP_CHILD:-0}" != 1 ]; then
  MP_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
echo "[mp] $(date +%T) wait r47 chain"
until grep -qE '^\[r47\] (END|train fail|mpair not shipped)|exit [0-9]' "$WS/eval_out/course/r47_chain.log" 2>/dev/null \
      || ! pgrep -f 'r47_chai[n].sh' >/dev/null; do sleep 60; done
tail -3 "$WS/eval_out/course/r47_chain.log"
grep -q MULTI_GROUPS "$WS/tools/collect_multiobj_avoid.sh" || { echo "[mp] collect_multiobj_avoid.sh 에 MULTI_GROUPS 미반영 — 중단"; exit 2; }
sleep 30
pgrep -af 'gz si[m]|avoidance_tria[l]|episode_recorde[r]' && { echo "[mp] stack running — 중단"; exit 3; }
TAG=mpilot NRUNS=6 OB_VARIANTS=v0,v1 MC_CHILD=1 bash "$WS/tools/multi_chain.sh"
echo "[mp] END $(date '+%F %T')"

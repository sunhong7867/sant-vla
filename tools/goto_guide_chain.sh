#!/bin/bash
# goto 증폭(guidance) 폐루프 시험 (2026-10-04): r52 30k, 쉬운 짝 배치 E
# (물체 2 개 좌우 14~25°, 같은 장면에 "left"/"right") 를 w=1 과 w=3 으로.
#   bash tools/goto_guide_chain.sh   (setsid nohup, 로그 eval_out/course/goto_guide_chain.log)
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_guide_chain.log
if [ "${GC_CHILD:-0}" != 1 ]; then
  GC_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
for w in ${GUIDES:-1.0 3.0}; do
  echo; echo "======== [$(date '+%F %T')] E guide w=$w ========"
  tag=r52_030000_g${w%.*}
  RUN=r52 STEP=030000 TAG=$tag POLICY_GUIDE=$w N=${N:-40} TIERS="E" GE_CHILD=1 \
    bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_$tag.log" 2>&1
  sed -n '/^== /,$p' "$WS/eval_out/course/goto_$tag.log"
done
echo "[gc] END $(date '+%F %T')"

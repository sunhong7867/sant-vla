#!/bin/bash
# 빈 차선 대조 (2026-10-01). 장애물 없이(가상 장애물 none: 스폰 안 함, 궤적 기준점만) 같은 자리를 지나가게 해
# "장애물을 보고 꺾는가 / 이 자리에서 꺾는가" 를 가른다. self_perception_eval 과 같은 설정(문구 없음, cbs10).
#   RUNS="sw80 sw40 sw20 sw10 sw5 r42" bash tools/eval/empty_lane_control.sh
#   tail -f eval_out/course/empty_lane_control.log
# WAIT_SWEEP=1 이면 스윕 체인이 끝날 때까지 기다렸다가 시작.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/empty_lane_control.log
if [ "${EL_CHILD:-0}" != 1 ]; then
  EL_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
RUNS=${RUNS:-"sw80 sw40 sw20 sw10 sw5 r42"}
SPOTS=${SPOTS:-"lane2:0.1725 lane2:0.35"}
VL=$WS/eval_out/course/r40_variants.log
if [ "${WAIT_SWEEP:-0}" = 1 ]; then
  until grep -q '^\[sweep\] END' "$WS/eval_out/course/sweep_chain.log" 2>/dev/null; do sleep 60; done
fi
echo "[empty] $(date '+%F %T') RUNS=$RUNS"
for run in $RUNS; do
  for spot in $SPOTS; do
    RUN=$run SITUATION=0 ORACLE=0 VARIANTS=cbs10 MODELS=none SPOT=$spot TAGX="_empty_${spot/:/_}" \
      bash "$WS/tools/eval/r40_bridge_variants.sh" > /dev/null
    sleep 5
    until grep -q "ALL_DONE" "$VL" 2>/dev/null; do sleep 10; done
    echo "== $run @ $spot"; grep -E -- "->|BRINGUP_FAIL" "$VL"
  done
done
echo; echo "[empty] traces"
python3 "$WS/tools/eval/trace_view.py" "$WS"/eval_out/course/multiobj_eval/trials/*_cbs10_empty_*.log
echo "[empty] ALL_DONE $(date +%T)"

#!/bin/bash
# r40 폐루프: 브리지 후처리 변형 비교 (2026-09-30). 박스 × N, 변형마다 스택 재기동.
#   bash tools/eval/r40_bridge_variants.sh ; tail -f eval_out/course/r40_variants.log
# 변형: base(기본 refill 0.3, curv_boost_slow 0.85) / refill06 / cbs10.
# 궤적은 트라이얼 로그의 TRACE 줄, 서빙 문구는 서버 logs/situation_serve.jsonl ("t" 로 맞춤).
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r40_variants.log
if [ "${R40V_CHILD:-0}" != 1 ]; then
  R40V_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-eval70}
export NAVVLA_SITUATION=${SITUATION:-1}
# ORACLE=1: 좌표 정답 상황 문구(avoidance_trial --oracle-situation). 서버 문구와 중복되지 않게 SITUATION=0 강제
if [ "${ORACLE:-0}" = 1 ]; then export NAVVLA_SITUATION=0 TRIAL_EXTRA="--oracle-situation"; fi
RUN=${RUN:-r40}                      # r38 = 상황 문구 없는 대조군 (SITUATION=0 과 함께)
VARIANTS=${VARIANTS:-"base refill06 cbs10"}
for v in $VARIANTS; do
  unset REFILL_AT CURV_BOOST_SLOW
  case $v in
    base) ;;
    refill06) export REFILL_AT=0.6 ;;
    cbs10) export CURV_BOOST_SLOW=1.0 ;;
    *) echo "unknown variant $v"; continue ;;
  esac
  echo "[r40v] $(date +%T) $RUN sit=$NAVVLA_SITUATION oracle=${ORACLE:-0} spot=${SPOT:-lane2:0.1725} $v REFILL_AT=${REFILL_AT:-0.3} CURV_BOOST_SLOW=${CURV_BOOST_SLOW:-0.85} (RAM $(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)G)"
  CKPT=runs/course/navvla_reasoning_${RUN}/checkpoints/last/pretrained_model \
  MODELS=${MODELS:-ob_box} N=${N:-2} SPOTS=${SPOT:-lane2:0.1725} START_OFF=0.155 SPEED="${SPEED:-slowly}" \
    bash "$WS/tools/eval/multiobj_heldout_eval.sh" "${RUN}_${v}${TAGX:-}"
  echo "[r40v] $(date +%T) $v rc=$?"
  sleep 10
done
echo "[r40v] ALL_DONE $(date +%T)"

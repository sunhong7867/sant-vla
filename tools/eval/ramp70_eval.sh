#!/bin/bash
# r38/r39 (장애물 lane2 70 학습) 폐루프 평가 — 감독 없이 정책 자체 반응.
#   bash tools/eval/ramp70_eval.sh              # r38 → r39, 백그라운드로 떠남
#   RUNS="r39" SPEED="at a normal speed" bash tools/eval/ramp70_eval.sh
# 위치: lane2 frac 0.1725 = 인덱스 70, 출발 frac 0.0175 = 인덱스 7 (약 22 m 앞, 왼쪽 직선).
# 모델당 8 트라이얼(물체 4 × 2) — gz create 는 스택당 약 8 회 넘으면 wedge.
# 수집과 같은 이유로 ROS_DOMAIN_ID / GZ_PARTITION 을 분리한다.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/ramp70_eval.log
if [ "${RAMP70_EVAL_CHILD:-0}" != 1 ]; then
  RAMP70_EVAL_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-eval70}
RUNS=${RUNS:-r38 r39}
# SITUATION=1: 해설로 동작 조건화 서빙(r40+). smolvla_demo.sh 가 NAVVLA_SITUATION 을 읽는다
export NAVVLA_SITUATION=${SITUATION:-0}
SUFFIX=${SUFFIX:-70}
for r in $RUNS; do
  AVAIL=$(awk '/MemAvailable/ {print $2/1048576}' /proc/meminfo)
  echo "[ramp70-eval] $(date +%T) $r 시작 (가용 RAM ${AVAIL}G)"
  MODELS=${MODELS:-ob_box,hatchback_red,ob_person,ob_barrel} N=${N:-2} \
    SPOTS=lane2:0.1725 START_OFF=0.155 SPEED="${SPEED:-slowly}" \
    bash "$WS/tools/eval/multiobj_heldout_eval.sh" "${r}_${SUFFIX}"
  echo "[ramp70-eval] $(date +%T) $r rc=$?"
  sleep 10
done
echo "[ramp70-eval] ALL_DONE $(date +%T)"

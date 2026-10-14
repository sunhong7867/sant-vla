#!/bin/bash
# 모델 스스로 장애물을 판단하는 폐루프 평가 (2026-10-01). 좌표 정답 문구 없음.
#   RUN=r41 SIT=1 bash tools/eval/self_perception_eval.sh   # B: 모델 자신의 해설 → 상황 문구 (--situation-from-reasoning)
#   RUN=r42 SIT=0 bash tools/eval/self_perception_eval.sh   # A: 순수 end-to-end (문구 없음)
#   tail -f eval_out/course/self_<RUN>.log
# 조건: 박스 × (인덱스 70, 142) × (우리 차선, 옆 차선) + 사람(학습 안 함) × (70, 142) 우리 차선, 각 N=2,
# curv_boost_slow 1.0 (CURV 로 변경). 판정: 우리 차선 회피 + 옆 차선 유지. 크기 아는 물체는 차체 겹침만으로 충돌 판정.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
RUN=${RUN:?RUN=r41|r42}
LOG=$WS/eval_out/course/self_${RUN}.log
if [ "${SELF_CHILD:-0}" != 1 ]; then
  SELF_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
SIT=${SIT:-0}
CURV=${CURV:-1.0}
VARIANT=cbs10; [ "$CURV" = 0.85 ] && VARIANT=base
VL=$WS/eval_out/course/r40_variants.log
MATRIX=${MATRIX:-"ob_box:lane2:0.1725 ob_box:lane1:0.1725 ob_box:lane2:0.35 ob_box:lane1:0.35 ob_person:lane2:0.1725 ob_person:lane2:0.35"}
echo "[self] $(date '+%F %T') RUN=$RUN SIT=$SIT curv_boost_slow=$CURV"
for cell in $MATRIX; do
  model=${cell%%:*}; spot=${cell#*:}
  tagx="_self_${model}_${spot/:/_}"
  RUN=$RUN SITUATION=$SIT ORACLE=0 VARIANTS=$VARIANT MODELS=$model SPOT=$spot TAGX=$tagx \
    bash "$WS/tools/eval/r40_bridge_variants.sh" > /dev/null
  sleep 5
  until grep -q "ALL_DONE" "$VL" 2>/dev/null; do sleep 10; done
  echo "== $model @ $spot"
  grep -E -- "->|BRINGUP_FAIL" "$VL"
done
echo; echo "[self] traces"
python3 "$WS/tools/eval/trace_view.py" "$WS"/eval_out/course/multiobj_eval/trials/${RUN}_${VARIANT}_self_*.log
echo "[self] ALL_DONE $(date +%T)"

#!/bin/bash
# 대량 폐루프 평가 (2026-10-01). 같은 자리 반복은 결과가 거의 같아(sw80 70: 2.79/2.63 m) 정보가 없으므로
# **무작위 위치 NPOS 곳** × 조건 3 개, 각 1 회:
#   ours  = 박스 우리 차선(lane2)  → 회피해야 함
#   adj   = 박스 옆 차선(lane1), 같은 위치 → 차선 유지해야 함
#   empty = 장애물 없음(가상 none), 같은 위치 → 꺾으면 위치 습관
# 출발은 장애물 frac − 0.155 (약 24 m, 기존 평가와 같음), 문구 없음, curv_boost_slow 1.0.
# BATCH 곳마다 스택 재기동(gz wedge 대비). 결과: eval_out/course/multiobj_eval/<RUN>_st_<cond>_b<k>.jsonl + trials/
#   RUN=sw80 NPOS=100 bash tools/eval/stat_eval.sh ; tail -f eval_out/course/stat_<RUN>.log
#   분석: python3 tools/eval/stat_analyze.py sw80
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
RUN=${RUN:?RUN=sw80 등}
LOG=$WS/eval_out/course/stat_${RUN}.log
if [ "${ST_CHILD:-0}" != 1 ]; then
  ST_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-stat}
export NAVVLA_SITUATION=0 CURV_BOOST_SLOW=1.0
export KEEP_TRIALS=100000   # cleanup_artifacts 가 트라이얼 로그를 최근 40 개만 남겨 r43 궤적이 지워졌음 (2026-10-02)
NPOS=${NPOS:-100}; BATCH=${BATCH:-25}; SEED=${SEED:-20261002}
CONDS=${CONDS:-"ours adj empty"}
POS=$WS/eval_out/course/stat_${RUN}_positions.txt
# 위치: lane frac 0.16~0.99 균등 무작위 (출발이 0 밑으로 잘리지 않게), 모든 RUN 이 같은 SEED 면 같은 위치
python3 -c "
import random; r = random.Random($SEED)
print('\n'.join('%.4f' % r.uniform(0.16, 0.99) for _ in range($NPOS)))" > "$POS"
echo "[stat] $(date '+%F %T') RUN=$RUN NPOS=$NPOS BATCH=$BATCH SEED=$SEED conds=$CONDS"

ram_ok() {
  while :; do
    AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
    awk -v a="$AV" 'BEGIN{exit !(a>=5.3)}' && return
    echo "[stat] $(date +%T) RAM ${AV}G < 5.3G — 대기"; sleep 60
  done
}
mapfile -t FR < "$POS"
k=0
for ((i = 0; i < NPOS; i += BATCH)); do
  k=$((k + 1))
  for cond in $CONDS; do
    elane=lane2   # ego start lane; *1 conditions start in lane1 (swerve right, 2026-10-02 multi-obstacle runs)
    case $cond in
      ours1)  elane=lane1; lane=lane1; model=ob_box ;;
      adj1)   elane=lane1; lane=lane2; model=ob_box ;;
      empty1) elane=lane1; lane=lane1; model=none ;;
      held1)  elane=lane1; lane=lane1; model=ob_person ;;
      ours)  lane=lane2; model=ob_box ;;
      adj)   lane=lane1; model=ob_box ;;
      empty) lane=lane2; model=none ;;
      held)  lane=lane2; model=ob_person ;;        # 미학습 물체 (R2, 다물체 짝 학습에 없음)
      heldcar) lane=lane2; model=hatchback_green ;; # 미학습 물체 — 학습한 hatchback_red 와 색만 다름
    esac
    spots=$(printf "%s\n" "${FR[@]:i:BATCH}" | sed "s/^/$lane:/" | paste -sd,)
    tag="${RUN}_st_${cond}_b${k}"
    [ -s "$WS/eval_out/course/multiobj_eval/$tag.jsonl" ] && [ "$(wc -l < "$WS/eval_out/course/multiobj_eval/$tag.jsonl")" -ge "$(echo "$spots" | tr , '\n' | wc -l)" ] \
      && { echo "[stat] $tag 이미 있음 — 건너뜀"; continue; }
    ram_ok
    echo "[stat] $(date +%T) $tag (${BATCH} spots, RAM ${AV}G)"
    CKPT=runs/course/navvla_reasoning_${CKPT_RUN:-$RUN}/checkpoints/last/pretrained_model \
    TRIAL_EXTRA="${TRIAL_EXTRA:-} --start-lane $elane" \
    MODELS=$model N=1 SPOTS=$spots START_OFF=0.155 SPEED=slowly \
      bash "$WS/tools/eval/multiobj_heldout_eval.sh" "$tag" 2>&1 | grep -E -- '->|BRINGUP|원격' | sed "s/^/[$cond] /"
    sleep 10
  done
done
echo "[stat] $(date +%T) collected"
python3 "$WS/tools/eval/stat_analyze.py" "$RUN"
echo "[stat] ALL_DONE $(date +%T)"

#!/bin/bash
# 스윕 마무리 (2026-10-01): 가용 RAM 이 5 G 이상이 될 때까지 기다렸다가 sw5 평가 → 빈 차선 대조.
# 21:00 에 노트북 RAM 4.2 G 로 sw5 평가가 BRINGUP_FAIL(데모 RAM 가드 5 G) 난 것을 이어서 돌린다.
#   bash tools/eval/sweep_finish.sh ; tail -f eval_out/course/sweep_finish.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sweep_finish.log
if [ "${SF_CHILD:-0}" != 1 ]; then
  SF_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
wait_ram() {
  local last=0
  while :; do
    AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
    awk -v a="$AV" 'BEGIN{exit !(a>=5.3)}' && { echo "[finish] $(date +%T) RAM ${AV}G — 진행"; return; }
    [ $(( $(date +%s) - last )) -ge 600 ] && { echo "[finish] $(date +%T) RAM ${AV}G < 5.3G — 대기"; last=$(date +%s); }
    sleep 30
  done
}
wait_ram
RUN=sw5 SIT=0 bash "$WS/tools/eval/self_perception_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/self_sw5.log" 2>/dev/null; do sleep 30; done
grep -E '^== |->|BRINGUP' "$WS/eval_out/course/self_sw5.log" | grep -v '\.log'
wait_ram
bash "$WS/tools/eval/empty_lane_control.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/empty_lane_control.log" 2>/dev/null; do sleep 30; done
grep -E '^== |->|BRINGUP' "$WS/eval_out/course/empty_lane_control.log" | grep -v '\.log'
echo "[finish] ALL_DONE $(date +%T)"

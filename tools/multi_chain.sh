#!/bin/bash
# 다장애물 주행 수집 체인 (2026-10-02): 수집(performance) → balanced → 라벨 → 서버 전송·개수 확인 → 로컬 정리.
# 정리: 시뮬 캐시·로그만(gz 로그, tools/sim_log_janitor.sh 도 같이 띄움). 원본 세션(데이터)은 지우지 않는다.
#   TAG=mpilot NRUNS=6 bash tools/multi_chain.sh                 # 시범
#   TAG=mrun NRUNS=120 bash tools/multi_chain.sh                 # 본 수집
#   tail -f eval_out/course/multi_chain_<TAG>.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
TAG=${TAG:-mrun}
LOG=$WS/eval_out/course/multi_chain_${TAG}.log
if [ "${MC_CHILD:-0}" != 1 ]; then
  MC_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
D=$WS/src/sant_vla_pkg/data_course_multiobj
P=$D/packed_$TAG
balanced() { powerprofilesctl set balanced 2>/dev/null; echo "[mc] power -> $(powerprofilesctl get 2>/dev/null)"; }
pgrep -af 'gz si[m]|episode_recorde[r]|avoidance_tria[l]' && { echo "[mc] stack running — stop"; exit 2; }
bash "$WS/tools/sim_log_janitor.sh"
echo "[mc] $(date '+%F %T') TAG=$TAG NRUNS=${NRUNS:-120} disk $(df -h ~ | awk 'NR==2{print $4}') free"
powerprofilesctl set performance; echo "[mc] power -> $(powerprofilesctl get)"
TAG=$TAG NRUNS=${NRUNS:-120} DIV_CHILD=1 bash "$WS/tools/multi_run.sh" > "$WS/eval_out/course/div_run_${TAG}.log" 2>&1
RC=$?
balanced
tail -4 "$WS/eval_out/course/div_run_${TAG}.log"
[ -f "$P/index.jsonl" ] || { echo "[mc] no packed (rc $RC)"; exit 3; }
python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$P" | tail -2 || exit 4
rsync -a "$P/" "$SRV":"~/sunhong/nav-vla/data/course/packed_$TAG/" || exit 5
NL=$(find "$P" -name reasoning.jsonl | wc -l)
NR=$(ssh "$SRV" "find ~/sunhong/nav-vla/data/course/packed_$TAG -name reasoning.jsonl | wc -l")
echo "[mc] shipped: local $NL, server $NR labelled episodes"
[ "$NL" -gt 0 ] && [ "$NL" = "$NR" ] || { echo "[mc] ship mismatch — 원본 보존"; exit 6; }
# --- 정리 ---------------------------------------------------------------
rm -rf ~/.gz/sim/log/* 2>/dev/null
echo "[mc] disk $(df -h ~ | awk 'NR==2{print $4}') free"
echo "[mc] END $(date '+%F %T')"

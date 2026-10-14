#!/bin/bash
# 박스 짝 수집 (2026-10-02): 같은 출발·같은 위치에서 v1(우리 차선 회피) + v2(옆 차선 직진) = 반반 (사용자 설계).
# 위치 라벨 = ego PosePublisher 스트림(POSE_SOURCE=cli, 수율 수정). r44 평가가 끝난 뒤 시작(시뮬 공유 금지).
#   bash tools/pair_collect_chain.sh ; tail -f eval_out/course/pair_collect_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/pair_collect_chain.log
if [ "${PC_CHILD:-0}" != 1 ]; then
  PC_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
D=$WS/src/sant_vla_pkg/data_course_multiobj
NGROUPS=${NGROUPS:-120}
balanced() { powerprofilesctl set balanced 2>/dev/null; echo "[pair] power -> $(powerprofilesctl get 2>/dev/null)"; }
echo "[pair] $(date +%T) wait for r44 eval"
until grep -qE '^\[r44\] (END|train fail)' "$WS/eval_out/course/r44_chain.log" 2>/dev/null; do sleep 60; done
pgrep -af 'gz si[m]|episode_recorde[r]|avoidance_tria[l]' && { echo "[pair] stack running — stop"; exit 2; }
powerprofilesctl set performance; echo "[pair] $(date +%T) power -> $(powerprofilesctl get)"
TAG=boxpair TRAIN_MODELS=ob_box HELDOUT_MODELS=ob_person TRAIN_GROUPS=$NGROUPS HELDOUT_GROUPS=0 \
  OB_VARIANTS=v1,v2 SEED_TRAIN=20261050 POSE_SOURCE=cli bash "$WS/tools/div_run.sh"
sleep 5
until grep -qE "ALL_DONE|없음|RAM 중단|이미 있음" "$WS/eval_out/course/div_run_boxpair.log" 2>/dev/null; do sleep 60; done
tail -4 "$WS/eval_out/course/div_run_boxpair.log"
balanced
[ -f "$D/packed_boxpair/index.jsonl" ] || { echo "[pair] no packed"; exit 3; }
python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D/packed_boxpair" || exit 3
rsync -a "$D/packed_boxpair/" "$SRV":'~/sunhong/nav-vla/data/course/packed_boxpair/' && echo "[pair] shipped"
echo "[pair] END $(date '+%F %T')"

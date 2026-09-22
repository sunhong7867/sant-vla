#!/bin/bash
# v10 속도-불변 순항 코퍼스 — 티어(70/110/150)×차선(1/2) 균등, 오라클 선생.
#
# 배경(docs/ver/20260914_1712): YOLO 선생은 1차선 110/150에서 양자화 조향
# 위빙으로 9~20% 밟음 — 파라미터·평활로 안 잡힘. route_oracle은
# lookahead_gain 0.6에서 전 매트릭스 무접촉(최대 0.63 m) 실측 통과.
# v10은 그 오라클로 모든 티어의 깨끗한 라인을 재시연한다.
#
#   bash tools/collect_v10p.sh          # 본수집 36그룹(72ep) + heldout 6그룹
#   V10_GROUPS=6 V10_NHELD=0
LG=${LG:-0.4} bash tools/collect_v10p.sh   # 스모크
WS=/home/sh/ROS2_project/sant-vla
OUT=$WS/eval_out/stanley
DATA=$WS/src/sant_vla_pkg/data_stanley
NGROUPS=${ST_GROUPS:-48}
NHELD=0
LG=${LG:-0.4}
# v9 교훈 재발(2026-09-14: 스모크가 1000그룹 계획으로 폭주) — 상한 가드.
[ "$NGROUPS" -le 130 ] 2>/dev/null || { echo "[st] NGROUPS=$NGROUPS > 60 — 거부"; exit 2; }
[ "$NHELD" -le 20 ] 2>/dev/null || { echo "[st] NHELD=$NHELD > 20 — 거부"; exit 2; }
SEED=${V10_SEED:-20260915}
mkdir -p "$OUT" "$DATA"
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

AVAIL=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
[ "$AVAIL" -ge 3 ] || { echo "[st] 가용 RAM ${AVAIL}G < 3G — 앱을 닫고 재시도"; exit 4; }

# 수집은 독점 스택: 데모(GUI/브리지/내레이터)까지 전부 내린다.
pat='chat_gui_nod';      pkill -9 -f "${pat}e"        2>/dev/null
pat='vla_narrato';       pkill -9 -f "${pat}r.py"     2>/dev/null
pat='vla_bridge_nod';    pkill -f "${pat}e"           2>/dev/null
pat='navigator_nod';     pkill -f "${pat}e"           2>/dev/null
pat='yolov8_nod';        pkill -f "${pat}e"           2>/dev/null
pat='lane_info_extracto'; pkill -f "${pat}r"          2>/dev/null
pat='lidar_obstacle_detecto'; pkill -f "${pat}r"      2>/dev/null
pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='route_oracle_nod';  pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
pat='collect_corpu';     pkill -f "${pat}s.py"        2>/dev/null
pat='parameter_bridg';   pkill -f "${pat}e"           2>/dev/null
for _ in $(seq 1 10); do
  pgrep -f "gz si[m]|route_oracle_nod[e]|episode_recorde[r]|vla_bridge_nod[e]" >/dev/null || break
  sleep 1
done
ros2 daemon stop >/dev/null 2>&1
sleep 3
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* 2>/dev/null

echo "[st] 시뮬 기동..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py \
  use_camera:=true use_perception_pipeline:=false use_driver:=false \
  use_policy:=false use_debug_visualizers:=false use_vla_camera:=false \
  > "$OUT/sim.log" 2>&1 < /dev/null &
for _ in $(seq 1 24); do
  N=$(timeout 5 ros2 topic list 2>/dev/null | grep -c "camera/image_raw")
  [ "${N:-0}" -ge 1 ] && break
  sleep 5
done
[ "${N:-0}" -ge 1 ] || { echo "[st] SIM_FAIL"; exit 3; }

echo "[st] 오라클(lg=0.6)+레코더 기동..."
setsid nohup ros2 run sant_vla_pkg route_oracle_node --ros-args \
  -p use_sim_time:=true -p lookahead_gain:=$LG -p controller:=${CTRL:-stanley} -p stanley_k:=${SK:-1.0} \
  > "$OUT/oracle.log" 2>&1 < /dev/null &
setsid nohup ros2 run sant_vla_pkg episode_recorder_node --ros-args \
  -p out_dir:="$DATA" -p use_sim_time:=true > "$OUT/recorder.log" 2>&1 < /dev/null &
sleep 5

run_batch() {  # $1 groups  $2 prefix  $3 split  $4 pack_dir
  echo "[st] 수집 시작 ($(date +%H:%M)) — $1그룹 ($3)..."
  python3 $WS/src/sant_vla_pkg/scripts/collect_corpus.py \
    --driver oracle --groups 0 --speed-groups 0 --floor-groups 0 \
    --ring-groups 0 --obstacle-groups 0 --cruise-groups "$1" \
    --cruise-lane match --split "$3" \
    --group-prefix "$2" --seed "$SEED" --out-dir "$DATA" --lat-jitter 0.0 --yaw-jitter 0 \
    >> "$OUT/collect.log" 2>&1
  RC=$?
  echo "[st] 배치 종료 rc=$RC"
  tail -6 "$OUT/collect.log"
  [ "$RC" -eq 0 ] || return "$RC"
  SESS=$(ls -dt "$DATA"/session_* 2>/dev/null | head -1)
  [ -n "$SESS" ] || { echo "[st] 세션 없음"; return 5; }
  echo "[st] finalize: $SESS -> $4"
  PACK_OUT=$4 bash $WS/src/sant_vla_pkg/scripts/finalize_corpus.sh "$SESS" \
    >> "$OUT/finalize.log" 2>&1 \
    && echo "[st] finalize 완료 -> $4" \
    || { echo "[st] finalize 실패 — $OUT/finalize.log"; return 6; }
}

run_batch "$NGROUPS" "st_" train "$DATA/packed_stanley" || exit $?
if [ "$NHELD" -gt 0 ]; then
  run_batch "$NHELD" "v10h_" heldout "$DATA/packed_v10_heldout" || exit $?
fi

pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='route_oracle_nod';  pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
sleep 3
rm -rf ~/.gz/sim/log
echo "[st] DONE"

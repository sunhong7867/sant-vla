#!/bin/bash
# 코퍼스 v8 야간 수집 — 축소 차 스케일, 방향·직행 축 포함 (~222 eps, ~2.5h)
# 이후 finalize(검증→10Hz 리샘플→CMI→패키징)까지 자동 진행.
#
#   ./tools/collect_v8_overnight.sh          # 전체 실행 (백그라운드 권장)
#
# 구성: CCW 순항 30그룹 + CW 순항 30 + 존 이동 20 + 직행 25 + 노이즈 바닥 6
WS=/home/sh/ROS2_project/sant-vla
OUT=$WS/eval_out/v8_collect
DATA=$WS/src/sant_vla_pkg/data_v8
mkdir -p "$OUT" "$DATA"
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='yolov8_nod';        pkill -f "${pat}e"           2>/dev/null
pat='navigator_nod';     pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
pat='collect_corpu';     pkill -f "${pat}s.py"        2>/dev/null
pat='vla_policy_serve';  pkill -f "${pat}r"           2>/dev/null
pat='vla_bridge_nod';    pkill -f "${pat}e"           2>/dev/null
pat='chat_gui_nod';      pkill -f "${pat}e"           2>/dev/null
pat='parameter_bridg';   pkill -f "${pat}e"           2>/dev/null
for _ in $(seq 1 10); do
  pgrep -f "gz si[m]|yolov8_nod[e]|navigator_nod[e]|episode_recorde[r]|vla_bridge_nod[e]" >/dev/null || break
  sleep 1
done
ros2 daemon stop >/dev/null 2>&1
sleep 3
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* 2>/dev/null

echo "[v8] 시뮬+욜로 기동..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py \
  use_camera:=true use_perception_pipeline:=true use_driver:=true use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > "$OUT/sim.log" 2>&1 < /dev/null &
for _ in $(seq 1 24); do
  NPUB=$(timeout 5 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
  [ "${NPUB:-0}" -ge 1 ] && break
  sleep 5
done
[ "${NPUB:-0}" -ge 1 ] || { echo "[v8] 시뮬 기동 실패"; exit 3; }

echo "[v8] 내비게이터+레코더 기동..."
setsid nohup ros2 run sant_vla_pkg navigator_node > "$OUT/navigator.log" 2>&1 < /dev/null &
# use_sim_time 필수: 프레임 t는 이미지 header.stamp(심 시간)라, 노드 클록이
# 벽시계면 포즈/컨트롤과 클록이 갈라져 리샘플이 전 에피소드를 거부한다 (2026-08-21 실증).
setsid nohup ros2 run sant_vla_pkg episode_recorder_node --ros-args \
  -p out_dir:="$DATA" -p use_sim_time:=true > "$OUT/recorder.log" 2>&1 < /dev/null &
sleep 5

echo "[v8] 본 수집 시작 ($(date +%H:%M))..."
python3 $WS/src/sant_vla_pkg/scripts/collect_corpus.py \
  --driver yolo --groups 0 --speed-groups 0 --floor-groups 6 \
  --cruise-groups 30 --cw-cruise-groups 30 --ring-groups 20 --direct-groups 25 \
  --group-prefix y8a --seed 20260821 \
  > "$OUT/collect.log" 2>&1
echo "[v8] 수집 종료 ($(date +%H:%M)) — 요약:"
tail -12 "$OUT/collect.log"

# 스택 정리 (시뮬 다운)
pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='yolov8_nod';        pkill -f "${pat}e"           2>/dev/null
pat='navigator_nod';     pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
sleep 3
rm -rf ~/.gz/sim/log

# finalize: 레코더 데이터 세션 디렉토리에 대해 실행
SESS=$(ls -dt "$DATA"/session_* 2>/dev/null | head -1)
if [ -n "$SESS" ]; then
  echo "[v8] finalize 시작: $SESS"
  PACK_OUT=$WS/src/sant_vla_pkg/data_v8/packed_v8 \
    bash $WS/src/sant_vla_pkg/scripts/finalize_corpus.sh "$SESS" \
    > "$OUT/finalize.log" 2>&1 \
    && echo "[v8] finalize 완료" || echo "[v8] finalize 실패 — $OUT/finalize.log 확인 (스테이지 수동 재개 가능)"
fi
echo "[v8] 전체 종료 ($(date +%H:%M))"

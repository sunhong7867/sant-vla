#!/bin/bash
# 욜로(인지판단제어) 스택 원클릭 기동 — smolvla_demo.sh 의 욜로판.
#
#   ./yolo_drive.sh          # 시뮬 + 욜로 파이프라인 자동주행 (기동 즉시 주행 시작)
#   ./yolo_drive.sh down     # 전체 종료 + gz 로그 정리
#
# 시각화 노드는 그래프 비교의 공정성을 위해 VLA 데모와 동일하게 끔.
# rqt_graph 캡처:  rqt_graph  (Nodes/Topics(active) 뷰)
WS="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOGD=$WS/eval_out/yolo_drive
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"

kill_stack() {
  pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
  pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
  pat='yolov8_nod';        pkill -f "${pat}e"           2>/dev/null
  pat='lane_info_extracto';pkill -f "${pat}r"           2>/dev/null
  pat='path_planner_nod';  pkill -f "${pat}e"           2>/dev/null
  pat='motion_planner_nod';pkill -f "${pat}e"           2>/dev/null
  pat='simulation_sende';  pkill -f "${pat}r"           2>/dev/null
  pat='vla_policy_serve';  pkill -f "${pat}r"           2>/dev/null
  pat='vla_bridge_nod';    pkill -f "${pat}e"           2>/dev/null
  pat='navigator_nod';     pkill -f "${pat}e"           2>/dev/null
  pat='vla_narrato';       pkill -f "${pat}r.py"        2>/dev/null
  pat='chat_gui_nod';      pkill -f "${pat}e"           2>/dev/null
  pat='parameter_bridg';   pkill -f "${pat}e"           2>/dev/null
  sleep 2
  pat='chat_gui_nod';      pkill -9 -f "${pat}e"        2>/dev/null
  # pkill은 비동기 — 이전 세션 노드가 완전히 죽기 전에 새 세션이 뜨면
  # 컨트롤러가 2개가 되어 /cmd_vel을 서로 뺏는다(차선 침범 사고의 실제 원인).
  # 전부 사라질 때까지 최대 10초 대기.
  for _ in $(seq 1 10); do
    pgrep -f "vla_bridge_nod[e]|navigator_nod[e]|chat_gui_nod[e]|vla_policy_serve[r]|simulation_sende[r]|motion_planner_nod[e]|yolov8_nod[e]|gz si[m]" >/dev/null || break
    sleep 1
  done
}

if [ "${1:-}" = "down" ]; then
  echo "[yolo] 전체 종료 중..."
  kill_stack
  sleep 3
  rm -rf ~/.gz/sim/log
  echo "[yolo] 종료 완료 (gz 로그 정리됨)"
  exit 0
fi

mkdir -p "$LOGD"
echo "[yolo] 이전 스택 정리 + DDS 초기화..."
kill_stack
ros2 daemon stop >/dev/null 2>&1
sleep 4
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* /dev/shm/cyclonedds* 2>/dev/null

echo "[yolo] 시뮬 + 욜로 파이프라인 기동 (약 30초, 기동되면 바로 자동주행)..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py \
  use_camera:=true use_perception_pipeline:=true use_driver:=true use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > "$LOGD/sim.log" 2>&1 < /dev/null &

# 욜로 가중치 로딩이 느려 /cmd_vel 발행까지 30~60초 걸림 — 발행 시작까지 폴링
echo "[yolo] 파이프라인 로딩 대기 (욜로 가중치 로딩 포함, 최대 120초)..."
for _ in $(seq 1 24); do
  NPUB=$(timeout 5 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
  [ "${NPUB:-0}" -ge 1 ] && break
  sleep 5
done
echo "[yolo] /cmd_vel 퍼블리셔 수: ${NPUB:-0}"
[ "${NPUB:-0}" -ge 1 ] || { echo "[yolo] 기동 실패 — $LOGD/sim.log 확인"; exit 3; }
echo
echo "[yolo] 기동 완료 — 욜로 스택이 자동주행 중입니다."
echo "[yolo] 그래프 캡처: 다른 터미널에서 rqt_graph 실행 (Nodes/Topics(active))"
echo "[yolo] 종료: ./yolo_drive.sh down"

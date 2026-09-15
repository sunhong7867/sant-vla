#!/bin/bash
# VLA 최소 주행 원클릭 — 채팅·내비게이터·내레이터 없이 e2e 순항만.
#
#   ./vla_drive.sh                 # 시뮬 + 정책서버 + 브리지, 기동 즉시 순항 시작
#   SENTENCE="Start driving in the outer lane, at a normal speed." ./vla_drive.sh
#   ./vla_drive.sh down            # 전체 종료 + gz 로그 정리
#
# rosgraph 비교용 최소 구성: 판단 노드는 vla_bridge 하나 (두뇌인 정책 서버는
# ZMQ 너머라 그래프에 안 보임). 나머지는 gz 브리지(시뮬-ROS 번역기)뿐.
WS="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOGD=$WS/eval_out/vla_drive
CKPT=${NAVVLA_CKPT:-$WS/models/ckpt_v6_60k}
VENV=${NAVVLA_VENV:-$HOME/venv/navvla}
POLICY_PYTHON=${NAVVLA_PYTHON:-$VENV/bin/python}
SENTENCE=${SENTENCE:-"Start driving in the inner lane, at a normal speed."}

source /opt/ros/${ROS_DISTRO:-jazzy}/setup.bash
source "$WS/install/setup.bash"

kill_stack() {
  pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
  pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
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
  echo "[vla] 전체 종료 중..."
  kill_stack
  sleep 3
  rm -rf ~/.gz/sim/log
  echo "[vla] 종료 완료 (gz 로그 정리됨)"
  exit 0
fi

[ -f "$CKPT/model.safetensors" ] || { echo "[vla] 체크포인트 없음: $CKPT"; exit 2; }
[ -x "$POLICY_PYTHON" ] || { echo "[vla] 정책 Python 없음: $POLICY_PYTHON"; exit 2; }
mkdir -p "$LOGD"

echo "[vla] 이전 스택 정리 + DDS 초기화..."
kill_stack
ros2 daemon stop >/dev/null 2>&1
sleep 4
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* /dev/shm/cyclonedds* 2>/dev/null

echo "[vla] 1/3 맨 시뮬 기동 (약 25초)..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_perception_pipeline:=false use_driver:=false use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > "$LOGD/sim.log" 2>&1 < /dev/null &
sleep 25

echo "[vla] 2/3 정책 서버 기동: $CKPT"
setsid nohup "$POLICY_PYTHON" -u \
  "$WS/src/sant_vla_pkg/scripts/vla_policy_server.py" \
  --checkpoint "$CKPT" --endpoint ipc:///tmp/nav_vla.sock --warmup 4 \
  > "$LOGD/serve.log" 2>&1 < /dev/null &
for _ in $(seq 1 40); do
  grep -q 'serving on' "$LOGD/serve.log" 2>/dev/null && break
  sleep 3
done
grep -q 'serving on' "$LOGD/serve.log" || { echo "[vla] 정책 서버 기동 실패 — $LOGD/serve.log"; exit 3; }

echo "[vla] 3/3 브리지 기동..."
setsid nohup ros2 run sant_vla_pkg vla_bridge_node --ros-args -p use_sim_time:=true \
  -p image_topic:=/camera/image_raw -p max_speed:=2.25 -p speed_slew:=0.08 \
  -p track_mode:=preview -p preview_dual:=false -p curv_slow_alat:=0.45 -p curv_boost:=0.95 \
  > "$LOGD/bridge.log" 2>&1 < /dev/null &
sleep 4

NPUB=$(timeout 10 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
echo "[vla] /cmd_vel 퍼블리셔 수: $NPUB (브리지+gz변환기=2가 정상, 초과면 유령)"
[ "$NPUB" -le 2 ] || { echo "[vla] 유령 퍼블리셔 감지, 중단"; exit 4; }

echo "[vla] 순항 문장 발행: $SENTENCE"
timeout 20 ros2 topic pub --once --qos-durability transient_local --qos-reliability reliable \
  /vla/instruction std_msgs/String "{data: '$SENTENCE'}" >/dev/null 2>&1 \
  && echo "[vla] 주행 시작" || echo "[vla] 문장 발행 실패 — 수동 발행 필요"

echo
echo "[vla] 정지:  ros2 topic pub --once --qos-durability transient_local --qos-reliability reliable /vla/instruction std_msgs/String \"{data: ''}\""
echo "[vla] 종료: ./vla_drive.sh down"

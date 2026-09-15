#!/bin/bash
# 오라클(파서 명령) 주행 원클릭 기동 — 예전 3터미널 조합의 원클릭판.
#
#   ./oracle_drive.sh          # 시뮬(욜로 파이프라인 포함) + 내비게이터 + 채팅 GUI(qwen)
#   ./oracle_drive.sh down     # 전체 종료 + gz 로그 정리
#
# 하이브리드 구조 (실행.txt "테스트(욜로 주행)" 조합 그대로):
#   - "출발/정지/속도/차선변경"  → 욜로 모션 파이프라인이 수행
#   - "T2로 가" 등 지점 명령     → 오라클 내비게이터(gz 좌표)가 수행
#   - 자연어 해석은 qwen(Ollama) 파서
# 예: "출발" / "go to T2" / "change to lane 1 then go m2" / "속도 100" / "멈춰"
WS="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOGD=$WS/eval_out/oracle_drive
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
  echo "[oracle] 전체 종료 중..."
  kill_stack
  sleep 3
  rm -rf ~/.gz/sim/log
  echo "[oracle] 종료 완료 (gz 로그 정리됨)"
  exit 0
fi

mkdir -p "$LOGD"
echo "[oracle] 이전 스택 정리 + DDS 초기화..."
kill_stack
ros2 daemon stop >/dev/null 2>&1
sleep 4
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* /dev/shm/cyclonedds* 2>/dev/null

echo "[oracle] 1/3 시뮬 + 욜로 파이프라인 기동 (욜로 가중치 로딩 포함 최대 120초)..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_perception_pipeline:=true use_driver:=true use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > "$LOGD/sim.log" 2>&1 < /dev/null &
for _ in $(seq 1 24); do
  NPUB=$(timeout 5 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
  [ "${NPUB:-0}" -ge 1 ] && break
  sleep 5
done
[ "${NPUB:-0}" -ge 1 ] || { echo "[oracle] 시뮬/파이프라인 기동 실패 — $LOGD/sim.log 확인"; exit 3; }

echo "[oracle] 2/3 오라클 내비게이터 기동..."
setsid nohup ros2 run sant_vla_pkg navigator_node > "$LOGD/navigator.log" 2>&1 < /dev/null &
sleep 4

echo "[oracle] 3/3 채팅 GUI(파서) 기동..."
setsid nohup ros2 run sant_vla_pkg chat_gui_node > "$LOGD/chat_gui.log" 2>&1 < /dev/null &
sleep 3

NPUB=$(timeout 10 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
echo "[oracle] /cmd_vel 퍼블리셔 수: $NPUB (욜로 송신 + 내비게이터 = 2가 정상)"
echo
echo "[oracle] 기동 완료 — 내비게이터가 초기 정지(stop)를 걸어두므로 차는 명령 대기 상태입니다."
echo "[oracle] 채팅창 예시: \"멈춰\" / \"출발\" / \"속도 100\" / \"go to T2\" / \"change to lane 1 then go m2\""
echo "[oracle] 종료: ./oracle_drive.sh down"

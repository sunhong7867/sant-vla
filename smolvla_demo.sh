#!/bin/bash
# SmolVLA 데모 스택 원클릭 기동 — 터미널 하나로 전부 실행.
#
#   ./smolvla_demo.sh                # 원격 r11 모델 + 통합 Driving Studio
#   ./smolvla_demo.sh --ckpt models/ckpt_v7_60k   # 다른 체크포인트로
#   NAVVLA_VENV=~/venv/navvla ./smolvla_demo.sh    # 정책 서버 venv 지정
#   ./smolvla_demo.sh --no-gui       # 창 없이 실행 (문장은 ros2 topic pub로)
#   sh smolvla_demo.sh --legacy-gui  # 기존 채팅 + 별도 Gazebo 창
#   ./smolvla_demo.sh check          # 실행 전 환경만 점검
#   ./smolvla_demo.sh down           # 전체 종료 + gz 로그 정리
#   NAVVLA_GUI_ARGS="-p avoid_enable:=false" ./smolvla_demo.sh   # chat_gui 파라미터 추가 (lecture_test.sh 가 사용)
#   REFILL_AT=0.65 ./smolvla_demo.sh   # 청크 재계획 시점(기본 0.8 = 0.6 s 커밋). 낮추면 계획을 더 오래 붙든다
#   2026-10-10: refill_at 0.3 -> 0.8, max_speed 2.25 -> 1.2. s3/s3n 폐루프에서 underrun 최대 100 %,
#   워치독 38 회였고 코퍼스 속도는 최대 1.90 / 중앙 1.00 이라 2.25 는 분포 밖이었다.
#   예전 설정 재현: MAX_SPEED=2.25 REFILL_AT=0.3 ./smolvla_demo.sh
#                                     # 값은 소수로 (XTRACK_GAIN=0 처럼 정수면 브리지가 타입 오류로 죽음)
#
# 로그: eval_out/demo/*.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
LOGD=$WS/eval_out/demo
CKPT=${NAVVLA_CKPT:-$WS/models/ckpt_v6_60k}
VENV=${NAVVLA_VENV:-${VIRTUAL_ENV:-${CONDA_PREFIX:-}}}
if [ -z "$VENV" ]; then
  if [ -x "$WS/.venv/bin/python" ]; then
    VENV=$WS/.venv
  else
    VENV=$HOME/venv/navvla
  fi
fi
POLICY_PYTHON=${NAVVLA_PYTHON:-$VENV/bin/python}
GUI=1
GUI_UI=dashboard
RACE=${NAVVLA_RACE:-qualifying}
REASONING_EVERY=${NAVVLA_REASONING_EVERY:-4}
# 1 = 해설로 동작 조건화(r40+ 체크포인트, --situation-from-reasoning). 해설을 매 요청 갱신
SITUATION=${NAVVLA_SITUATION:-0}
[ "$SITUATION" = 1 ] && REASONING_EVERY=${NAVVLA_REASONING_EVERY:-1}

ROS_SETUP=/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash

preflight() {
  local failed=0
  if [ "$GUI" = 1 ] && [ "$GUI_UI" = dashboard ]; then
    python3 -c 'from PySide6 import QtWidgets; from Xlib.display import Display' 2>/dev/null || {
      echo "[demo] 통합 GUI 의존성 없음: python3 -m pip install -r requirements-dashboard.txt"
      echo "       기존 창으로 실행: --legacy-gui"
      failed=1
    }
  fi
  [ -f "$ROS_SETUP" ] || { echo "[demo] ROS 환경 없음: $ROS_SETUP"; failed=1; }
  [ -f "$WS/install/setup.bash" ] || {
    echo "[demo] 워크스페이스 미빌드: ./setup_smolvla_demo.sh 실행 필요"
    failed=1
  }
  # Remote serving does not execute a local policy Python or load local weights.
  if [ "${LOCAL_VLA:-0}" = 1 ]; then
    [ -x "$POLICY_PYTHON" ] || {
      echo "[demo] 정책 Python 없음: $POLICY_PYTHON"
      echo "       NAVVLA_VENV 또는 NAVVLA_PYTHON으로 경로 지정 가능"
      failed=1
    }
    [ -f "$CKPT/model.safetensors" ] || {
      echo "[demo] 체크포인트 없음: $CKPT/model.safetensors"
      echo "       --ckpt 또는 NAVVLA_CKPT로 경로 지정 가능"
      failed=1
    }
    if [ "$failed" -eq 0 ]; then
      "$POLICY_PYTHON" -c 'import lerobot, msgpack, zmq, torch' 2>/dev/null || {
        echo "[demo] $POLICY_PYTHON 에 lerobot/msgpack/pyzmq/torch 중 일부가 없습니다."
        failed=1
      }
    fi
  fi
  # NVIDIA 드라이버 업그레이드 후 미재부팅이면 커널모듈/유저랜드 버전이 어긋나
  # gz 서버(ogre2)가 GLX BadValue로 즉사한다(2026-09-21). 시뮬 기동 전에 걸러낸다.
  if command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi -L 2>&1 | grep -q 'Driver/library version mismatch'; then
      echo "[demo] NVIDIA 드라이버 불일치(커널 모듈 vs 라이브러리) — 재부팅이 필요합니다."
      echo "       증상: gz 서버가 'X Error BadValue (GLX)'로 죽고 /world/default/control 타임아웃"
      failed=1
    fi
  fi
  [ "$failed" -eq 0 ]
}

kill_stack() {
  # pkill 자기매칭 방지: 패턴을 쪼개서 자기 자신(cmdline에 전체 문자열 없음)만 피함
  # 원격 서빙 정리: ssh 터널 + 랩서버의 정책 서버
  pat='ExitOnForwardFailur'; pkill -f "${pat}e"          2>/dev/null
  ssh -o ConnectTimeout=6 "${VLA_SRV:-autolab_sw@115.145.211.157}" \
    'p=vla_policy_serve; pkill -f "${p}r"' 2>/dev/null
  pat='gz si';            pkill -9 -f "${pat}m"          2>/dev/null
  pat='driving_sim.launc';pkill -f "${pat}h"             2>/dev/null
  pat='vla_policy_serve'; pkill -f "${pat}r"             2>/dev/null
  pat='vla_bridge_nod';   pkill -f "${pat}e"             2>/dev/null
  pat='navigator_nod';    pkill -f "${pat}e"             2>/dev/null
  pat='vla_narrato';      pkill -f "${pat}r.py"          2>/dev/null
  pat='chat_gui_nod';     pkill -f "${pat}e"             2>/dev/null
  pat='parameter_bridg';  pkill -f "${pat}e"             2>/dev/null
  pat='yolov8_nod';       pkill -f "${pat}e"             2>/dev/null
  pat='lane_info_extracto'; pkill -f "${pat}r"           2>/dev/null
  pat='lidar_obstacle_detecto'; pkill -f "${pat}r"       2>/dev/null
  pat='clock_throttl';    pkill -f "${pat}e"             2>/dev/null
  pat='ackermann_cmd_adapte'; pkill -f "${pat}r"         2>/dev/null
  pat='goal_from_scene_nod'; pkill -f "${pat}e"         2>/dev/null
  pat='lidar_marke';      pkill -f "${pat}r.py"         2>/dev/null
  # Qt GUI는 이벤트 루프가 파이썬 시그널을 삼켜 SIGTERM으로 안 죽는 경우가
  # 있음 — 잠시 후에도 살아있으면 강제 종료
  sleep 2
  pat='chat_gui_nod';     pkill -9 -f "${pat}e"          2>/dev/null
  pat='vla_narrato';      pkill -9 -f "${pat}r.py"       2>/dev/null
  # pkill은 비동기 — 이전 세션 노드가 완전히 죽기 전에 새 세션이 뜨면
  # 컨트롤러가 2개가 되어 /cmd_vel을 서로 뺏는다(차선 침범 사고의 실제 원인).
  # 전부 사라질 때까지 최대 10초 대기.
  for _ in $(seq 1 10); do
    pgrep -f "vla_bridge_nod[e]|navigator_nod[e]|chat_gui_nod[e]|vla_policy_serve[r]|simulation_sende[r]|motion_planner_nod[e]|yolov8_nod[e]|lidar_obstacle_detecto[r]|ackermann_cmd_adapte[r]|clock_throttl[e]|gz si[m]" >/dev/null || break
    sleep 1
  done
}

if [ "${1:-}" = "down" ]; then
  echo "[demo] 전체 종료 중..."
  kill_stack
  sleep 3
  rm -rf ~/.gz/sim/log
  # 세션 뷰어(view.html) 자동 생성 — view.html이 없는 세션 전부.
  # 좌: log.csv 테이블 / 우: 선택 프레임. 브라우저로 열어 리뷰.
  python3 "$WS/tools/scene_log_viewer.py" --missing 2>/dev/null \
    | sed 's/^/[demo] 뷰어: /' || true
  echo "[demo] 종료 완료 (gz 로그 정리됨)"
  exit 0
fi

if [ "${1:-}" = "check" ]; then
  CKPT="$(readlink -f "$CKPT")"
  preflight && echo "[demo] 실행 환경 정상"
  exit $?
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --ckpt) CKPT="$2"; shift 2 ;;
    --no-gui) GUI=0; shift ;;
    --legacy-gui) GUI_UI=legacy; shift ;;
    *) echo "알 수 없는 인자: $1"; exit 2 ;;
  esac
done
CKPT="$(readlink -f "$CKPT")"
preflight || exit 2
source "$ROS_SETUP"
source "$WS/install/setup.bash"
mkdir -p "$LOGD"
write_stage() {
  python3 - "$LOGD/startup.json" "$1" "$2" <<'PY_STAGE'
import json,os,sys,time
path,stage,message=sys.argv[1:]
with open(path+'.tmp','w') as out:
    json.dump({'stage':stage,'message':message,'time':time.time()},out,ensure_ascii=False)
os.replace(path+'.tmp',path)
PY_STAGE
}
trap 'code=$?; if [ "$code" -ne 0 ]; then write_stage failed "실행 실패 (종료 코드 $code). eval_out/demo 로그와 실행 터미널을 확인하세요."; fi' EXIT
write_stage starting "시뮬레이터와 모델 서버를 준비하고 있습니다."

echo "[demo] 이전 스택 정리 + DDS 초기화..."
kill_stack
ros2 daemon stop >/dev/null 2>&1
sleep 4
# 재실행 시 기존 데모가 점유한 RAM을 회수한 다음 점검합니다.
# 과거 시스템 프리즈 재발을 줄이기 위한 여유 메모리 점검입니다.
# 6G는 고정된 필수 요구량이 아닌 보수적인 기준이었으며, 사용자 요청으로
# 시작 기준을 5G로 조정합니다. 실제 사용량은 실행 모드와 다른 앱에 따라 달라집니다.
AVAIL_G=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
echo "[demo] 가용 RAM: ${AVAIL_G}G"
awk -v a="$AVAIL_G" 'BEGIN{exit !(a<5.0)}' && {
  echo "[demo] 중단: 가용 RAM ${AVAIL_G}G < 5G — 브라우저/앱을 닫고 재시도하세요."
  exit 7
}

rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* /dev/shm/cyclonedds* 2>/dev/null

# SmolVLA 전용: LLM 명령 해석기 끔(노트북 qwen3:4b 예열 방지), 표시 번역·대화 문장은 서버 EXAONE(글 전용, 이미지 안 봄)
SV_GUI_ARGS=""
if [ "${NAVVLA_PERCEIVER:-qwen}" = smolvla ]; then
  SV_GUI_ARGS="-p parser_backend:=disabled -p scene_host:=http://127.0.0.1:11501 -p translate_model:=exaone3.5:7.8b"
fi
GAZEBO_GUI=true
if [ "$GUI" = 0 ]; then GAZEBO_GUI=false; fi
if [ "$GUI" = 1 ] && [ "$GUI_UI" = dashboard ]; then
  GAZEBO_GUI=false
  if [ "${LOCAL_VLA:-0}" != 1 ] && [ "${NAVVLA_PERCEIVER:-qwen}" != smolvla ]; then
    SCENE_ARGS="-p scene_model:=qwen2.5vl:7b -p scene_host:=http://127.0.0.1:11501 -p ollama_host:=http://127.0.0.1:11501 -p parser_model:=qwen2.5vl:7b -p translate_model:=${NAVVLA_TRANSLATE_MODEL:-exaone3.5:7.8b}"
  fi
  echo "[demo] 통합 Driving Studio 기동 — 3D / BEV / 채팅 / reasoning"
  setsid nohup ros2 run sant_vla_pkg chat_gui_node --ros-args ${NAVVLA_GUI_ARGS:-} \
    -p control_backend:=smolvla -p ui:=dashboard ${SCENE_ARGS:-} ${SV_GUI_ARGS:-} \
    > "$LOGD/chat_gui.log" 2>&1 < /dev/null &
fi

echo "[demo] 1/5 시뮬레이터 기동 (약 25초)..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_gazebo_gui:="$GAZEBO_GUI" \
  use_perception_pipeline:=false use_driver:=false use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > "$LOGD/sim.log" 2>&1 < /dev/null &
sleep 25

# The same scene presets are used by the dashboard's race selector.
write_stage scene "선택한 경기의 차량과 장애물을 배치합니다."
python3 -m sant_vla_pkg.race_scenarios --scenario "$RACE" --registry "$LOGD/obstacles.json" \
  > "$LOGD/scenario.log" 2>&1 || { cat "$LOGD/scenario.log"; exit 3; }
write_stage model "정책 모델을 불러오고 있습니다."

if [ "${LOCAL_VLA:-0}" = 1 ]; then
  echo "[demo] 2/5 정책 서버 기동(로컬): $CKPT"
  VLA_ENDPOINT="ipc:///tmp/nav_vla.sock"
  setsid nohup "$POLICY_PYTHON" -u \
    "$WS/src/sant_vla_pkg/scripts/vla_policy_server.py" \
    --checkpoint "$CKPT" --endpoint "$VLA_ENDPOINT" --warmup 4 --reasoning-every "$REASONING_EVERY" \
    $( [ "$SITUATION" = 1 ] && echo --situation-from-reasoning ) \
    > "$LOGD/serve.log" 2>&1 < /dev/null &
  for _ in $(seq 1 40); do
    grep -q 'serving on' "$LOGD/serve.log" 2>/dev/null && break
    sleep 3
  done
  STATE_DIM=$("$POLICY_PYTHON" -c 'import json,sys; print(json.load(open(sys.argv[1]))["input_features"]["observation.state"]["shape"][0])' "$CKPT/config.json")
  grep -q 'serving on' "$LOGD/serve.log" || { echo "정책 서버 기동 실패 — $LOGD/serve.log 확인"; exit 3; }
else
  # 기본값: 랩서버(4070Ti)에서 서빙 (2026-08-28 결정 — 노트북 GPU 4.7G/RAM 3G
  # 회수 + 추론 106 ms로 로컬 대비 2.5배 빠름; ssh 터널 왕복 실측 114 ms).
  # 폴백: LOCAL_VLA=1 ./smolvla_demo.sh
  SRV=${VLA_SRV:-autolab_sw@115.145.211.157}
  base=$(basename "$CKPT")                      # ckpt_v6_60k -> navvla_smolvla_v6
  ver=${base#ckpt_}; ver=${ver%_60k}
  if [ -n "${NAVVLA_CKPT:-}" ] || [ "$CKPT" != "$WS/models/ckpt_v6_60k" ]; then
    DEFAULT_REMOTE=runs/navvla_smolvla_${ver}/checkpoints/060000/pretrained_model
  else
    # r26 (2026-09-17): Stanley reactive-teacher single cruise action — the
    # imitation-phase fix. Clean/centred at normal+slow (no oracle-phase
    # oscillation); high-speed inner-lane curves are closed by the bridge's
    # cross-track assist (xtrack, fast tier only) below. See
    # docs/experiments/log/20260916_1945_oracle-vs-yolo-imitation-diagnosis.md.
    DEFAULT_REMOTE=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
  fi
  RCKPT=${REMOTE_CKPT:-$DEFAULT_REMOTE}
  echo "[demo] 2/5 정책 서버 기동(랩서버 GPU${POLICY_GPU:-0}): $RCKPT"
  printf -v REMOTE_COMMAND 'bash -s -- %q %q %q %q %q' "$RCKPT" "$REASONING_EVERY" "$SITUATION" "${POLICY_GUIDE:-1.0}" "${POLICY_GPU:-0}"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$SRV" "$REMOTE_COMMAND" \
    < "$WS/server/start_demo_policy.sh" > "$LOGD/remote_start.log" 2>&1 || {
      cat "$LOGD/remote_start.log"
      echo "[demo] 원격 정책 서버 기동 실패 — $LOGD/remote_start.log 확인"
      exit 3
    }
  grep -q REMOTE_SERVING "$LOGD/remote_start.log" || { cat "$LOGD/remote_start.log"; exit 3; }
  STATE_DIM=$(sed -n 's/^STATE_DIM=//p' "$LOGD/remote_start.log" | tail -1)
  pat='ExitOnForwardFailur'; pkill -f "${pat}e" 2>/dev/null
  sleep 1
  setsid nohup ssh -N -o BatchMode=yes -o ServerAliveInterval=15 -o ExitOnForwardFailure=yes \
    -L 5556:127.0.0.1:5555 -L 11501:127.0.0.1:11500 \
    "$SRV" > "$LOGD/tunnel.log" 2>&1 < /dev/null &
  TUNNEL_PID=$!
  sleep 3
  kill -0 "$TUNNEL_PID" 2>/dev/null || { cat "$LOGD/tunnel.log"; exit 3; }
  VLA_ENDPOINT="tcp://127.0.0.1:5556"
  # 장면 reasoning: 서버 3090의 비전 LLM(ollama, 실패해도 데모는 진행 —
  # GUI가 템플릿 해설로 폴백)
  ssh -o ConnectTimeout=10 "$SRV" 'bash ~/sunhong/nav-vla/code/remote_ollama_up.sh' \
    | tail -1 || echo "[demo] 경고: 원격 ollama 미가동 — 해설은 템플릿 폴백"
  # 파서와 해설 모두 서버의 단일 비전 모델로 통일 (노트북 ollama 불사용)
  SCENE_ARGS="-p scene_model:=qwen2.5vl:7b -p scene_host:=http://127.0.0.1:11501 -p ollama_host:=http://127.0.0.1:11501 -p parser_model:=qwen2.5vl:7b -p translate_model:=${NAVVLA_TRANSLATE_MODEL:-exaone3.5:7.8b}"
fi
SCENE_ARGS="${SCENE_ARGS:-}"
# SmolVLA 전용 목표 모드(lecture_test.sh --goto-smolvla): 해설·대화·명령 해석의 Qwen 도 끈다(해설은 템플릿 폴백)
if [ "${NAVVLA_PERCEIVER:-qwen}" = smolvla ]; then SCENE_ARGS=""; fi
STANDSTILL=false
GOAL_CONDITIONING=false
case "$STATE_DIM" in
  3) ;;
  4) STANDSTILL=true ;;
  5) GOAL_CONDITIONING=true ;;
  6) STANDSTILL=true; GOAL_CONDITIONING=true ;;   # 2026-10-12 g5d: [v,w,steer,goal_b,goal_d,standstill]
  *) echo "[demo] 지원하지 않는 모델 상태 차원: $STATE_DIM"; exit 3 ;;
esac
write_stage bridge "모델 준비 완료. 차량 제어 브리지를 연결합니다."

echo "[demo] 3/5 브리지 기동..."
setsid nohup ros2 run sant_vla_pkg vla_bridge_node --ros-args -p use_sim_time:=true \
  -p endpoint:="$VLA_ENDPOINT" -p standstill_state:="$STANDSTILL" -p standstill_cap:=3.5 -p goal_conditioning:="$GOAL_CONDITIONING" \
  -p model_name:=ego_vehicle -p display_preview_period:=0.4 \
  -p image_topic:=/camera/image_raw -p max_speed:="${MAX_SPEED:-1.2}" -p speed_slew:=0.08 \
  -p track_mode:=preview -p curv_slow_alat:=0.6 -p curv_boost:=0.95 \
  -p curv_boost_slow:="${CURV_BOOST_SLOW:-0.85}" -p curv_boost_fast:=0.85 \
  -p xtrack_gain:="${XTRACK_GAIN:-0.15}" -p xtrack_tiers:="${XTRACK_TIERS:-fast}" \
  -p refill_at:="${REFILL_AT:-0.8}" \
  > "$LOGD/bridge.log" 2>&1 < /dev/null &

echo "[demo] 4/5 내비게이터 + 내레이터 기동..."
# 장면 해설용 지각: YOLO 차선/객체 감지 + lane_info — GUI의 1초 주기
# 이미지 기반 reasoning 말풍선 재료. lane1_car/lane2_car는 회피 감독의
# 트리거이기도 하다(chat_gui의 avoid_* 파라미터): best_cap.pt가 차량을
# 차선별 클래스로 구분해 주므로 "내 차선에 장애물" 판정이 클래스명만으로 된다.
setsid nohup ros2 run camera_perception_pkg yolov8_node --ros-args \
  -p model:="$WS/best_cap.pt" -p device:=cuda:0 \
  -p "allowed_class_names:=[lane1, lane2, lane1_car, lane2_car]" \
  -p "ignore_class_names:=[crosswalk]" \
  -p inference_period:=1.0 -p imgsz:=416 \
  > "$LOGD/yolo.log" 2>&1 < /dev/null &
setsid nohup ros2 run camera_perception_pkg lane_info_extractor_node --ros-args \
  -p lane_mode:=keep_lane -p target_lane:=lane2 \
  > "$LOGD/lane_info.log" 2>&1 < /dev/null &

# 회피 주 트리거: LiDAR 전방 섹터 검출 (기하 기반 — 시뮬 저폴리곤 차량을
# best_cap/COCO YOLO 모두 정면·근거리에서 놓치는 것을 16:37 세션에서 실측).
# range_max 8m: 2 m/s 기준 차선 변경(~4 s)에 필요한 여유. 라이브 튜닝:
#   ros2 param set /lidar_obstacle_detector_node range_max 10.0
#
# 2026-10-12: 이 트리거는 그동안 한 번도 발화하지 않았다. eval_out/demo 의
# 10-10 로그 835 줄 전부 `front 0-15deg nearest=inf detected=False` 다. 두 가지
# 고장이 겹쳐 있었다.
#   (1) 센서가 뒷범퍼 뒤 0.645 m(차체 밖)에 떠 있어 전방 레이가 자기 차체에
#       막혔다 — argmin 이 늘 idx 265~273 에서 0.70 m, 즉 자기 뒷범퍼였다.
#       prius_hybrid/model.sdf 의 lidar_link 를 앞범퍼(y -1.80, z 0.70)로 옮겼다.
#   (2) 섹터 0~15° 는 전방이 아니다. 센서 프레임 0° = +x(우측)이고 차량 전방은
#       로컬 -y = **270°** 다(위 argmin 중심 269° 와 일치, 노드 docstring 의
#       "~90 deg yaw offset" 경고가 이것). 262~278° = 전방 ±8° 로 지정한다.
# 두 수정 뒤 range_max 8.0 은 코끝 기준 약 7.9 m 를 뜻한다 — 주석의 설계 의도와
# 처음으로 일치한다(이전 마운트에서는 실질 3.5 m 였고, 그마저 자기 차체에 막혔다).
# 회피 발화 시점이 바뀌므로 avoidance 결과는 이 날짜 전후로 비교하지 않는다.
setsid nohup ros2 run ros_gz_bridge parameter_bridge \
  "/scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan" \
  > "$LOGD/scan_bridge.log" 2>&1 < /dev/null &
setsid nohup ros2 run lidar_perception_pkg lidar_obstacle_detector_node --ros-args \
  -p range_max:=8.0 -p start_angle:=262 -p end_angle:=278 -p debug_argmin:=true \
  > "$LOGD/lidar_obstacle.log" 2>&1 < /dev/null &

# direct_twist_topic: 직행(최단거리) 구간은 VLA를 침묵시키고 navigator가
# /cmd_vel을 직접 구동한다 (docs/experiments/log/20260824_1138 좌표 위임 결정).
setsid nohup ros2 run sant_vla_pkg navigator_node --ros-args \
  -p direct_twist_topic:=/cmd_vel > "$LOGD/navigator.log" 2>&1 < /dev/null &
setsid nohup python3 "$WS/src/sant_vla_pkg/scripts/vla_narrator.py" > "$LOGD/narrator.log" 2>&1 < /dev/null &
# 라이다 빔 시각화 (2026-10-13): 3D 뷰에 파란 빔. GUI 의 MarkerManager 로 그린다
# (VisualizeLidar 는 토픽 선택 칸이 화면에 보여야만 그려서 숨긴 패널로는 안 됨). 끄기: NAVVLA_LIDAR_VIS=0
if [ "$GUI" = 1 ] && [ "${NAVVLA_LIDAR_VIS:-1}" = 1 ]; then
  setsid nohup python3 "$WS/src/sant_vla_pkg/scripts/lidar_marker.py" > "$LOGD/lidar_marker.log" 2>&1 < /dev/null &
fi
# 점 목표 모드 (2026-10-13, g5d): GUI 문장 -> /goal_request -> Qwen2.5-VL 박스 + /scan 거리 -> /vla_goal.
# 정책은 "Target." 만 듣는다. lecture_test.sh --goto 가 NAVVLA_POINT_GOAL=1 로 켠다.
# NAVVLA_STOP_GAP: 정지 간격(기본 0.8 → 실측 물체 표면까지 약 0.9 m·전방 카메라에 물체가 보임; 0.4 → 0.47 m, 너무 가까움)
if [ "${NAVVLA_POINT_GOAL:-0}" = 1 ]; then
  setsid nohup python3 "$WS/src/sant_vla_pkg/sant_vla_pkg/goal_from_scene_node.py" --ros-args -p use_sim_time:=true \
    -p ollama_host:=http://127.0.0.1:11501 -p scan_topic:=/scan -p hfov_deg:=62.2 -p stop_gap_m:="${NAVVLA_STOP_GAP:-0.8}" -p perceiver:="${NAVVLA_PERCEIVER:-qwen}" \
    > "$LOGD/goal_from_scene.log" 2>&1 < /dev/null &
fi
sleep 6

# 정당한 /cmd_vel 퍼블리셔 3: gz 브리지 어댑터, vla_bridge, navigator(직행 Twist).
NPUB=$(timeout 10 ros2 topic info /cmd_vel --verbose --no-daemon --spin-time 3 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
echo "[demo] /cmd_vel 퍼블리셔 수: $NPUB (3 초과면 유령 노드 — down 후 재기동)"
[ "$NPUB" -le 3 ] || { echo "[demo] 유령 퍼블리셔 감지, 중단"; exit 4; }
timeout 15 ros2 topic echo /vla/status std_msgs/msg/String --once > "$LOGD/bridge_ready.log" 2>&1
grep -qE "latency_ms|override" "$LOGD/bridge_ready.log" || {
  echo "[demo] 차량 제어 브리지 응답 없음 — $LOGD/bridge.log 확인"
  exit 3
}

if [ "$GUI" = 1 ] && [ "$GUI_UI" = legacy ]; then
  echo "[demo] 5/5 채팅 GUI 기동..."
  setsid nohup ros2 run sant_vla_pkg chat_gui_node --ros-args ${NAVVLA_GUI_ARGS:-} -p control_backend:=smolvla -p ui:=legacy \
    $SCENE_ARGS \
    > "$LOGD/chat_gui.log" 2>&1 < /dev/null &
elif [ "$GUI" = 0 ]; then
  echo "[demo] 5/5 GUI 생략 — 문장 직접 발행 예:"
  echo "  ros2 topic pub --once --qos-durability transient_local --qos-reliability reliable \\"
  echo "    /vla/instruction std_msgs/String \"{data: 'Start driving in the outer lane, at a fast speed.'}\""
fi

echo
write_stage ready "주행 준비 완료 · 채팅으로 출발할 수 있습니다."
echo "[demo] 스택 기동 완료. 예시 명령: \"start drive\" / \"천천히 안쪽 차선으로\" / \"go to T2\" / \"멈춰\""
echo "[demo] 종료: ./smolvla_demo.sh down"

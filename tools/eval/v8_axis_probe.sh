#!/bin/bash
# v8 신규 축 프로브: CW 방향 반사실 + 직행 2회. 시뮬은 떠 있다고 가정
# (ring_map_probe.sh가 남겨둔 상태), 서버+브리지는 여기서 기동/정리.
# Usage: v8_axis_probe.sh <ckpt_dir> <prefix>
set -e
CKPT=$1; PFX=$2
WS="${WS:-$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)}"
NAVVLA_PY="${NAVVLA_PY:-$HOME/venv/navvla/bin/python}"
OUT=$WS/eval_out
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

pat_s='vla_policy_serve'; pkill -f "${pat_s}r" || true
pat_b='vla_bridge_nod'; pkill -f "${pat_b}e" || true
sleep 3

setsid nohup "$NAVVLA_PY" -u \
  $WS/src/sant_vla_pkg/scripts/vla_policy_server.py \
  --checkpoint $CKPT --endpoint ipc:///tmp/nav_vla.sock --warmup 4 \
  > $OUT/${PFX}_serve.log 2>&1 < /dev/null &
until grep -q 'serving on' $OUT/${PFX}_serve.log 2>/dev/null; do sleep 3; done

setsid nohup ros2 run sant_vla_pkg vla_bridge_node --ros-args -p use_sim_time:=true \
  -p max_speed:=3.2 -p image_topic:=/camera/image_raw -p speed_slew:=0.08 \
  > $OUT/${PFX}_bridge.log 2>&1 < /dev/null &
sleep 4

# 1) CW 방향 반사실: 표준 시작점에서 요를 π 반전(+1.571), cruise_cw 문장 안/바깥
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw 1.571 --duration 115 \
  --say-a "Take a lap the opposite way around in the inner driving lane." \
  --say-b "Drive around the track in the reverse direction in the outer lane." \
  --out $OUT/${PFX}_cw_map.json > $OUT/${PFX}_cw_probe.log 2>&1
echo "CW_DONE"

# 2) 직행: 같은 시작점 부근에서 두 존으로 최단거리 (반사실 쌍)
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw -1.571 --duration 60 \
  --say-a "Take the shortest path to T3." \
  --say-b "Head directly to checkpoint M3." \
  --out $OUT/${PFX}_direct_map.json > $OUT/${PFX}_direct_probe.log 2>&1
echo "DIRECT_DONE"

pat_s='vla_policy_serve'; pkill -f "${pat_s}r" || true
pat_b='vla_bridge_nod'; pkill -f "${pat_b}e" || true
echo "AXIS_PROBE_DONE ${PFX}"

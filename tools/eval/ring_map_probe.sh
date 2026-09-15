#!/bin/bash
# Full-ring mapping probe for a policy checkpoint.
# Usage: ring_map_probe.sh <checkpoint_dir> <out_prefix>
#   EXTRA_BRIDGE_ARGS="-p curv_boost:=1.2" 처럼 환경변수로 브리지 파라미터 추가 가능
# Brings up bare sim + server + bridge, runs the standard inner/outer 115 s
# counterfactual cruise from the canonical start, writes <out_prefix>_map.json,
# then tears the server/bridge down (sim left up for chained probes).
set -e
CKPT=$1
PFX=$2
[ -d "$CKPT" ] || { echo "usage: ring_map_probe.sh <ckpt_dir> <out_prefix>"; exit 2; }
# Workspace root is derived from this script's location (tools/eval/ -> repo).
# Override with WS= for out-of-tree checkouts; NAVVLA_PY points at the LeRobot
# venv python (the serving deps are not in the ROS environment).
WS="${WS:-$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)}"
NAVVLA_PY="${NAVVLA_PY:-$HOME/venv/navvla/bin/python}"
MAX_SPEED="${MAX_SPEED:-3.2}"
SPEED_SCALE="${SPEED_SCALE:-1.0}"
SPEED_SLEW="${SPEED_SLEW:-0.08}"
TRACK_MODE="${TRACK_MODE:-replay}"
REFILL_AT="${REFILL_AT:-0.3}"
SPLICE_OVERLAP="${SPLICE_OVERLAP:-5}"
FORCE_ZERO_STEER_STATE="${FORCE_ZERO_STEER_STATE:-false}"
START_X="${START_X:--1.49}"
START_Y="${START_Y:-24.55}"
START_YAW="${START_YAW:--1.571}"
START_LABEL="${START_LABEL:-outer}"
OUT=$WS/eval_out
mkdir -p $OUT
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

pat_g='gz si'; pkill -9 -f "${pat_g}m" || true; pat_l='driving_sim.launc'; pkill -f "${pat_l}h" || true
pat_s='vla_policy_serve'; pkill -f "${pat_s}r" || true; pat_b='vla_bridge_nod'; pkill -f "${pat_b}e" || true
pat_pb='parameter_bridg'; pkill -f "${pat_pb}e" || true
sleep 3
rm -rf ~/.gz/sim/log

setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_perception_pipeline:=false use_driver:=false use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > $OUT/${PFX}_sim.log 2>&1 < /dev/null &
sleep 25

setsid nohup "$NAVVLA_PY" -u \
  $WS/src/sant_vla_pkg/scripts/vla_policy_server.py \
  --checkpoint $CKPT --endpoint ipc:///tmp/nav_vla.sock --warmup 4 \
  > $OUT/${PFX}_serve.log 2>&1 < /dev/null &
until grep -q 'serving on' $OUT/${PFX}_serve.log 2>/dev/null; do sleep 3; done

setsid nohup ros2 run sant_vla_pkg vla_bridge_node --ros-args -p use_sim_time:=true \
  -p max_speed:="$MAX_SPEED" -p speed_scale:="$SPEED_SCALE" \
  -p speed_slew:="$SPEED_SLEW" -p track_mode:="$TRACK_MODE" \
  -p refill_at:="$REFILL_AT" -p splice_overlap:="$SPLICE_OVERLAP" \
  -p force_zero_steer_state:="$FORCE_ZERO_STEER_STATE" \
  -p image_topic:=/camera/image_raw \
  -p seed:=${POLICY_SEED:-0} \
  ${EXTRA_BRIDGE_ARGS:-} \
  > $OUT/${PFX}_bridge.log 2>&1 < /dev/null &
sleep 4

NPUB=$(timeout 10 ros2 topic info /cmd_vel --verbose 2>/dev/null | grep -c 'Endpoint type: PUBLISHER')
echo "cmd_vel publishers: $NPUB"
# 정규 퍼블리셔 3: vla_bridge, gz_bridge_control(양방향), ackermann_cmd_adapter
# (+ FastDDS 미해석 중복 1까지 허용). 진짜 고스트는 유휴 스팸으로 판별:
[ "$NPUB" -le 4 ] || { echo GHOST; exit 20; }
IDLE=$(timeout 4 ros2 topic echo /cmd_vel --once 2>/dev/null | head -1)
[ -z "$IDLE" ] || { echo "GHOST_IDLE_SPAM: $IDLE"; exit 21; }

python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x "$START_X" --y "$START_Y" --yaw "$START_YAW" \
  --start-label "$START_LABEL" --run-id "$PFX" \
  --duration ${DURATION:-115} \
  --repeats ${REPEATS:-1} \
  --say-a "${SAY_A:-Start driving in the inner lane, at a ${SPEED_WORD:-fast} speed.}" \
  --say-b "${SAY_B:-Start driving in the outer lane, at a ${SPEED_WORD:-fast} speed.}" \
  --case-label "${CASE_LABEL:-DIFFERENT instruction}" \
  --out $OUT/${PFX}_map.json > $OUT/${PFX}_probe.log 2>&1

pat_s='vla_policy_serve'; pkill -f "${pat_s}r" || true; pat_b='vla_bridge_nod'; pkill -f "${pat_b}e" || true
echo "PROBE_DONE ${PFX} -> $OUT/${PFX}_map.json"

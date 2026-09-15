#!/bin/bash
# v8g(목표 조건화) 프로브: 직행(목표 채널 ON) + CW 회귀 + CCW 회귀.
# 시뮬은 떠 있다고 가정. Usage: v8g_axis_probe.sh <ckpt_dir> <prefix>
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
SRV_PID=$!
# 무한 대기 금지: 워밍업 크래시가 이틀짜리 행이 된 적 있음(2026-08-22).
for i in $(seq 1 60); do
  grep -q 'serving on' $OUT/${PFX}_serve.log 2>/dev/null && break
  if ! kill -0 $SRV_PID 2>/dev/null; then echo "SERVER_DIED"; tail -5 $OUT/${PFX}_serve.log; exit 22; fi
  sleep 3
done
grep -q 'serving on' $OUT/${PFX}_serve.log || { echo "SERVER_TIMEOUT"; exit 23; }

setsid nohup ros2 run sant_vla_pkg vla_bridge_node --ros-args -p use_sim_time:=true \
  -p max_speed:=3.2 -p image_topic:=/camera/image_raw -p speed_slew:=0.08 \
  -p goal_conditioning:=true -p model_name:=ego_vehicle \
  > $OUT/${PFX}_bridge.log 2>&1 < /dev/null &
sleep 6
grep -q "goal conditioning ON" $OUT/${PFX}_bridge.log \
  || { echo "BRIDGE_NO_GOAL_MODE"; exit 21; }

# 1) 직행 (분포 안 거리: M2 18.8m / T2 28.7m) — 문장+목표 채널 동시
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw -1.571 --duration 60 \
  --say-a "Head directly to checkpoint M2." --goal-a M2 \
  --say-b "Make a beeline for checkpoint T2." --goal-b T2 \
  --out $OUT/${PFX}_direct_map.json > $OUT/${PFX}_direct_probe.log 2>&1
echo "DIRECT_DONE"

# 2) 직행 원거리 일반화 (학습 분포 8-30m 밖, T3 49m)
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw -1.571 --duration 90 \
  --say-a "Take the shortest path to T3." --goal-a T3 \
  --say-b "Head directly to checkpoint M3." --goal-b M3 \
  --out $OUT/${PFX}_directfar_map.json > $OUT/${PFX}_directfar_probe.log 2>&1
echo "DIRECT_FAR_DONE"

# 3) CW 방향 회귀 (목표 없음 — (0,0) 채널)
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw 1.571 --duration 115 \
  --say-a "Take a lap the opposite way around in the inner driving lane." \
  --say-b "Drive around the track in the reverse direction in the outer lane." \
  --out $OUT/${PFX}_cw_map.json > $OUT/${PFX}_cw_probe.log 2>&1
echo "CW_DONE"

# 4) CCW 링 회귀
python3 $WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py \
  --x -1.49 --y 24.55 --yaw -1.571 --duration 115 \
  --say-a "Start driving in the inner lane, at a fast speed." \
  --say-b "Start driving in the outer lane, at a fast speed." \
  --out $OUT/${PFX}_ccw_map.json > $OUT/${PFX}_ccw_probe.log 2>&1
echo "CCW_DONE"

pat_s='vla_policy_serve'; pkill -f "${pat_s}r" || true
pat_b='vla_bridge_nod'; pkill -f "${pat_b}e" || true
echo "V8G_PROBE_DONE ${PFX}"

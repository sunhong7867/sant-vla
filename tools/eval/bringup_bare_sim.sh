#!/bin/bash
# 베어 시뮬(카메라만) 기동 — 프로브용. 파일 스크립트: pkill 자기매치 방지.
WS=/home/sh/ROS2_project/sant-vla
OUT=$WS/eval_out
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash
p='gz si'; pkill -9 -f "${p}m" 2>/dev/null
p='driving_sim.launc'; pkill -f "${p}h" 2>/dev/null
for _ in $(seq 1 8); do pgrep -f "gz si[m]" >/dev/null || break; sleep 1; done
rm -rf ~/.gz/sim/log
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_perception_pipeline:=false use_driver:=false use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > $OUT/v8g_sim.log 2>&1 < /dev/null &
for _ in $(seq 1 12); do
  N=$(timeout 5 ros2 topic list 2>/dev/null | grep -c "camera/image_raw")
  [ "${N:-0}" -ge 1 ] && { echo SIM_UP; exit 0; }
  sleep 5
done
echo SIM_FAIL; exit 3

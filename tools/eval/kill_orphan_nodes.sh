#!/bin/bash
# 시뮬 런치가 남긴 고아 노드 정리 (파일 스크립트: pkill 자기매치 방지).
# 대상: ackermann 어댑터, clock 스로틀, ros_gz 브리지, yolo/lane/lidar 인지 노드.
p='ackermann_cmd_adapte'; pkill -f "${p}r" 2>/dev/null
p='clock_throttl';        pkill -f "${p}e" 2>/dev/null
p='parameter_bridg';      pkill -f "${p}e" 2>/dev/null
p='yolov8_nod';           pkill -f "${p}e" 2>/dev/null
p='lane_info_extracto';   pkill -f "${p}r" 2>/dev/null
p='lidar_obstacle_detecto'; pkill -f "${p}r" 2>/dev/null
for _ in $(seq 1 8); do
  pgrep -f "ackermann_cmd_adapte[r]|clock_throttl[e]|parameter_bridg[e]|yolov8_nod[e]|lane_info_extracto[r]|lidar_obstacle_detecto[r]" >/dev/null || break
  sleep 1
done
for q in 'ackermann_cmd_adapte[r]' 'clock_throttl[e]' 'parameter_bridg[e]' 'gz si[m]'; do
  printf '%-24s %s\n' "$q" "$(pgrep -c -f "$q")"
done
echo ORPHANS_CLEANED

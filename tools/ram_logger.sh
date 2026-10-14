#!/bin/bash
# 5 분마다 가용 RAM·스왑 기록 (2026-10-03 주말 무인 실행 감시). 종료: touch /tmp/claude-ram-logger.stop
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
LOG=/home/sh/ROS2_project/sant-vla/eval_out/course/ram_log.txt
if [ "${RL_CHILD:-0}" != 1 ]; then
  rm -f /tmp/claude-ram-logger.stop
  RL_CHILD=1 setsid nohup bash "$0" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — $LOG"; exit 0
fi
while [ ! -f /tmp/claude-ram-logger.stop ]; do
  echo "$(date '+%F %T') $(free -m | awk 'NR==2{printf "avail %dM used %dM", $7, $3} NR==3{printf " swap %dM/%dM", $(NF-1), $(NF-2)}')"
  sleep 300
done

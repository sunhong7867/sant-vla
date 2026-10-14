#!/bin/bash
# 시뮬 로그·캐시 청소기 (2026-10-02, 사용자 요청 "시뮬 돌리며 생기는 캐시·로그 바로바로 정리").
# gz server_console.log 가 prius_hybrid 조인트 경고(Physics.cc:2519, 약 200 줄/s)로 50 분에 1.5 GB 씩 쌓인다.
#  - 5 분마다: 200 MB 넘는 server_console.log 는 비움(truncate — 쓰는 중이어도 안전),
#    지금 실행 중이 아닌 옛 gz 로그 폴더 삭제, 1 일 지난 /tmp/prius_hybrid_*·launch_params_* 삭제
#  - 종료: touch /tmp/claude-sim-janitor.stop   (또는 pidfile 의 pid 에 kill)
#   bash tools/sim_log_janitor.sh ; tail eval_out/course/sim_log_janitor.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sim_log_janitor.log
PIDF=/tmp/claude-sim-janitor.pid
STOP=/tmp/claude-sim-janitor.stop
if [ "${JN_CHILD:-0}" != 1 ]; then
  if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then echo "already running (pid $(cat "$PIDF"))"; exit 0; fi
  rm -f "$STOP"
  JN_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDF"; echo "started (pid $!) — $LOG"; exit 0
fi
LIM=$((200 * 1024 * 1024))
while [ ! -f "$STOP" ]; do
  newest=$(ls -td ~/.gz/sim/log/*/ 2>/dev/null | head -1)
  for f in ~/.gz/sim/log/*/server_console.log; do
    [ -f "$f" ] || continue
    # 실제 디스크 사용량(블록) 기준: 쓰는 중인 파일을 비우면 이후 쓰기가 옛 오프셋에 붙어 겉보기 크기만 큰 희소 파일이 된다
    sz=$(( $(stat -c %b "$f") * $(stat -c %B "$f") ))
    [ "$sz" -gt "$LIM" ] && { truncate -s 0 "$f"; echo "$(date '+%F %T') truncate $(( sz / 1048576 )) MB $f"; }
  done
  for d in ~/.gz/sim/log/*/; do
    [ -d "$d" ] && [ "$d" != "$newest" ] && { echo "$(date '+%F %T') rm old gz log $d ($(du -sh "$d" | cut -f1))"; rm -rf "$d"; }
  done
  find /tmp -maxdepth 1 \( -name 'prius_hybrid_*' -o -name 'launch_params_*' \) -mmin +1440 -exec rm -rf {} + 2>/dev/null
  sleep 300
done
echo "$(date '+%F %T') stop"; rm -f "$PIDF" "$STOP"

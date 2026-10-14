#!/bin/bash
# a1 회피 평가(union_avoid_chain 의 "<RUN> avoidance eval" 단계)가 시작되면 gz GUI 창을 붙인다 (2026-10-12 사용자 요청).
# stat_eval 은 조건마다 헤드리스 시뮬을 재기동하므로, 서버 pid 가 바뀌면 끊긴 창을 닫고 새로 붙인다.
# 평가 서버는 건드리지 않는다. 창 기동은 watch_collection_gui.sh(가용 RAM 3G 미만이면 거부)에 맡긴다.
#   setsid nohup bash tools/eval/watch_a1_eval_gui.sh > eval_out/course/watch_a1_eval_gui.log 2>&1 < /dev/null &
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
RUN=${RUN:-a1}
UA=$WS/eval_out/course/union_avoid_chain.log
ST=$WS/eval_out/course/stat_$RUN.log
exec 9> /tmp/watch_a1_eval_gui.lock
flock -n 9 || { echo "이미 실행 중"; exit 0; }
note() { echo "[gui $(date '+%F %T')] $*"; }

part_of() { tr '\0' '\n' < "/proc/$1/environ" 2>/dev/null | sed -n 's/^GZ_PARTITION=//p'; }
close_guis() {   # div(수집)·stat(평가) partition 의 GUI 클라이언트만 닫는다
  for p in $(pgrep -f 'gz sim -[g]'); do
    case "$(part_of "$p")" in div|stat) kill "$p" 2>/dev/null && note "창 닫음 pid $p" ;; esac
  done
}
stat_server() {
  for p in $(pgrep -f 'gz sim -r -[s]'); do [ "$(part_of "$p")" = stat ] && { echo "$p"; return; }; done
}

note "대기: '$RUN avoidance eval' 단계"
until grep -q "\] $RUN avoidance eval" "$UA" 2>/dev/null; do
  grep -q '^\[ua\] ' "$UA" 2>/dev/null && grep -qE '^\[ua\] (END|.*실패|.*없음)' "$UA" && { note "체인이 평가 전에 끝남"; exit 1; }
  sleep 30
done
note "$RUN 평가 시작 — 창 붙이기"
cur=""
while ! grep -qE 'ALL_DONE [0-9]' "$ST" 2>/dev/null; do
  srv=$(stat_server)
  if [ -n "$srv" ] && [ "$srv" != "$cur" ]; then
    sleep 20   # 월드 로드 대기
    [ "$(stat_server)" = "$srv" ] || continue
    close_guis; sleep 2
    out=$(PART=stat bash "$WS/tools/watch_collection_gui.sh" 2>&1); note "$out"
    case "$out" in *"GUI 기동"*) cur=$srv ;; esac
  fi
  sleep 15
done
sleep 5; close_guis
note "$RUN 평가 끝 — 종료"

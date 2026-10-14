#!/bin/bash
# 말로 지정한 물체로 가기 — 3시간 주기 자율 진행 루프 (2026-10-07).
#
# 왜 파일 스크립트인가: (1) 이 작업은 랩서버 ssh 키와 노트북의 gz 시뮬이 둘 다 필요해서
# 클라우드 루틴으로는 불가능하다. (2) 인라인 pkill/pgrep 패턴은 자기 자신을 죽인다
# (docs/experiments/log/20260828_1617) — 그래서 확인은 대괄호 패턴, 정리는 파일 스크립트로만 한다.
# (3) setsid 로 떼어 두면 대화 세션을 닫아도 계속 돈다.
#
#   setsid nohup bash tools/goto_loop_chain.sh > /dev/null 2>&1 < /dev/null &
#   tail -f eval_out/course/goto_loop.log
#   bash tools/goto_loop_chain.sh stop        # 다음 주기에 종료
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_loop.log
STOP=$WS/eval_out/course/goto_loop.stop
STATE=$WS/eval_out/course/goto_loop_state.txt
SRV=autolab_sw@115.145.211.157
PERIOD=${PERIOD:-10800}          # 3 h

[ "$1" = stop ] && { : > "$STOP"; echo "다음 주기에 종료한다"; exit 0; }
mkdir -p "$(dirname "$LOG")"
rm -f "$STOP"
exec >> "$LOG" 2>&1

rs() { ssh -o ConnectTimeout=20 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[loop $(date '+%F %T')] $*"; }
seen() { grep -qxF "$1" "$STATE" 2>/dev/null; }
mark() { echo "$1" >> "$STATE"; }

note "=== 루프 시작 (주기 ${PERIOD}s) ==="
while :; do
  [ -f "$STOP" ] && { note "stop 파일 확인 — 종료"; rm -f "$STOP"; exit 0; }

  # ── 1. 자원 상태 (기동 전 프리플라이트: docs/experiments/log/20260828_1224) ─────────
  AVAIL=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
  FREE=$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  SRVFREE=$(rs "df -BG --output=avail ~ | tail -1 | tr -dc 0-9" 2>/dev/null)
  note "노트북 RAM ${AVAIL}G, 디스크 ${FREE}G / 서버 디스크 ${SRVFREE:-?}G"

  # ── 2. 서버 학습 감시 ───────────────────────────────────────────────────
  RUNNING=$(rs "pgrep -c -f 'train_reasonin[g]'" 2>/dev/null || echo 0)
  note "서버 학습 프로세스 ${RUNNING:-?}개"
  for rc in $(rs "cd ~/sunhong/nav-vla/runs/course 2>/dev/null && for d in navvla_reasoning_*/checkpoints/*/pretrained_model; do [ -f \$d/model.safetensors ] && echo \$d; done" 2>/dev/null); do
    key="probe:$rc"
    seen "$key" && continue
    note "새 체크포인트: $rc — 통계 교정 + 반사실 프로브"
    rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py runs/course/$rc 2>&1 | tail -2; \
        CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_goto_language.py runs/course/$rc \
          data/course/packed_goto --n 60 2>&1 | grep -E 'PRED|opposite|goto_'" && mark "$key"
  done

  # ── 3. 서버 디스크 경고 (체크포인트 1개가 1.05G) ────────────────────────
  if [ -n "$SRVFREE" ] && [ "$SRVFREE" -lt 5 ]; then
    note "경고: 서버 여유 ${SRVFREE}G < 5G — 다음 저장이 실패할 수 있다. 진단 끝난 체크포인트 정리 필요"
  fi

  # ── 4. 수집/평가는 시뮬이 비어 있을 때만 (중복 기동 금지) ───────────────
  BUSY=$(pgrep -c -f 'gz si[m]')
  if [ "$BUSY" -gt 0 ]; then
    note "시뮬 ${BUSY}개 실행 중 — 이번 주기에는 수집/폐루프를 건드리지 않는다"
  fi

  note "--- 주기 종료, ${PERIOD}s 대기 ---"
  SLEPT=0
  while [ "$SLEPT" -lt "$PERIOD" ]; do
    [ -f "$STOP" ] && break
    sleep 60; SLEPT=$((SLEPT+60))
  done
done

#!/bin/bash
# s0(상수 문장) → r26(베이스) SEC 폐루프 순차 실행 (2026-10-08).
# 순차여야 한다: goto_stat_eval 은 모두 ROS_DOMAIN_ID=87 / GZ_PARTITION=goto 를 쓰므로
# 동시에 돌리면 gz 중복 기동 + /cmd_vel 퍼블리셔 2개가 된다(docs/ver/20260828_1617).
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sec_closedloop_all.log
exec >> "$LOG" 2>&1
note() { echo "[cl $(date '+%F %T')] $*"; }
cd "$WS" || exit 1

run_one() {   # $1=RUN $2=STEP $3=TAG $4=CKPT(비우면 기본 경로)
  note "--- $3 시작 ---"
  CKPT=$4 RUN=$1 STEP=$2 TIERS=SEC N=30 TAG=$3 bash tools/eval/goto_stat_eval.sh
  local gl=$WS/eval_out/course/goto_$1_$2.log
  until grep -q "ALL_DONE" "$gl" 2>/dev/null; do
    grep -qE "BRINGUP_FAIL|RAM_WAIT_TIMEOUT" "$gl" 2>/dev/null && { note "$3 기동 실패"; tail -5 "$gl"; return 1; }
    sleep 30
  done
  note "--- $3 완료 ---"
  python3 tools/eval/goto_analyze.py eval_out/course/goto_eval "$3" 2>&1 | tail -5
  # 다음 실행 전 잔류 확인 (어댑터·클록 고아가 /cmd_vel·/clock 을 중복시킨 전례)
  for p in 'gz si[m]' 'vla_bridge_nod[e]' 'ackermann_cmd_adapte[r]' 'clock_throttle_nod[e]'; do
    note "  잔류 $p = $(pgrep -c -f "$p")"
  done
}

note "=== 시작 ==="
run_one s0 010000 s0_sec ""
run_one r26 last r26_sec "runs/navvla_reasoning_r26/checkpoints/last/pretrained_model"
note "=== END ==="
echo
note "세 체크포인트 비교:"
for t in s1_sec s0_sec r26_sec; do python3 "$WS/tools/eval/goto_analyze.py" "$WS/eval_out/course/goto_eval" "$t" 2>&1 | grep -E "^==|SEC |sets"; done

#!/bin/bash
# r52(방향 단어) 체인 (2026-10-04): 체크포인트마다 언어 반사실 진단(서버, 시뮬 없음) →
# 30k 에서 폐루프 평가(정책 단독 방향 문장 + Qwen 계층형). r51 30k 진단도 기록.
#   bash tools/goto_r52_chain.sh   (setsid nohup 으로 스스로 분리, 로그 eval_out/course/goto_r52_chain.log)
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_r52_chain.log
if [ "${GC_CHILD:-0}" != 1 ]; then
  GC_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
rs() { ssh -o ConnectTimeout=15 "$SRV" "$@"; }
step() { echo; echo "======== [$(date '+%F %T')] $1 ========"; }
ck() { echo "runs/course/navvla_reasoning_$1/checkpoints/$2/pretrained_model"; }
wait_ck() {
  until rs "test -f ~/sunhong/nav-vla/$(ck "$1" "$2")/model.safetensors" 2>/dev/null; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log" 2>/dev/null && { echo "[gc] $1 train fail"; return 1; }
    sleep 180
  done
  sleep 60
}
probe() {   # $1 run, $2 step, $3 packed dir
  rs "cd ~/sunhong/nav-vla && CUDA_VISIBLE_DEVICES=${PROBE_GPU:-0} ./venv/bin/python code/course/probe_goto_language.py \
      $(ck "$1" "$2") $3 --n 60 2>&1 | grep -E '^\[|PRED|opposite'"
}

step "r52 010000 probe"
wait_ck r52 010000 && probe r52 010000 data/course/packed_goto_pos

step "r51 030000 probe (이름 문장, 기준)"
wait_ck r51 030000 && probe r51 030000 data/course/packed_goto

step "r52 020000 probe"
wait_ck r52 020000 && probe r52 020000 data/course/packed_goto_pos

step "r52 030000 probe"
wait_ck r52 030000 || exit 5
probe r52 030000 data/course/packed_goto_pos

step "eval r52 030000 (정책 단독 방향 문장 + Qwen 계층형)"
RUN=r52 STEP=030000 N=${N:-30} GE_CHILD=1 \
  TIERS="${TIERS:-T1:pos T2:pos T1:qpos T3b:qpos T4:qpos T3a:qpos T3c:qpos}" \
  bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_r52_030000.log" 2>&1
sed -n '/^== /,$p' "$WS/eval_out/course/goto_r52_030000.log"
rs "df -h ~ | tail -1"
echo "[gc] END $(date '+%F %T')"

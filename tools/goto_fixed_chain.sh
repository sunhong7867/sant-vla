#!/bin/bash
# 정규화 통계 교정 후 재평가 (2026-10-05): train_reasoning 이 postprocessor 를 베이스에서
# 복사해 행동 복원이 옛 통계였음(fix_postproc_stats.py). 교정한 r52 30k → E(w=1) + T1:pos,
# 이어서 r54 15k(교정 루프 확인 뒤) 진단 + E + T1:pos.  로그 eval_out/course/goto_fixed_chain.log
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_fixed_chain.log
if [ "${GC_CHILD:-0}" != 1 ]; then
  GC_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
rs() { ssh -o ConnectTimeout=15 "$SRV" "$@"; }
step() { echo; echo "======== [$(date '+%F %T')] $1 ========"; }
ev() {  # $1 run $2 step $3 tag $4 tiers $5 N
  RUN=$1 STEP=$2 TAG=$3 POLICY_GUIDE=1.0 N=$5 TIERS="$4" GE_CHILD=1 \
    bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_$3.log" 2>&1
  sed -n '/^== /,$p' "$WS/eval_out/course/goto_$3.log"
}
step "r52 030000 fixed: E + T1:pos"
ev r52 030000 r52_030000_fx "E T1:pos" 40
step "r54 015000 wait (fixed stats)"
until rs "grep -q 015000 ~/sunhong/nav-vla/logs/course/r54_fix_loop.log" 2>/dev/null; do
  rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_r54.log" 2>/dev/null && { echo "[gc] r54 train fail"; exit 5; }
  sleep 120
done
rs "cat ~/sunhong/nav-vla/logs/course/r54_fix_loop.log; cd ~/sunhong/nav-vla && C=runs/course/navvla_reasoning_r54/checkpoints/015000/pretrained_model; \
    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_frames.py \$C data/course/probe_E --guide 1 3 2>&1 | grep -E 'w='; \
    CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py \$C data/course/packed_goto_pos --n 60 --guide 1 3 2>&1 | grep -E 'PRED|opposite|guide'"
step "r54 015000: E + T1:pos"
ev r54 015000 r54_015000 "E T1:pos" 40
rs "df -h ~ | tail -1"
echo "[gc] END $(date '+%F %T')"

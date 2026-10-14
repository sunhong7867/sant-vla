#!/bin/bash
# r54(좌우 반전 + 방향 없는 문장 사본) 체인 (2026-10-05): 체크포인트마다 오프라인 진단
# (E 출발 화면 probe_frames + 언어 반사실 probe_goto_language) → 15k 에서 폐루프
# E(w=1, w=3) + T1:pos.   bash tools/goto_r54_chain.sh  (로그 eval_out/course/goto_r54_chain.log)
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_r54_chain.log
if [ "${GC_CHILD:-0}" != 1 ]; then
  GC_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
R=${R:-r54}
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
probe() {   # $1 run, $2 step  (GPU0: the serving GPU, idle between evals)
  rs "cd ~/sunhong/nav-vla && CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_frames.py \
      $(ck "$1" "$2") data/course/probe_E --guide 1 3 --state 0 0 0 0 2>&1 | grep -E '^\[|w='; \
      CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py \
      $(ck "$1" "$2") data/course/packed_goto_pos --n 60 --guide 1 3 2>&1 | grep -E 'PRED|opposite|guide'"
}
for s in 005000 010000 015000; do
  step "$R $s probe"
  wait_ck "$R" "$s" || exit 5
  probe "$R" "$s"
done
for w in 1.0 3.0; do
  step "eval $R 015000 E w=$w"
  tag=${R}_015000_g${w%.*}
  RUN=$R STEP=015000 TAG=$tag POLICY_GUIDE=$w N=40 TIERS="E" GE_CHILD=1 \
    bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_$tag.log" 2>&1
  sed -n '/^== /,$p' "$WS/eval_out/course/goto_$tag.log"
done
step "eval $R 015000 T1:pos (w=1)"
RUN=$R STEP=015000 N=30 TIERS="T1:pos" GE_CHILD=1 \
  bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_${R}_015000.log" 2>&1
sed -n '/^== /,$p' "$WS/eval_out/course/goto_${R}_015000.log"
rs "df -h ~ | tail -1"
echo "[gc] END $(date '+%F %T')"

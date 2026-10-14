#!/bin/bash
# 주말 체인 (2026-10-03): goto 수집 종료 대기 → (서버 대기) 변환 g1 → r50 학습 30k(10k 마다 저장, GPU1)
# → 체크포인트가 나올 때마다 로컬 시뮬에서 T1·T2 평가(각 30 회). 전체 단계(T3·T4) 는 최고 체크포인트로 따로.
#   bash tools/goto_weekend_chain.sh ; tail -f eval_out/course/goto_weekend_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_weekend_chain.log
if [ "${GW_CHILD:-0}" != 1 ]; then
  GW_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
RUN=${RUN:-r50}; DATA=${DATA:-g1}
step() { echo; echo "======== [$(date '+%F %T')] $1 ========"; }
rs() { ssh -o ConnectTimeout=15 "$SRV" "$@"; }

step "wait goto collection"
until grep -qE '^\[mc\] (END|no packed|ship mismatch)' "$WS/eval_out/course/goto_chain_goto.log" 2>/dev/null; do sleep 60; done
tail -5 "$WS/eval_out/course/goto_chain_goto.log"
grep -q '^\[mc\] shipped' "$WS/eval_out/course/goto_chain_goto.log" || {
  step "ship retry"
  until rs true 2>/dev/null; do echo "[gw] $(date +%T) 서버 접속 불가 — 5 분 뒤"; sleep 300; done
  rsync -a "$WS/src/sant_vla_pkg/data_course_multiobj/packed_goto/" "$SRV":'~/sunhong/nav-vla/data/course/packed_goto/' || exit 2; }

step "convert $DATA"
until rs true 2>/dev/null; do echo "[gw] $(date +%T) 서버 접속 불가 — 5 분 뒤"; sleep 300; done
scp -q "$WS/server/code/course/convert_goto.sh" "$WS/server/code/course/launch_goto.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
rs "df -h ~ | tail -1; cd ~/sunhong/nav-vla && OUT=$DATA bash code/course/convert_goto.sh 2>&1 | grep -E 'stanley|packed_|segment rows|CONVERT|Error|Traceback' | tail -6" || exit 3

step "train $RUN (GPU1, 30k)"
rs -n "cd ~/sunhong/nav-vla && RUN=$RUN DATA=$DATA GPU=1 bash code/course/launch_goto.sh" || exit 4
sleep 300
rs "grep -E 'dataset:|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log | head -3"

for s in 010000 020000 030000; do
  step "wait checkpoint $s"
  until rs "test -f ~/sunhong/nav-vla/runs/course/navvla_reasoning_$RUN/checkpoints/$s/pretrained_model/model.safetensors" 2>/dev/null; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log" 2>/dev/null && { echo "[gw] train fail"; exit 5; }
    sleep 120
  done
  sleep 60
  step "eval $RUN $s T1 T2"
  RUN=$RUN STEP=$s TIERS="T1 T2" N=30 GE_CHILD=1 bash "$WS/tools/eval/goto_stat_eval.sh" > "$WS/eval_out/course/goto_${RUN}_${s}.log" 2>&1
  sed -n '/^== /,$p' "$WS/eval_out/course/goto_${RUN}_${s}.log"
done
rs "grep 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log; df -h ~ | tail -1"
echo "[gw] END $(date '+%F %T')"

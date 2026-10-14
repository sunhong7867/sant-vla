#!/bin/bash
# G-pilot 진단 체인 (2026-10-05): rp2(rp1 5k + 10k, bs8 lr1e-5) 5k/10k, rp3(r26 + 10k, bs16 lr5e-5)
# 체크포인트마다 이름 문장 반사실 진단 + pre/post 통계 확인.  로그 eval_out/course/goto_pilot_probe.log
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto_pilot_probe.log
if [ "${GC_CHILD:-0}" != 1 ]; then
  GC_CHILD=1 setsid nohup bash "$0" "$@" >> "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
rs() { ssh -o ConnectTimeout=15 "$SRV" "$@"; }
for rc in rp2:005000 rp2:010000 rp3:010000; do
  r=${rc%%:*}; s=${rc#*:}
  C=runs/course/navvla_reasoning_$r/checkpoints/$s/pretrained_model
  echo; echo "======== [$(date '+%F %T')] $r $s ========"
  until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors" 2>/dev/null; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$r.log" 2>/dev/null && { echo "[gp] $r fail"; continue 2; }
    sleep 120
  done
  sleep 60
  rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C; \
      CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_goto_language.py $C data/course/packed_goto --n 60 2>&1 | grep -E 'PRED|opposite'"
done
echo "[gp] END $(date '+%F %T')"

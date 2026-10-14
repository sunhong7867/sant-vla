#!/usr/bin/env bash
# 2026-10-09: overnight_s3_chain 5단계(폐루프)만 재시작. 체인이 끊긴 뒤 수동 재개용.
# goto_stat_eval.sh 는 스스로 detach 하므로 ALL_DONE 을 기다려야 한다(두 런 동시 기동 금지).
set -u
WS=/home/sh/ROS2_project/sant-vla
STEPS=15000; S=$(printf '%06d' $STEPS)
L=$WS/eval_out/course/s3_closedloop_resume.log
note(){ echo "[rs $(date '+%F %T')] $*" >> "$L"; }
note "=== RESUME ==="
for R in s3 s3n; do
  GL=$WS/eval_out/course/goto_${R}_${S}.log
  : > "$GL"
  note "--- $R SEC n=30 ---"
  CKPT=runs/course/navvla_reasoning_$R/checkpoints/$S/pretrained_model \
  RUN=$R STEP=$S TIERS=SEC N=30 TAG=${R}_sec RAM_WAIT_H=6 \
    bash "$WS/tools/eval/goto_stat_eval.sh" >> "$L" 2>&1
  until grep -q "ALL_DONE" "$GL" 2>/dev/null; do
    grep -qE "BRINGUP_FAIL|RAM_WAIT_TIMEOUT" "$GL" 2>/dev/null && { note "$R 기동 실패"; break; }
    sleep 60
  done
  note "--- $R 폐루프 종료 ---"
  python3 "$WS/tools/eval/goto_analyze.py" "$WS/eval_out/course/goto_eval" "${R}_sec" >> "$L" 2>&1
done
note "=== END ==="

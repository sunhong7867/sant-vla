#!/bin/bash
# g5d 데이터 줄이기 평가 (2026-10-15, docs/experiments/goto_object/20261015_1757_g5d-data-size-prereg.md).
# g5s100 → g5s200 차례로: 서버 체크포인트(003000)가 생기면 P4t(이미지 목표, P2 와 같은 20 장면) 20 회.
# goto_stat_eval.sh 는 스스로 뒤로 빠지므로(started pid …) 끝은 그 로그의 ALL_DONE 으로 기다린다.
# 이미 돌고 있는 RUN 의 평가는 다시 띄우지 않는다 (SKIP_LAUNCH="g5s100").
#   setsid nohup bash tools/eval/g5s_p4t_chain.sh > /dev/null 2>&1 &
#   tail -f eval_out/course/g5s_p4t_chain.log
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/g5s_p4t_chain.log
exec >> "$LOG" 2>&1
exec 9> /tmp/g5s_p4t_chain2.lock
flock -n 9 || { echo "[g5s] 이미 실행 중 — 종료"; exit 1; }
SRV=autolab_sw@115.145.211.157
note() { echo "[g5s $(date '+%F %T')] $*"; }
note "=== 시작 (SKIP_LAUNCH=${SKIP_LAUNCH:-}) ==="
for RUN in g5s100 g5s200; do
  C=runs/course/navvla_reasoning_$RUN/checkpoints/003000/pretrained_model
  GE=$WS/eval_out/course/goto_${RUN}_003000.log
  w=0
  until ssh -o ConnectTimeout=20 -o BatchMode=yes "$SRV" "test -f ~/sunhong/nav-vla/$C/model.safetensors"; do
    [ $w -ge 3600 ] && { note "$RUN 체크포인트 대기 초과"; continue 2; }
    sleep 30; w=$((w+30))
  done
  before=$(grep -c ALL_DONE "$GE" 2>/dev/null); before=${before:-0}
  if [[ " ${SKIP_LAUNCH:-} " == *" $RUN "* ]]; then
    note "$RUN 평가는 이미 실행 중 — 끝나기만 기다림"; before=0
  else
    note "$RUN 체크포인트 있음 → P4t"
    RUN=$RUN STEP=003000 TIERS="P4t" N=20 TAG=${RUN}_003000 bash "$WS/tools/eval/goto_stat_eval.sh" 9>&- | tail -1
  fi
  w=0
  until [ "$(grep -c ALL_DONE "$GE" 2>/dev/null || echo 0)" -gt "$before" ]; do
    grep -qE "BRINGUP_FAIL|RAM_WAIT_TIMEOUT|원격 서빙 미확인" "$GE" 2>/dev/null && { note "$RUN 기동 실패"; tail -3 "$GE"; continue 2; }
    [ $w -ge 5400 ] && { note "$RUN 평가 대기 초과"; continue 2; }
    sleep 30; w=$((w+30))
  done
  python3 - "$WS/eval_out/course/goto_eval/${RUN}_003000_P4t.jsonl" "$RUN" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1])]
print(f"[g5s] {sys.argv[2]} P4t 성공 {sum(r['success'] for r in rows)}/{len(rows)} "
      f"strict {sum(bool(r.get('success_strict')) for r in rows)}/{len(rows)} "
      f"결과 {dict((k, sum(r['result'] == k for r in rows)) for k in set(r['result'] for r in rows))}")
PY
done
note "=== END ==="

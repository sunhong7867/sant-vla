#!/bin/bash
# 점 목표 원시 동작 폐루프 (2026-10-12 사전 등록: docs/experiments/goto_object/20261012_1850).
#   g5d 학습 완료 + a1 체인(union_avoid_chain) 종료를 기다린 뒤
#   P2 (main/alt) + P2:zero 바닥 → 사전 등록선 충족 시 P3a·P3b 자동 → 요약.
#   setsid nohup bash tools/eval/goto5d_after_a1.sh > /dev/null 2>&1 &
#   tail -f eval_out/course/goto5d_after_a1.log
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/goto5d_after_a1.log
exec >> "$LOG" 2>&1
note() { echo "[g5e $(date '+%F %T')] $*"; }
RUN=${RUN:-g5d}; STEP=${STEP:-015000}; N=${N:-20}; TAG=${TAG:-${RUN}_${STEP}}
OUT=$WS/eval_out/course/goto_eval
GE_LOG=$WS/eval_out/course/goto_${RUN}_${STEP}.log
CHAIN=$WS/eval_out/course/g5d_chain.log
UA=$WS/eval_out/course/union_avoid_chain.log

note "=== 시작: RUN=$RUN STEP=$STEP N=$N ==="
# ── 1. g5d 체크포인트 (체인 로그는 누적이므로 마지막 "=== 시작" 이후만 본다) ──
seg() { awk '/=== 시작 ===/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$CHAIN" 2>/dev/null; }
w=0
until seg | grep -q "=== END"; do
  seg | grep -qE "실패|중단|초과|불일치|아님" && { note "g5d 체인 실패"; seg | tail -3; exit 1; }
  [ $w -ge 21600 ] && { note "g5d 대기 초과(6h)"; exit 1; }; sleep 120; w=$((w+120))
done
note "g5d 완료: $(grep '=== END' "$CHAIN" | tail -1)"

# ── 1b. 시작 시각 (사용자 10-12: a1 은 01시쯤 끝나니 02:00 부터 시작) ──────
NOT_BEFORE=${NOT_BEFORE:-"2026-10-13 02:00"}
T0=$(date -d "$NOT_BEFORE" +%s)
if [ "$(date +%s)" -lt "$T0" ]; then
  note "시작 대기: $NOT_BEFORE 까지 ($(( (T0 - $(date +%s)) / 60 ))분)"
  while [ "$(date +%s)" -lt "$T0" ]; do sleep 60; done
fi
# ── 2. a1 체인(로컬 시뮬 평가 포함) 종료 대기 — 사용자 실험을 끊지 않는다 ──
w=0
while pgrep -f 'union_avoid_chai[n]' > /dev/null || pgrep -f 'collect_corpu[s]' > /dev/null \
      || pgrep -f 'avoidance_tria[l]' > /dev/null || pgrep -f 'stat_eval\.s[h]' > /dev/null; do
  [ $w -ge 43200 ] && { note "a1 체인 대기 초과(12h)"; exit 2; }
  [ $((w % 1800)) -eq 0 ] && note "a1 체인 진행 중 — 대기 ($(tail -1 "$UA" 2>/dev/null | cut -c1-80))"
  sleep 120; w=$((w+120))
done
note "a1 체인 종료 (gz 사용 가능)"
# 남은 스택이 있으면 파일 스크립트로 정리하고 리핑을 기다린다 (sim-stack-bringup §0,§3)
if [ "$(pgrep -c -f 'gz si[m]')" -gt 0 ] || [ "$(pgrep -c -f 'vla_bridge_nod[e]')" -gt 0 ]; then
  note "잔여 스택 정리: gz $(pgrep -c -f 'gz si[m]') bridge $(pgrep -c -f 'vla_bridge_nod[e]')"
  "$WS/smolvla_demo.sh" down > /dev/null 2>&1
  w=0; until [ "$(pgrep -c -f 'gz si[m]')" -eq 0 ]; do [ $w -ge 120 ] && break; sleep 5; w=$((w+5)); done
fi
note "가용 RAM $(awk '/MemAvailable/{printf "%.1f", $2/1048576}' /proc/meminfo)G"

run_tiers() {   # $1 = TIERS
  local before; before=$(grep -c "ALL_DONE" "$GE_LOG" 2>/dev/null); before=${before:-0}
  note "--- 폐루프 기동: tiers [$1] ---"
  RUN=$RUN STEP=$STEP TIERS="$1" N=$N SEED=20261090 TAG=$TAG bash "$WS/tools/eval/goto_stat_eval.sh" | tail -1
  local w=0
  until [ "$(grep -c "ALL_DONE" "$GE_LOG" 2>/dev/null; true)" -gt "$before" ] 2>/dev/null; do
    grep -qE "BRINGUP_FAIL|RAM_WAIT_TIMEOUT|원격 서빙 미확인" "$GE_LOG" 2>/dev/null && { note "기동 실패"; tail -5 "$GE_LOG"; return 1; }
    [ $w -ge 14400 ] && { note "폐루프 대기 초과(4h)"; return 1; }
    sleep 60; w=$((w+60))
  done
  grep -E '^\[P' "$GE_LOG" | tail -n 60
  return 0
}

# ── 3. P2 + 바닥 ───────────────────────────────────────────────────
run_tiers "P2 P2:zero" || exit 3
python3 "$WS/tools/eval/goto5d_summary.py" "$OUT/${TAG}_P2.jsonl" "$OUT/${TAG}_P2zero.jsonl"

# 사전 등록 판정: main >= 14/20, alt >= 14/20, 바닥 < 10/20 → P3 진행
DECISION=$(python3 - "$OUT/${TAG}_P2.jsonl" "$OUT/${TAG}_P2zero.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
zero = [json.loads(l) for l in open(sys.argv[2]) if l.strip()]
main = [r for r in rows if r.get("arm") == "main"]; alt = [r for r in rows if r.get("arm") == "alt"]
ok = lambda rs: sum(1 for r in rs if r["success"])
m, a, z = ok(main), ok(alt), ok(zero)
print(f"P2 main {m}/{len(main)} alt {a}/{len(alt)} zero {z}/{len(zero)}")
verdict = "PASS" if (m >= 14 and a >= 14 and z < 10) else ("FLOOR_HIGH" if (m >= 14 and a >= 14) else "REJECT")
print(verdict)
PY
)
note "P2 판정: $DECISION"
case "$DECISION" in
  *PASS)
    run_tiers "P3a P3b" || exit 4
    python3 "$WS/tools/eval/goto5d_summary.py" "$OUT/${TAG}_P3a.jsonl" "$OUT/${TAG}_P3b.jsonl" ;;
  *FLOOR_HIGH) note "바닥 >= 10/20: 하네스가 목표를 요구하지 않음 → 배치 재설계 (P3 보류)" ;;
  *) note "P2 기각 — 사전 등록대로 P3/P4 진행 안 함 (화면 표시 방식 1런만 검토 대상)" ;;
esac
note "=== END ==="

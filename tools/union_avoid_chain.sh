#!/bin/bash
# ③ 회피 합집합 학습 체인 (2026-10-12): 다장애물 수집(multi_chain mrun) 끝 → u1 변환(v3+v3y+mrun) →
# a1 학습(GPU1, c0 와 같은 레시피 + obstacle-boost) ‖ 그동안 c0 대조군 회피 평가(로컬 시뮬, 정책 서버 GPU0)
# → a1 ①② 유지 프로브(c0 와 같은 슬롯) → a1 회피 평가 → 요약.
# 사전 기각선: docs/experiments/avoidance/20261012_*_a1-union-preregistration.md
#   bash tools/union_avoid_chain.sh ; tail -f eval_out/course/union_avoid_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/union_avoid_chain.log
if [ "${UA_CHILD:-0}" != 1 ]; then
  UA_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
# 단일 실행 잠금 (2026-10-12 18:16: 두 세션이 7 초 차이로 체인을 띄워 같은 partition 에서 수집기 둘이 섞였다)
exec 9> /tmp/union_avoid_chain.lock
flock -n 9 || { echo "[ua] 다른 union_avoid_chain 이 이미 실행 중 — 종료"; exit 9; }
SRV=autolab_sw@115.145.211.157
RUN=${RUN:-a1}; DATA=${DATA:-u1}; STEPS=${STEPS:-15000}; S=$(printf '%06d' $STEPS)
CONDS=${CONDS:-"ours adj empty ours1 empty1 held"}
step() { echo; echo "======== [$(date '+%F %T')] $1 ========"; }
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }

stat_run() {   # $1 = RUN (checkpoint runs/course/navvla_reasoning_$1)
  until ! pgrep -f 'gz si[m]|avoidance_tria[l]|episode_recorde[r]' >/dev/null; do sleep 60; done
  RUN=$1 NPOS=20 BATCH=20 CONDS="$CONDS" bash "$WS/tools/eval/stat_eval.sh"
  sleep 10
  until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_$1.log" 2>/dev/null; do sleep 60; done
  sed -n '/collected/,$p' "$WS/eval_out/course/stat_$1.log"
}

step "wait collection (multi_chain mrun)"
until grep -qE '^\[mc\] (END|no packed|ship mismatch|stack running)' "$WS/eval_out/course/multi_chain_mrun.log" 2>/dev/null; do
  pgrep -f 'multi_chai[n].sh' >/dev/null || { echo "[ua] multi_chain 이 END 없이 끝남"; tail -8 "$WS/eval_out/course/multi_chain_mrun.log"; exit 1; }
  sleep 60
done
tail -8 "$WS/eval_out/course/multi_chain_mrun.log"
grep -q '^\[mc\] END' "$WS/eval_out/course/multi_chain_mrun.log" || exit 1

# ── 연속 회피 보충 (2026-10-12): 짧은 간격으로 다른 차선에 붙인 장애물 쌍 → 차선 변경 시점이 장애물로 정해짐 ──
CHAIN_P=${CHAIN_P:-0.6}; NSUPP=${NSUPP:-40}
P=$WS/src/sant_vla_pkg/data_course_multiobj
if [ ! -f "$P/packed_mrunc/index.jsonl" ]; then
  if [ "${SKIP_PILOT:-0}" != 1 ]; then
  step "chained pilot (3 starts x v0,v1, chain_p $CHAIN_P)"
  rm -rf "$P/packed_mcpilot"
  # session_sec_good / session_sec2_good 처럼 날짜가 아닌 세션 디렉터리가 있어서
  # session_* 글롭 + sort 는 늘 그것들을 마지막으로 돌려준다('s' > '2'). 그래서
  # before == sess 가 되어 시범이 정상 수집돼도 "세션 없음" 으로 죽었다 (10-12 18:14).
  before=$(ls -d "$P"/session_[0-9]* | sort | tail -1)
  TAG=mcpilot NRUNS=3 OB_VARIANTS=v0,v1 MULTI_TRIGGER=7.5,10 MULTI_RAMP=5,8 MULTI_CHAIN_P=$CHAIN_P SEED_TRAIN=20261213 \
    DIV_CHILD=1 bash "$WS/tools/multi_run.sh" > "$WS/eval_out/course/div_run_mcpilot.log" 2>&1
  tail -3 "$WS/eval_out/course/div_run_mcpilot.log"
  sess=$(ls -d "$P"/session_[0-9]* | sort | tail -1)
  [ "$sess" != "$before" ] || { echo "[ua] 시범 세션 없음"; exit 1; }
  python3 "$WS/tools/eval/check_multi_session.py" "$sess" | tee "$WS/eval_out/course/mcpilot_check.txt"
  NCOL=$(grep -c '"termination": "collision"' "$sess/manifest.jsonl")
  NW=$(awk '/^경고/ {print $2}' "$WS/eval_out/course/mcpilot_check.txt")
  echo "[ua] 시범 충돌 $NCOL, 근접 경고 $NW"
  [ "$NCOL" = 0 ] && [ "$NW" = 0 ] || { echo "[ua] 시범 실패 — 보충 수집·학습 중단"; exit 1; }
  fi   # SKIP_PILOT=1: 시범을 이미 수동 점검한 경우 (10-12 18:20 mcpilot 통과)
  step "chained collection mrunc ($NSUPP starts x v0,v1)"
  TAG=mrunc NRUNS=$NSUPP OB_VARIANTS=v0,v1 MULTI_TRIGGER=7.5,10 MULTI_RAMP=5,8 MULTI_CHAIN_P=$CHAIN_P SEED_TRAIN=20261214 \
    MC_CHILD=1 bash "$WS/tools/multi_chain.sh" > "$WS/eval_out/course/multi_chain_mrunc.log" 2>&1
  tail -6 "$WS/eval_out/course/multi_chain_mrunc.log"
  grep -q '^\[mc\] END' "$WS/eval_out/course/multi_chain_mrunc.log" || { echo "[ua] mrunc 수집 실패"; exit 1; }
  python3 "$WS/tools/eval/check_multi_session.py" "$(ls -d "$P"/session_[0-9]* | sort | tail -1)" | tail -1
fi

step "convert $DATA"
scp -q "$WS/server/code/course/convert_u1.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
rs "cd ~/sunhong/nav-vla && OUT=$DATA bash code/course/convert_u1.sh 2>&1 | grep -vE 'it/s|%\|' | tail -12"
rs "test -f ~/sunhong/nav-vla/data/course/lerobot/$DATA/reasoning_labels.jsonl" || { echo "[ua] 변환 실패"; exit 2; }

step "train $RUN (GPU1, stock base, bs8, $STEPS step, ce 0, obstacle-boost 4 sampler + v0 twin)"
STOCK=$(rs 'ls -d ~/.cache/huggingface/hub/models--lerobot--smolvla_base/snapshots/*/ | head -1' | tr -d '\r')
R26=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
rs "cd ~/sunhong/nav-vla && RUN=$RUN DATA=$DATA GPU=1 STEPS=$STEPS SAVE=$STEPS BASE='$STOCK' BASE_CONFIG='$R26' \
    EXTRA='--batch-size 8 --ce-weight 0 --obstacle-boost 4.0 --boost-target sampler --contrast-twin-boost --contrast-twin-variants v0' bash code/course/launch_goto.sh" || exit 3
sleep 300
rs "grep -E 'dataset|obstacle boost|GO-transition|twin|sampled share|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log | head -10"

step "control c0 avoidance eval (while $RUN trains)"
stat_run c0

step "wait $RUN"
C=runs/course/navvla_reasoning_$RUN/checkpoints/$S/pretrained_model
until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors"; do
  rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log" && {
    echo "[ua] $RUN 학습 실패"; rs "tail -20 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log"; exit 4; }
  sleep 180
done
sleep 60
rs "grep -E 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log; grep '^step' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log | tail -1"

step "$RUN ①② retention probe (c0 = ratio 0.89, same slot)"
rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2; \
    CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_goto_language.py $C \
      data/course/packed_v3g_staging --n 80 \
      --slot intent_id=ring_goal --slot speed_level=fast 2>&1 | grep -E 'slot|PRED'"

step "$RUN avoidance eval"
stat_run "$RUN"

step "summary"
python3 "$WS/tools/eval/stat_analyze.py" c0 2>&1 | tail -15
python3 "$WS/tools/eval/stat_analyze.py" "$RUN" 2>&1 | tail -15
echo "[ua] END $(date '+%F %T')"

#!/usr/bin/env bash
# 2026-10-09: 조합 일반화 홀드아웃 학습 3런 (c0 천장 / c1 홀드아웃 / cn 바닥).
# 설계: docs/experiments/reports/20261009_1559_composition-generalization-holdout-plan.md
# 홀드아웃 = intent_id=ring_goal AND lane=lane2 AND speed_level=fast (74 ep 삼중 교차).
# 해설 라벨이 없으므로 --ce-weight 0 (빈 reasoning_labels.jsonl).
set -u
WS=/home/sh/ROS2_project/sant-vla
SRV=autolab_sw@115.145.211.157
L=$WS/eval_out/course/comp_train.log
STEPS=15000; S=$(printf '%06d' $STEPS); BS=8
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[cmp $(date '+%F %T')] $*" >> "$L"; }

note "=== START ==="

# ── 1. 변환 완료 대기 + 홀드아웃 수 검증 ──────────────────────────
CL=/home/autolab_sw/sunhong/nav-vla/logs/course/convert_v3g.log
w=0
until rs "grep -q CONVERT_V3G_OK $CL"; do
  rs "grep -qE 'CONVERT_ABORT|Traceback' $CL" && { note "변환 실패"; rs "tail -20 $CL"; exit 2; }
  [ "$w" -ge 3600 ] && { note "변환 대기 초과"; exit 2; }
  sleep 60; w=$((w+60))
done
note "변환 완료"
EX=$(rs "grep -o 'holdout: excluded [0-9]* episodes' $CL | grep -o '[0-9]*'" | tr -d ' \r')
note "홀드아웃 제외 ${EX} ep (기대 74)"
[ "$EX" = "74" ] || { note "제외 수 불일치 — 중단 (설계 전제 깨짐)"; exit 3; }
for d in v3g_full v3g_hold; do
  rs "test -f /home/autolab_sw/sunhong/nav-vla/data/course/lerobot/$d/reasoning_labels.jsonl" \
    || { note "$d 없음 — 중단"; exit 3; }
done
rs "grep -E 'episodes, [0-9]+ frames at' $CL" >> "$L" 2>&1

# ── 2. 학습 3런 (순차, GPU0) ──────────────────────────────────────
STOCK=$(rs 'ls -d ~/.cache/huggingface/hub/models--lerobot--smolvla_base/snapshots/*/ | head -1' | tr -d '\r')
R26=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
note "stock base: $STOCK"

train_one() {   # $1=RUN  $2=DATA  $3=추가 EXTRA
  local R=$1 D=$2 X=$3
  local C=runs/course/navvla_reasoning_$R/checkpoints/$S/pretrained_model
  rs "test -f /home/autolab_sw/sunhong/nav-vla/$C/model.safetensors" && { note "$R 이미 완료"; return 0; }
  local w=0
  until [ "$(rs 'nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0' | tr -d ' \r')" -ge 9000 ]; do
    [ "$w" -ge 5400 ] && { note "$R: GPU 대기 초과"; return 1; }
    sleep 300; w=$((w+300))
  done
  note "--- $R 기동 (data=$D, stock base, bs${BS}, ${STEPS} step, extra='$X') ---"
  rs "cd ~/sunhong/nav-vla && RUN=$R DATA=$D GPU=0 STEPS=$STEPS SAVE=$STEPS \
      BASE='$STOCK' BASE_CONFIG='$R26' EXTRA='--batch-size $BS --ce-weight 0 $X' \
      bash code/course/launch_goto.sh" || { note "$R 기동 실패"; return 1; }
  sleep 150
  rs "grep -vE 'torch_dtype|^Loading  |Reducing' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log | head -8" >> "$L" 2>&1
  until rs "test -f /home/autolab_sw/sunhong/nav-vla/$C/model.safetensors"; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log" && {
      note "$R 학습 실패"; rs "tail -20 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log" >> "$L" 2>&1; return 1; }
    sleep 180
  done
  sleep 45
  note "--- $R 프로브 (홀드아웃 칸 짝: ring_goal x fast) ---"
  rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2; \
      CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py $C \
        data/course/packed_v3g_staging --n 80 \
        --slot intent_id=ring_goal --slot speed_level=fast 2>&1 | grep -E 'slot|PRED'" >> "$L" 2>&1
  rs "grep '^step' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log | tail -1" >> "$L" 2>&1
  note "--- $R 완료 ---"
}

train_one c0 v3g_full ""                      # 천장: 조합을 본 모델
train_one c1 v3g_hold ""                      # 본 실험: 조합만 안 본 모델
train_one cn v3g_hold "--blank-task Drive."   # 바닥: 문장 무조건 모델

note "=== END ==="
note "판정: c1 ratio >= 0.70 x c0 ratio -> 조합 일반화 성립."
note "      c1 이 cn 과 유의 차 없으면 실패로 적는다(짝 n~74)."

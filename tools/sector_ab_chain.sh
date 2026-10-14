#!/bin/bash
# 섹터 A/B 학습 3런 순차 (2026-10-08). GPU0 하나만 비어 있어 동시 실행 불가
# (GPU1 은 타 사용자 19G). 런마다 끝나면 통계 교정 + 섹터 반사실 프로브.
#
#   setsid nohup bash tools/sector_ab_chain.sh > /dev/null 2>&1 &
#   tail -f eval_out/course/sector_ab_chain.log
#
# s2  = r26 베이스 + 프레임별 섹터 라벨          (주 실험)
# s2n = 위와 동일 + 상수 문장 'Drive.'            (대조군 — 이것 없이는 아무 주장도 못 한다)
# s3  = stock smolvla_base + r26 설정             (차선 탐색 사전 없음: A/B)
#
# 왜 이 순서인가: s2·s2n 쌍이 "문장을 읽는가"에 답하고, s3 는 "우측 쏠림이 베이스
# 사전인가"에 답한다. 전자가 먼저다 — 후자가 유의미해지려면 섹터 학습이 애초에
# 먹혀야 한다.
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sector_ab_chain.log
SRV=autolab_sw@115.145.211.157
STEPS=${STEPS:-10000}
DATA=${DATA:-g5}
exec >> "$LOG" 2>&1
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[ab $(date '+%F %T')] $*"; }

STOCK=$(rs 'ls -d ~/.cache/huggingface/hub/models--lerobot--smolvla_base/snapshots/*/ | head -1' | tr -d '\r')
R26=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
note "=== 시작: DATA=$DATA STEPS=$STEPS ==="
note "stock base: $STOCK"

run_one() {   # $1=RUN  $2=추가 EXTRA  $3=BASE  $4=BASE_CONFIG
  local R=$1
  if rs "test -f ~/sunhong/nav-vla/runs/course/navvla_reasoning_$R/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model/model.safetensors"; then
    note "$R 이미 완료 — 건너뜀"; return 0
  fi
  # GPU0 에 13.5G 이상 여유가 생길 때까지 대기 (타 사용자와 공유)
  local waited=0
  until [ "$(rs 'nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0' | tr -d " \r")" -ge 13500 ]; do
    [ "$waited" -ge 7200 ] && { note "$R: GPU0 2시간 대기 초과 — 중단"; return 1; }
    sleep 300; waited=$((waited+300))
  done
  note "--- $R 기동 (GPU0) ---"
  rs "cd ~/sunhong/nav-vla && RUN=$R DATA=$DATA GPU=0 STEPS=$STEPS SAVE=$STEPS \
      BASE='$3' ${4:+BASE_CONFIG='$4'} EXTRA='--batch-size 16 --sector-balance $2' \
      bash code/course/launch_goto.sh"
  sleep 120
  rs "sed -n '1,12p' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log" | grep -vE "torch_dtype|Loading|Reducing"
  local C=runs/course/navvla_reasoning_$R/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model
  until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors"; do
    if rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log"; then
      note "$R 실패"; rs "tail -18 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log"; return 1
    fi
    sleep 180
  done
  sleep 60
  note "--- $R 프로브 ---"
  rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2; \
      CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py $C \
        data/course/packed_sec --n 60 2>&1 | grep -E 'PRED|instructed side'"
  note "--- $R 완료 ---"
}

run_one s2  ""                      "$R26"   ""
run_one s2n "--blank-task Drive."   "$R26"   ""
run_one s3  ""                      "$STOCK" "$R26"

note "=== END ==="
note "판정: s2 가 s2n 을 유의하게 넘어야 '문장을 읽는다'(n=42 기준 27/42=64%)."
note "      s3 는 평면 우측 쏠림(현재 64%)이 내려가는지로 본다 — 폐루프 측정 필요."

#!/bin/bash
# v8 야간 파이프라인 후반부: finalize 2-4단계 → 서버 반입 → lerobot 변환 → 60K 학습 개시
# (verify는 zone-축 별칭 패치 후 PASS 확인됨 — 2026-08-21 22:08)
set -uo pipefail

WS=/home/sh/ROS2_project/sant-vla
S=$WS/src/sant_vla_pkg/scripts
SESS=$(ls -dt $WS/src/sant_vla_pkg/data_v8/session_*[0-9] 2>/dev/null | head -1)
PACK=$WS/src/sant_vla_pkg/data_v8/packed_v8
SRV=autolab_sw@115.145.211.157
BASE='~/sunhong/nav-vla'
OUT=$WS/eval_out/v8_collect

step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }
echo "session: $SESS"

# collect_v8_overnight.sh의 자동 finalize가 성공했으면 2-4단계는 이미 끝나 있다.
N_LOCAL=$(find "$PACK" -type f 2>/dev/null | wc -l)
if [ "$N_LOCAL" -lt 100 ]; then
  step "1/4 verify"
  python3 "$S/verify_corpus.py" "$SESS" --json "$WS/verify_report.json" \
    || { echo VERIFY_FAIL; exit 2; }

  step "2/4 resample 10Hz"
  python3 "$S/resample_episodes.py" --session "$SESS" \
      --yaw-offset-deg -90 --pose-source tf || { echo RESAMPLE_FAIL; exit 2; }

  step "3/4 CMI"
  for axis in ordinal lane speed; do
    python3 "$S/measure_cmi.py" "$SESS" --axis "$axis" \
        --json "$WS/cmi_${axis}_v8.json" || true
  done

  step "4/4 package"
  rm -rf "$PACK"
  python3 "$S/package_corpus.py" "$PACK" "$SESS" || { echo PACKAGE_FAIL; exit 3; }
  N_LOCAL=$(find "$PACK" -type f | wc -l)
fi
echo "packed files: $N_LOCAL"
[ "$N_LOCAL" -ge 100 ] || { echo PACK_TOO_SMALL; exit 3; }

step "ship packed_v8"
ssh "$SRV" "mkdir -p $BASE/data/packed_v8"
rsync -a "$PACK"/ "$SRV":'~/sunhong/nav-vla/data/packed_v8/' || { echo RSYNC_FAIL; exit 4; }
N_REMOTE=$(ssh "$SRV" "find $BASE/data/packed_v8 -type f | wc -l")
echo "local $N_LOCAL / remote $N_REMOTE"
[ "$N_LOCAL" = "$N_REMOTE" ] || { echo COUNT_MISMATCH; exit 4; }

step "ship raw session (source of record)"
ssh "$SRV" "mkdir -p $BASE/data/raw_v8_30hz"
rsync -a "$SESS" "$SRV":'~/sunhong/nav-vla/data/raw_v8_30hz/' || echo RAW_RSYNC_FAIL_nonfatal

step "convert lerobot/v8"
ssh "$SRV" "cd ~/sunhong/nav-vla && rm -rf data/lerobot/v8 && \
  ./venv/bin/python code/to_lerobot.py data/packed_v8 \
    --repo-id sunhong/navvla_sim_v8 --out data/lerobot/v8 && echo CONVERT_DONE" \
  || { echo CONVERT_FAIL; exit 5; }

step "disk check + launch training (60K, GPU1/3090)"
ssh "$SRV" "df -h ~ | tail -1"
ssh "$SRV" "cd ~/sunhong/nav-vla && [ ! -d runs/navvla_smolvla_v8 ] || { echo RUN_DIR_EXISTS; exit 9; } && \
  setsid nohup env GPU=1 BATCH=8 STEPS=60000 WORKERS=8 SAVE_FREQ=5000 \
    bash code/train_smolvla.sh \
      /home/autolab_sw/sunhong/nav-vla/data/lerobot/v8 \
      sunhong/navvla_sim_v8 navvla_smolvla_v8 \
    > /dev/null 2>&1 < /dev/null & echo TRAIN_LAUNCHED" \
  || { echo TRAIN_LAUNCH_FAIL; exit 6; }

step "confirm training started"
sleep 240
ssh "$SRV" "tail -5 ~/sunhong/nav-vla/logs/navvla_smolvla_v8.log 2>/dev/null; \
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader"
echo
echo "[v8-train] 전체 완료 $(date +%H:%M) — 학습은 서버에서 계속 (약 8.6h)"

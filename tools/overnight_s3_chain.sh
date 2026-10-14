#!/bin/bash
# 밤샘 체인 (2026-10-08 22:35): 섹터 재수집 → 라벨 → g6 변환 → s3/s3n 학습 → 프로브 → 폐루프.
# 목표: 10-09 10:00 까지 학습·평가 완료.
#
#   setsid nohup bash tools/overnight_s3_chain.sh > /dev/null 2>&1 &
#   tail -f eval_out/course/overnight_s3.log
#
# s3  = stock smolvla_base + r26 설정 + 섹터 데이터        (차선 탐색 사전 없음)
# s3n = 위와 동일 + 상수 문장 'Drive.'                      (대조군)
#
# 왜 새 베이스인가: r26 베이스에서는 goto 미세조정이 베이스의 방향 반응을 파괴했다
# (0.82 -> s2 0.04 / s2n 0.16 / b1 0.06). 문장 유무와 무관하게 떨어지므로 원인은
# 학습 자체다. 파괴할 사전이 없는 베이스에서 섹터 행동을 처음부터 배우게 한다.
#
# bs8 인 이유: 새 베이스는 0.281 s/step (r26 베이스 bs16 은 0.775) 이라 두 런을
# 순차로 돌려도 2.4h 에 끝난다. s3/s3n 쌍이 서로 같은 설정이면 비교가 성립한다.
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/overnight_s3.log
SRV=autolab_sw@115.145.211.157
TAG=sec2
OUT=g6
STEPS=${STEPS:-15000}
BS=${BS:-8}
exec >> "$LOG" 2>&1
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[ovn $(date '+%F %T')] $*"; }
D=$WS/src/sant_vla_pkg/data_course_multiobj/packed_$TAG

note "=== 시작 (목표 10-09 10:00) ==="

# ── 1. 수집 완료 대기 ───────────────────────────────────────────────
RUNLOG=$WS/eval_out/course/div_run_${TAG}.log
# 2026-10-09: 이미 패킹이 끝나 있으면 기다리지 않는다. 첫 실행은 449 ep 중 3 ep 의
# 프레임 시퀀스 결함에 verify 가 fail-fast 로 걸려 02:15 에 중단됐다(레코더 수정은
# 작동 — frames 빈 것 0건). 정상분 446 ep 로 다시 패킹해 400 ep 를 얻었다.
if [ -f "$D/index.jsonl" ]; then
  note "packed_${TAG} 이미 존재 ($(wc -l < "$D/index.jsonl") ep) — 수집 대기 생략"
else
while :; do
  grep -q "ALL_DONE" "$RUNLOG" 2>/dev/null && { note "수집 ALL_DONE"; break; }
  if grep -qE "RAM 중단|packed_${TAG} 없음|collect rc=[1-9]" "$RUNLOG" 2>/dev/null; then
    note "수집 실패"; tail -6 "$RUNLOG"; exit 4
  fi
  sleep 120
done
fi
[ -f "$D/index.jsonl" ] || { note "$D/index.jsonl 없음 — 중단"; exit 5; }
note "packed_${TAG}: $(wc -l < "$D/index.jsonl") 에피소드, $(du -sh "$D" | cut -f1)"

# ── 2. 해설 라벨 (없으면 convert 가 조용히 0개 연결한다) ────────────
NEP=$(wc -l < "$D/index.jsonl"); NLAB=$(ls "$D"/*/reasoning.jsonl 2>/dev/null | wc -l)
if [ "$NLAB" -lt "$NEP" ]; then
  note "라벨 생성 ($NLAB/$NEP)"
  python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D" 2>&1 | tail -2 || { note "라벨 실패"; exit 9; }
fi
NLAB=$(ls "$D"/*/reasoning.jsonl 2>/dev/null | wc -l)
note "라벨 $NLAB/$NEP"
[ "$NLAB" -gt 0 ] || { note "라벨 0 — 중단"; exit 9; }

# ── 3. 업로드 + 변환 (기존 packed_sec 292 와 합친다) ────────────────
note "업로드 → data/course/packed_${TAG}"
rsync -a --info=stats2 "$D/" "$SRV:~/sunhong/nav-vla/data/course/packed_${TAG}/" | tail -2 \
  || { note "rsync 실패"; exit 7; }
LN=$(find "$D" -type f | wc -l); SN=$(rs "find ~/sunhong/nav-vla/data/course/packed_${TAG} -type f | wc -l")
note "파일 수 로컬 $LN / 서버 $SN"
[ "$SN" = "$LN" ] || { note "불일치 — 중단"; exit 7; }

FREE=$(rs "df -BG --output=avail ~ | tail -1 | tr -dc 0-9")
note "서버 여유 ${FREE}G"
[ "${FREE:-0}" -ge 6 ] || { note "여유 부족 — 중단"; exit 6; }

note "변환 → data/course/lerobot/${OUT} (packed_sec + packed_${TAG})"
rs "cd ~/sunhong/nav-vla && rm -rf data/course/lerobot/${OUT} data/course/packed_${OUT}_staging && \
    OUT=${OUT} SRCS='data/course/packed_sec data/course/packed_${TAG}' \
    EXTRA_TOLEROBOT='--sector-per-frame' bash code/course/convert_goto.sh 2>&1 | tail -5" \
  || { note "변환 실패"; exit 8; }
rs "test -d ~/sunhong/nav-vla/data/course/lerobot/${OUT}" || { note "변환 결과 없음"; exit 8; }

# ── 4. 학습 2런 (순차, GPU0) ────────────────────────────────────────
STOCK=$(rs 'ls -d ~/.cache/huggingface/hub/models--lerobot--smolvla_base/snapshots/*/ | head -1' | tr -d '\r')
R26=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
train_one() {   # $1=RUN $2=추가 EXTRA
  local R=$1 C=runs/course/navvla_reasoning_$1/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model
  rs "test -f ~/sunhong/nav-vla/$C/model.safetensors" && { note "$R 이미 완료"; return 0; }
  local w=0
  until [ "$(rs 'nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0' | tr -d " \r")" -ge 9000 ]; do
    [ "$w" -ge 5400 ] && { note "$R: GPU 대기 초과"; return 1; }
    sleep 300; w=$((w+300))
  done
  note "--- $R 기동 (stock base, bs${BS}, ${STEPS} step) ---"
  rs "cd ~/sunhong/nav-vla && RUN=$R DATA=$OUT GPU=0 STEPS=$STEPS SAVE=$STEPS \
      BASE='$STOCK' BASE_CONFIG='$R26' EXTRA='--batch-size $BS --sector-balance $2' \
      bash code/course/launch_goto.sh"
  sleep 150
  rs "grep -vE 'torch_dtype|^Loading  |Reducing' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log | head -6"
  until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors"; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log" && {
      note "$R 실패"; rs "tail -15 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log"; return 1; }
    sleep 180
  done
  sleep 45
  note "--- $R 프로브 ---"
  rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2; \
      CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_goto_language.py $C \
        data/course/packed_sec --n 60 2>&1 | grep -E 'PRED|instructed side'"
  rs "grep '^step' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$R.log | tail -1"
  note "--- $R 완료 ---"
}
train_one s3  ""
train_one s3n "--blank-task Drive."

# ── 5. 폐루프 (노트북 시뮬) ─────────────────────────────────────────
for R in s3 s3n; do
  C=runs/course/navvla_reasoning_$R/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model
  rs "test -f ~/sunhong/nav-vla/$C/model.safetensors" || { note "$R 체크포인트 없음 — 폐루프 생략"; continue; }
  note "--- $R 폐루프 SEC n=30 ---"
  CKPT=$C RUN=$R STEP=$(printf '%06d' "$STEPS") TIERS=SEC N=30 TAG=${R}_sec \
    bash "$WS/tools/eval/goto_stat_eval.sh"
  GL=$WS/eval_out/course/goto_${R}_$(printf '%06d' "$STEPS").log
  until grep -q "ALL_DONE" "$GL" 2>/dev/null; do
    grep -qE "BRINGUP_FAIL|RAM_WAIT_TIMEOUT" "$GL" 2>/dev/null && { note "$R 폐루프 기동 실패"; break; }
    sleep 60
  done
  python3 "$WS/tools/eval/goto_analyze.py" "$WS/eval_out/course/goto_eval" "${R}_sec" 2>&1 | tail -6
done

note "=== END ==="
note "판정: s3 가 s3n 을 유의하게 넘어야 '문장을 읽는다'(n=42 기준 27/42=64%)."
note "      s2/s2n (r26 베이스) 은 38/55 vs 41/55, p=0.672 로 구별되지 않았다."

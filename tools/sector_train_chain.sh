#!/bin/bash
# 섹터 수집 완료 → 서버 업로드 → lerobot 변환 → 학습 2종(문장 / 상수 문장 대조군) → 프로브
# (2026-10-07). 수집이 끝날 때까지 기다린 뒤 알아서 진행한다.
#
#   setsid nohup bash tools/sector_train_chain.sh > /dev/null 2>&1 < /dev/null &
#   tail -f eval_out/course/sector_train_chain.log
#
# 대조군이 핵심이다: b1/b0 에서 문장 유무가 구별되지 않았으므로(22/42 vs 23/42),
# 섹터 설계가 작동한다는 주장은 같은 설정의 상수 문장 런과 비교해야만 성립한다.
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sector_train_chain.log
SRV=autolab_sw@115.145.211.157
TAG=${TAG:-sec}
OUT=${OUT:-g4}
STEPS=${STEPS:-10000}
MIN_FREE_G=${MIN_FREE_G:-6}
exec >> "$LOG" 2>&1
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[chain $(date '+%F %T')] $*"; }

note "=== 시작: TAG=$TAG OUT=$OUT STEPS=$STEPS ==="

# ── 1. 수집 완료 대기 ───────────────────────────────────────────────────
RUNLOG=$WS/eval_out/course/div_run_${TAG}.log
D=$WS/src/sant_vla_pkg/data_course_multiobj/packed_${TAG}
# 2026-10-07: 이미 패킹이 끝나 있으면 기다리지 않는다. 첫 실행은 수집이 실패해
# (레코더 쓰기 스레드 사망, 283/596 손실) 중단됐고, 정상분만 다시 패킹한 뒤
# 같은 스크립트로 재시작할 수 있어야 한다.
if [ -f "$D/index.jsonl" ]; then
  note "packed_${TAG} 이미 존재 — 수집 대기 생략"
else
while :; do
  grep -q "ALL_DONE" "$RUNLOG" 2>/dev/null && { note "수집 ALL_DONE"; break; }
  if grep -qE "RAM 중단|packed_${TAG} 없음|collect rc=[1-9]" "$RUNLOG" 2>/dev/null; then
    note "수집 실패 — 중단"; tail -5 "$RUNLOG"; exit 4
  fi
  sleep 120
done
fi
[ -f "$D/index.jsonl" ] || { note "$D/index.jsonl 없음 — 중단"; exit 5; }
NEP=$(wc -l < "$D/index.jsonl")
note "packed_${TAG}: ${NEP} 에피소드, $(du -sh "$D" | cut -f1)"

# ── 2. 서버 여유 확인 (체크포인트 1개가 1.05G, 런 2개) ──────────────────
FREE=$(rs "df -BG --output=avail ~ | tail -1 | tr -dc 0-9")
note "서버 여유 ${FREE}G (필요 ${MIN_FREE_G}G 이상)"
if [ -z "$FREE" ] || [ "$FREE" -lt "$MIN_FREE_G" ]; then
  note "여유 부족 — 진단 끝난 체크포인트를 지우고 다시 실행할 것:"
  note "  runs/course/navvla_reasoning_b1, _b0 (22/42·23/42 기록 완료, 각 2.1G)"
  exit 6
fi

# ── 3. 업로드 + 변환 ────────────────────────────────────────────────────
note "업로드 → data/course/packed_${TAG}"
rsync -a --info=stats2 "$D/" "$SRV:~/sunhong/nav-vla/data/course/packed_${TAG}/" | tail -3 \
  || { note "rsync 실패"; exit 7; }
SN=$(rs "find ~/sunhong/nav-vla/data/course/packed_${TAG} -type f | wc -l")
LN=$(find "$D" -type f | wc -l)
note "파일 수 로컬 ${LN} / 서버 ${SN}"
[ "$SN" = "$LN" ] || { note "파일 수 불일치 — 중단"; exit 7; }

# 2026-10-08: 해설 라벨이 없으면 convert_goto.sh 가 그 소스를 조용히 건너뛴다.
# packed_sec 292개에 reasoning.jsonl 이 없어 g4 가 Stanley 109개만 담겼고,
# s1/s0 를 2시간 학습해 섹터 결과처럼 비교했다. 패킹 직후 라벨이 필수다.
note "해설 라벨 생성 (label_reasoning.py)"
NLAB=$(ls "$D"/*/reasoning.jsonl 2>/dev/null | wc -l)
NEP=$(wc -l < "$D/index.jsonl")
if [ "$NLAB" -lt "$NEP" ]; then
  python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D" 2>&1 | tail -3 \
    || { note "라벨링 실패"; exit 9; }
fi
NLAB=$(ls "$D"/*/reasoning.jsonl 2>/dev/null | wc -l)
note "라벨 보유 ${NLAB}/${NEP}"
[ "$NLAB" -gt 0 ] || { note "라벨 0 — 중단"; exit 9; }

note "변환 → data/course/lerobot/${OUT}"
rs "cd ~/sunhong/nav-vla && OUT=${OUT} SRCS='data/course/packed_${TAG}' bash code/course/convert_goto.sh 2>&1 | tail -6" \
  || { note "변환 실패"; exit 8; }
rs "test -d ~/sunhong/nav-vla/data/course/lerobot/${OUT}" || { note "변환 결과 없음"; exit 8; }

# ── 4. 학습 2종 — 문장 / 상수 문장 대조군 ───────────────────────────────
note "학습 기동: s1(문장) GPU1, s0(상수 문장 'Drive.') GPU0, ${STEPS} step, 체크포인트 1개"
rs "cd ~/sunhong/nav-vla && RUN=s1 DATA=${OUT} GPU=1 STEPS=${STEPS} SAVE=${STEPS} EXTRA='--batch-size 16' bash code/course/launch_goto.sh"
sleep 30
rs "cd ~/sunhong/nav-vla && RUN=s0 DATA=${OUT} GPU=0 STEPS=${STEPS} SAVE=${STEPS} EXTRA='--batch-size 16 --blank-task Drive.' bash code/course/launch_goto.sh"
sleep 60
for r in s1 s0; do
  note "--- $r 기동 확인 ---"
  rs "tail -6 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$r.log 2>/dev/null"
done

# ── 5. 완료 대기 + 프로브 ───────────────────────────────────────────────
for r in s1 s0; do
  C=runs/course/navvla_reasoning_$r/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model
  note "대기: $r $C"
  until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors" 2>/dev/null; do
    if rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$r.log" 2>/dev/null; then
      note "$r 실패 — Traceback"; rs "tail -15 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$r.log"; continue 2
    fi
    sleep 180
  done
  sleep 60
  note "--- $r 프로브 (섹터 반사실) ---"
  rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2; \
      CUDA_VISIBLE_DEVICES=1 ./venv/bin/python code/course/probe_goto_language.py $C \
        data/course/packed_${TAG} --n 60 2>&1 | grep -E 'PRED|instructed side'"
done

note "=== END ==="
note "판정: 섹터 반사실이 27/42=64% 를 넘어야 우연과 유의하게 구별된다(n=42)."
note "      s0(상수 문장)이 노이즈 하한이다. b1/b0 기준선은 22/42 · 23/42 였다."

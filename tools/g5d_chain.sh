#!/bin/bash
# g5d 체인 (2026-10-12): 점 목표 원시 동작 학습. 사전 등록:
#   docs/experiments/goto_object/20261012_1850_point-goal-primitive-prereg.md
# 라벨·업로드 대기 → 코드 업로드 → 변환(state 6) → 학습(GPU0, stock base, bs8, 15k, ce 0, 상수 문장) → 통계 교정
#   setsid nohup bash tools/g5d_chain.sh > /dev/null 2>&1 &
#   tail -f eval_out/course/g5d_chain.log
WS=/home/sh/ROS2_project/sant-vla
SP=/tmp/claude-1000/-home-sh-ROS2-project-sant-vla/6e509714-993b-42d5-92b2-828386540bb6/scratchpad
LOG=$WS/eval_out/course/g5d_chain.log
SRV=autolab_sw@115.145.211.157
RUN=${RUN:-g5d}; OUT=${OUT:-g5d}; STEPS=${STEPS:-15000}; BS=${BS:-8}
exec >> "$LOG" 2>&1
rs() { ssh -o ConnectTimeout=25 -o BatchMode=yes "$SRV" "$@"; }
note() { echo "[g5d $(date '+%F %T')] $*"; }
D=$WS/src/sant_vla_pkg/data_course_multiobj

note "=== 시작 ==="
if [ "${SKIP_CONVERT:-0}" = 1 ]; then
  note "SKIP_CONVERT=1: 업로드·변환 생략 (data/course/lerobot/$OUT 존재 가정)"
  rs "test -f ~/sunhong/nav-vla/data/course/lerobot/$OUT/meta/info.json" || { note "데이터셋 없음"; exit 8; }
else
# ── 1. 라벨(gv2b·sec1) + sec/sec2 업로드 대기 ──────────────────────────
w=0
until grep -q LABEL_DONE "$SP/label_gv2b_sec1.log" 2>/dev/null; do
  grep -q Traceback "$SP/label_gv2b_sec1.log" 2>/dev/null && { note "라벨 실패"; tail -5 "$SP/label_gv2b_sec1.log"; exit 4; }
  [ $w -ge 7200 ] && { note "라벨 대기 초과"; exit 4; }; sleep 30; w=$((w+30))
done
note "라벨 완료: gv2b $(ls $D/packed_gv2b/*/reasoning.jsonl | wc -l)/68, sec1 $(ls $D/packed_sec1/*/reasoning.jsonl | wc -l)/35"
w=0
until grep -q RSYNC_sec2_DONE "$SP/rsync_sec.log" 2>/dev/null; do
  [ $w -ge 10800 ] && { note "sec/sec2 업로드 대기 초과"; exit 7; }; sleep 60; w=$((w+60))
done
note "sec/sec2 업로드 완료"

# ── 2. gv2b·sec1 업로드 + 파일 수 검증 ────────────────────────────────
for t in gv2b sec1; do
  rsync -a --info=stats2 "$D/packed_$t/" "$SRV:~/sunhong/nav-vla/data/course/packed_$t/" | tail -1 || { note "rsync $t 실패"; exit 7; }
done
for t in gv2b sec sec1 sec2; do
  LN=$(find "$D/packed_$t" -type f | wc -l); SN=$(rs "find ~/sunhong/nav-vla/data/course/packed_$t -type f | wc -l" | tr -d '\r')
  note "packed_$t 파일 수 로컬 $LN / 서버 $SN"
  [ "$SN" = "$LN" ] || { note "불일치 — 중단"; exit 7; }
done
FREE=$(rs "df -BG --output=avail ~ | tail -1 | tr -dc 0-9" | tr -d '\r')
note "서버 여유 ${FREE}G"; [ "${FREE:-0}" -ge 10 ] || { note "여유 부족"; exit 6; }

# ── 3. 코드 업로드 (패치된 to_lerobot + 변환 스크립트) ───────────────
scp -q "$WS/server/code/to_lerobot.py" "$SRV:~/sunhong/nav-vla/code/to_lerobot.py" || exit 8
scp -q "$WS/server/code/course/convert_g5d.sh" "$SRV:~/sunhong/nav-vla/code/course/convert_g5d.sh" || exit 8
LM=$(md5sum "$WS/server/code/to_lerobot.py" | cut -c1-12); SM=$(rs "md5sum ~/sunhong/nav-vla/code/to_lerobot.py" | cut -c1-12)
[ "$LM" = "$SM" ] || { note "to_lerobot md5 불일치"; exit 8; }

# ── 4. 변환 ──────────────────────────────────────────────────────────
note "변환 → data/course/lerobot/$OUT"
rs "cd ~/sunhong/nav-vla && OUT=$OUT bash code/course/convert_g5d.sh 2>&1 | tail -8" || { note "변환 실패"; exit 8; }
SD=$(rs "python3 -c \"import json; print(json.load(open('/home/autolab_sw/sunhong/nav-vla/data/course/lerobot/$OUT/meta/info.json'))['features']['observation.state']['shape'][0])\"" | tr -d '\r')
[ "$SD" = "6" ] || { note "state shape 가 6 이 아님 ($SD) — 중단"; exit 8; }
note "변환 OK (state 6)"
fi

# ── 5. 학습 (GPU0, stock base, r26 설정, ce 0, 상수 문장) ───────────
STOCK=$(rs 'ls -d ~/.cache/huggingface/hub/models--lerobot--smolvla_base/snapshots/*/ | head -1' | tr -d '\r')
R26=runs/navvla_reasoning_r26/checkpoints/last/pretrained_model
C=runs/course/navvla_reasoning_$RUN/checkpoints/$(printf '%06d' "$STEPS")/pretrained_model
if rs "test -f ~/sunhong/nav-vla/$C/model.safetensors"; then note "$RUN 이미 완료"; else
  w=0
  until [ "$(rs 'nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits -i 0' | tr -d ' \r')" -ge 9000 ]; do
    [ $w -ge 5400 ] && { note "GPU0 대기 초과"; exit 1; }; sleep 300; w=$((w+300))
  done
  note "--- $RUN 기동 (stock base, bs$BS, $STEPS step, ce 0, blank-task Target.) ---"
  rs "cd ~/sunhong/nav-vla && RUN=$RUN DATA=$OUT GPU=0 STEPS=$STEPS SAVE=$STEPS \
      BASE='$STOCK' BASE_CONFIG='$R26' EXTRA='--batch-size $BS --ce-weight 0 --blank-task Target.' \
      bash code/course/launch_goto.sh"
  sleep 150
  rs "grep -vE 'torch_dtype|^Loading  |Reducing' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log | head -8"
  until rs "test -f ~/sunhong/nav-vla/$C/model.safetensors"; do
    rs "grep -q Traceback ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log" && {
      note "$RUN 실패"; rs "tail -15 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log"; exit 1; }
    sleep 180
  done
  sleep 45
fi
note "--- $RUN 통계 교정 ---"
rs "cd ~/sunhong/nav-vla && ./venv/bin/python code/fix_postproc_stats.py $C 2>&1 | tail -2"
rs "grep '^step' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$RUN.log | tail -1"
note "=== END: $C ==="

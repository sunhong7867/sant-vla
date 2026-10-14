#!/bin/bash
# packed_div 수집 완료 대기 → 라벨 → 서버 → v41r 변환 → r41 학습 → 오프라인 문구 프로브 →
# 좌표 정답 문구 폐루프(인덱스 70·142 × 우리 차선/옆 차선 × curv_boost_slow 0.85/1.0) → 전원 프로필 복구.
#   bash tools/r41_chain.sh ; tail -f eval_out/course/r41_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r41_chain.log
if [ "${R41_CHILD:-0}" != 1 ]; then
  R41_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
SRV=autolab_sw@115.145.211.157
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
finish() { powerprofilesctl set balanced 2>/dev/null; echo "[chain] power profile -> $(powerprofilesctl get 2>/dev/null)"; echo "[chain] END $(date '+%F %T') $1"; exit "${2:-0}"; }

step "wait for collection"
until grep -qE "ALL_DONE|없음|RAM 중단" "$WS/eval_out/course/div_run_div.log" 2>/dev/null; do sleep 60; done
tail -3 "$WS/eval_out/course/div_run_div.log"
[ -f "$D/packed_div/index.jsonl" ] || finish "no packed_div" 2

step "labels"
HELD=""; [ -f "$D/packed_div_heldout/index.jsonl" ] && HELD="$D/packed_div_heldout"
python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D/packed_div" $HELD || finish "label fail" 3

step "ship"
rsync -a "$D/packed_div/" "$SRV":'~/sunhong/nav-vla/data/course/packed_div/' || finish "rsync fail" 4
[ -n "$HELD" ] && rsync -a "$D/packed_div_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_div_heldout/'
scp -q "$WS/server/code/train_reasoning.py" "$WS/server/code/vla_policy_server.py" "$SRV":'~/sunhong/nav-vla/code/' || finish "scp fail" 4
scp -q "$WS/server/code/reasoning_vla/"*.py "$SRV":'~/sunhong/nav-vla/code/reasoning_vla/'
scp -q "$WS/server/code/course/convert_v41r.sh" "$WS/server/code/course/launch_r41.sh" \
  "$WS/server/code/course/probe_situation.py" "$SRV":'~/sunhong/nav-vla/code/course/'

step "convert v41r"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v41r.sh 2>&1 | grep -v "Svt\|mp4 @\|Map:" | tail -6' || finish "convert fail" 5
ssh "$SRV" 'cd ~/sunhong/nav-vla && python3 - <<EOF
import json,collections,sys
sys.path.insert(0,"code")
from reasoning_vla.reasoning_dataset import situation_of
c=collections.Counter()
for l in open("data/course/lerobot/v41r/reasoning_labels.jsonl"):
    r=json.loads(l); c[situation_of(r["variants"][0])]+=r["f1"]-r["f0"]+1
print("situation frames:", dict(c))
EOF'

step "train r41 (GPU0)"
ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/launch_r41.sh" || finish "launch fail" 6
sleep 180
ssh "$SRV" "grep -E 'dataset:|situation prompt|Traceback|Error' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r41.log | head -4"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r41.log" 2>/dev/null; do sleep 120; done
ssh "$SRV" "grep -E 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r41.log | tail -2"
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r41.log" || finish "train fail" 7

step "offline situation probe (lane2 70 frames from packed_ramp70 — r41 never trained there)"
ssh "$SRV" "cd ~/sunhong/nav-vla && CUDA_VISIBLE_DEVICES=0 ./venv/bin/python code/course/probe_situation.py \
  runs/course/navvla_reasoning_r41/checkpoints/last/pretrained_model > logs/course/probe_situation_r41.txt 2>&1; \
  grep -E '^\[|==|m  n=|Traceback' logs/course/probe_situation_r41.txt"

step "closed loop, oracle phrase"
VL=$WS/eval_out/course/r40_variants.log
for spot in lane2:0.1725 lane1:0.1725 lane2:0.35 lane1:0.35; do
  tagx="_oracle_${spot/:/_}"
  RUN=r41 ORACLE=1 VARIANTS="base cbs10" MODELS=ob_box SPOT=$spot TAGX=$tagx \
    bash "$WS/tools/eval/r40_bridge_variants.sh"
  sleep 5
  until grep -q "ALL_DONE" "$VL" 2>/dev/null; do sleep 15; done
  grep -E "\[r40v\]|->|BRINGUP_FAIL" "$VL"
done
python3 "$WS/tools/eval/trace_view.py" "$WS"/eval_out/course/multiobj_eval/trials/r41_*oracle*_ob_box_*.log
finish "ok" 0

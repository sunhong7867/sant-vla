#!/bin/bash
# 다중 물체 회피 코퍼스 → 라벨 → 서버 전송 → v29r 변환 → r29 학습 개시.
# 전제: tools/collect_multiobj_avoid.sh (TAG=multi) 가 끝나 packed_multi / packed_multi_heldout 존재.
#   bash tools/multiobj_train_chain.sh            # 전체
#   SKIP_TRAIN=1 bash tools/multiobj_train_chain.sh   # 변환까지만
set -uo pipefail
SRV=autolab_sw@115.145.211.157
WS=/home/sh/ROS2_project/sant-vla
D=$WS/src/sant_vla_pkg/data_course_multiobj
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }

[ -f "$D/packed_multi/index.jsonl" ] || { echo "packed_multi 없음 — 수집 먼저"; exit 2; }
[ -f "$D/packed_multi_heldout/index.jsonl" ] || { echo "packed_multi_heldout 없음"; exit 2; }

step "reasoning labels (noun-aware)"
FIX=""; [ -f "$D/packed_multi_fix/index.jsonl" ] && FIX="$D/packed_multi_fix"
python3 $WS/src/sant_vla_pkg/scripts/label_reasoning.py "$D/packed_multi" "$D/packed_multi_heldout" $FIX || exit 3
python3 - "$D/packed_multi" <<'PY'
import glob, json, sys, collections
c = collections.Counter()
for f in glob.glob(sys.argv[1] + "/*/reasoning.jsonl"):
    for ln in open(f):
        r = json.loads(ln)
        if "_meta" in r: continue
        for n in ("car", "box", "cone", "barrier", "person", "barrel"):
            if f" {n}" in r.get("skeleton", ""): c[n] += 1
print("noun mentions (frames):", dict(c))
PY

step "ship packed_multi(+heldout) + code"
rsync -a --info=progress2 "$D/packed_multi/" "$SRV":'~/sunhong/nav-vla/data/course/packed_multi/' || exit 4
rsync -a --info=progress2 "$D/packed_multi_heldout/" "$SRV":'~/sunhong/nav-vla/data/course/packed_multi_heldout/' || exit 4
[ -n "$FIX" ] && { rsync -a --info=progress2 "$FIX/" "$SRV":'~/sunhong/nav-vla/data/course/packed_multi_fix/' || exit 4; }
scp -q $WS/server/code/train_reasoning.py \
  "$SRV":'~/sunhong/nav-vla/code/' || exit 4
scp -q $WS/server/code/course/convert_v29r.sh $WS/server/code/course/launch_r29.sh "$SRV":'~/sunhong/nav-vla/code/course/' || exit 4
ssh "$SRV" 'chmod +x ~/sunhong/nav-vla/code/convert_v29r.sh ~/sunhong/nav-vla/code/launch_r29.sh; df -h ~ | tail -1'

step "convert v29r (staging + to_lerobot + sidecar)"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v29r.sh 2>&1 | tail -15' || { echo CONVERT_FAIL; exit 5; }
ssh "$SRV" 'grep -c . ~/sunhong/nav-vla/data/course/lerobot/v29r/nav_vla_index.jsonl; grep -c . ~/sunhong/nav-vla/data/course/lerobot/v29r/reasoning_labels.jsonl'

[ "${SKIP_TRAIN:-0}" = 1 ] && { echo "변환까지 완료 (SKIP_TRAIN)"; exit 0; }

step "launch r29 (3090)"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/launch_r29.sh' || exit 6
sleep 240
ssh "$SRV" 'cd ~/sunhong/nav-vla; grep -E "MULTIOBJ|SIGNAL-STOP|resample-comp|obstacle boost|dataset:" logs/course/navvla_reasoning_r29.log | head; tail -c 400 logs/course/navvla_reasoning_r29.log | tr "\r" "\n" | tail -3; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader'
echo "[r29] 개시 $(date +%H:%M) — 약 2.6h 뒤 runs/course/navvla_reasoning_r29/checkpoints/025000"

step "정리 (로컬 캐시·로그 + 서버 스테이징/완료 런 중간 체크포인트)"
bash $WS/tools/cleanup_artifacts.sh --server | tail -6

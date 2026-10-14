#!/bin/bash
# boxpair2 수집 → 라벨·전송(boxpair, boxpair2) → v45r 변환 → r45 학습(GPU1) → 무작위 20 곳 × 우리 차선/옆 차선/빈 차선 (2026-10-02)
#   bash tools/r45_chain.sh ; tail -f eval_out/course/r45_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/r45_chain.log
if [ "${R45_CHILD:-0}" != 1 ]; then
  R45_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
step "collect boxpair2 (재부팅으로 중단된 boxpair 의 나머지)"
# boxpair 는 13:20 재부팅 전 84 ep 에서 중단 → 부분 세션을 finalize(83 통과, 42 짝) 해 packed_boxpair.
D=$WS/src/sant_vla_pkg/data_course_multiobj
if [ ! -f "$D/packed_boxpair2/index.jsonl" ]; then
  pgrep -af 'gz si[m]|episode_recorde[r]|avoidance_tria[l]' && { echo "[r45] stack running"; exit 1; }
  powerprofilesctl set performance; echo "[r45] power -> $(powerprofilesctl get)"
  TAG=boxpair2 TRAIN_MODELS=ob_box HELDOUT_MODELS=ob_person TRAIN_GROUPS=${NGROUPS:-78} HELDOUT_GROUPS=0 \
    OB_VARIANTS=v1,v2 SEED_TRAIN=20261051 POSE_SOURCE=cli bash "$WS/tools/div_run.sh"
  sleep 5
  until grep -qE "ALL_DONE|없음|RAM 중단|이미 있음" "$WS/eval_out/course/div_run_boxpair2.log" 2>/dev/null; do sleep 60; done
  tail -4 "$WS/eval_out/course/div_run_boxpair2.log"
  powerprofilesctl set balanced; echo "[r45] power -> $(powerprofilesctl get)"
fi
for p in packed_boxpair packed_boxpair2; do
  [ -f "$D/$p/index.jsonl" ] || { echo "[r45] $p 없음"; continue; }
  python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D/$p" || exit 1
  rsync -a "$D/$p/" "$SRV":"~/sunhong/nav-vla/data/course/$p/" || exit 1
  echo "[r45] shipped $p"
done

step "ship code + convert v45r"
scp -q "$WS/server/code/train_reasoning.py" "$SRV":'~/sunhong/nav-vla/code/' || exit 2
scp -q "$WS/server/code/course/convert_v45r.sh" "$WS/server/code/course/launch_r45.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
ssh "$SRV" 'df -h ~ | tail -1; cd ~/sunhong/nav-vla && bash code/course/convert_v45r.sh 2>&1 | grep -E "stanley|packed_|segment rows|CONVERT|Error|Traceback" | tail -8' || exit 3

step "train r45 (GPU1)"
ssh -n "$SRV" "cd ~/sunhong/nav-vla && GPU=1 bash code/course/launch_r45.sh" || exit 4
sleep 240
ssh "$SRV" "grep -E 'dataset:|twin|sampled share|obstacle boost|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r45.log | head -6"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r45.log" 2>/dev/null; do sleep 120; done
ssh "$SRV" "grep -E 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r45.log | tail -1"
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r45.log" || { echo "[r45] train fail"; exit 5; }

step "stat eval r45 (20 positions)"
RUN=r45 NPOS=20 BATCH=20 bash "$WS/tools/eval/stat_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r45.log" 2>/dev/null; do sleep 30; done
sed -n '/collected/,$p' "$WS/eval_out/course/stat_r45.log"
echo "[r45] END $(date '+%F %T')"

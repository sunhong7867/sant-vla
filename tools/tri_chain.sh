#!/bin/bash
# 박스 묶음 시연(v0/v1/v2) → r43 → 무작위 100 곳 대량 평가 (2026-10-01).
#   영상 녹화 끝 대기 → 서버 sw5~sw80 체크포인트 삭제(사용자 승인) → 수집(performance, 끝나면 balanced)
#   → 라벨 → 서버 → v43r 변환 → r43 학습(GPU1) → stat_eval (우리 차선/옆 차선/빈 차선 × 100 곳)
#   bash tools/tri_chain.sh ; tail -f eval_out/course/tri_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/tri_chain.log
if [ "${TRI_CHILD:-0}" != 1 ]; then
  TRI_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
SRV=autolab_sw@115.145.211.157
D=$WS/src/sant_vla_pkg/data_course_multiobj
NGROUPS=${NGROUPS:-120}   # (GROUPS 는 bash 예약 변수)
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
balanced() { powerprofilesctl set balanced 2>/dev/null; echo "[tri] power profile -> $(powerprofilesctl get 2>/dev/null)"; }
die() { balanced; echo "[tri] END $(date '+%F %T') FAIL $1"; exit "${2:-1}"; }

step "wait for clip recording"
until grep -q "ALL_DONE" "$WS/eval_out/course/clips/record.log" 2>/dev/null; do sleep 30; done
grep -E '^\[clip\].*mp4|BRINGUP' "$WS/eval_out/course/clips/record.log"

step "server: remove sweep checkpoints sw5..sw80 (사용자 승인 2026-10-01)"
ssh "$SRV" 'cd ~/sunhong/nav-vla/runs/course && for n in 5 10 20 40 80; do [ -d navvla_reasoning_sw$n ] && rm -rf navvla_reasoning_sw$n && echo "removed sw$n"; done; df -h ~ | tail -1'

step "preflight"
pgrep -af 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]|avoidance_tria[l]' && die "stack running" 2
AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo); echo "RAM avail ${AV}G"
awk -v a="$AV" 'BEGIN{exit !(a<4)}' && die "RAM ${AV}G < 4G" 2
powerprofilesctl set performance; echo "[tri] power profile -> $(powerprofilesctl get)"

step "collect boxtri ($NGROUPS groups x v0/v1/v2)"
TAG=boxtri TRAIN_MODELS=ob_box HELDOUT_MODELS=ob_person TRAIN_GROUPS=$NGROUPS HELDOUT_GROUPS=0 \
  OB_VARIANTS=v0,v1,v2 SEED_TRAIN=20261030 bash "$WS/tools/div_run.sh"
sleep 5
until grep -qE "ALL_DONE|없음|RAM 중단|이미 있음" "$WS/eval_out/course/div_run_boxtri.log" 2>/dev/null; do sleep 60; done
tail -4 "$WS/eval_out/course/div_run_boxtri.log"
balanced
[ -f "$D/packed_boxtri/index.jsonl" ] || die "no packed_boxtri" 3

step "labels + ship"
python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$D/packed_boxtri" || die "label fail" 3
FREE=$(ssh "$SRV" "df -BG --output=avail ~ | tail -1 | tr -dc 0-9"); echo "[tri] server free ${FREE}G"
[ "${FREE:-0}" -ge 3 ] || die "server disk ${FREE}G < 3G" 4
rsync -a "$D/packed_boxtri/" "$SRV":'~/sunhong/nav-vla/data/course/packed_boxtri/' || die "rsync fail" 4
scp -q "$WS/server/code/course/convert_v43r.sh" "$WS/server/code/course/launch_r43.sh" \
  "$SRV":'~/sunhong/nav-vla/code/course/' || die "scp fail" 4

step "convert v43r"
ssh "$SRV" 'cd ~/sunhong/nav-vla && bash code/course/convert_v43r.sh 2>&1 | grep -v "Svt\|mp4 @\|Map:\|video_backend\|LeRobotDataset" | tail -8' || die "convert fail" 5

step "train r43 (GPU1)"
ssh -n "$SRV" "cd ~/sunhong/nav-vla && GPU=1 bash code/course/launch_r43.sh" || die "launch fail" 6
sleep 240
ssh "$SRV" "grep -E 'dataset:|twin|obstacle boost|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r43.log | head -5"
until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r43.log" 2>/dev/null; do sleep 120; done
ssh "$SRV" "grep -E 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r43.log | tail -1"
ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_r43.log" || die "train fail" 7

step "stat eval r43 (100 positions x ours/adj/empty)"
RUN=r43 NPOS=100 bash "$WS/tools/eval/stat_eval.sh"
sleep 10
until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_r43.log" 2>/dev/null; do sleep 60; done
sed -n '/collected/,$p' "$WS/eval_out/course/stat_r43.log"
echo "[tri] END $(date '+%F %T') ok"

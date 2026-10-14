#!/bin/bash
# 다장애물 120 바퀴 스윕 (2026-10-03): 수집 끝 → (서버 복구 대기) 전송 → m40/m80/m120 변환 → 학습 → 같은 20 곳 평가.
#   r48c = 120 바퀴(GPU1), r48b = 80(GPU0) 동시 → r48a = 40(GPU1). 평가 순서 r48c → r48b → r48a
#   (평가 정책 서버가 GPU0 을 쓰므로 평가 중 학습은 GPU1 만).
#   조건: ours adj empty (2차선 출발) + ours1 empty1 (1차선 출발, 오른쪽 회피) = 20 곳 × 5, 모델당 약 1 h 40 m
#   bash tools/mrun_sweep_chain.sh ; tail -f eval_out/course/mrun_sweep_chain.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/mrun_sweep_chain.log
if [ "${SW_CHILD:-0}" != 1 ]; then
  SW_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
SRV=autolab_sw@115.145.211.157
P=$WS/src/sant_vla_pkg/data_course_multiobj/packed_mrun
CONDS=${CONDS:-"ours adj empty ours1 empty1"}
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
rs() { ssh -o ConnectTimeout=15 "$SRV" "$@"; }
trained() { rs "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log" 2>/dev/null; }
wait_train() {
  until rs "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log" 2>/dev/null; do sleep 120; done
  trained "$1" || { echo "[sw] $1 train fail"; rs "tail -5 ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log"; return 1; }
  rs "grep -E 'dataset:|sampled share|obstacle boost|done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_$1.log"
}
stat_run() {
  until ! pgrep -af 'gz si[m]|avoidance_tria[l]|episode_recorde[r]' >/dev/null; do sleep 60; done
  RUN=$1 NPOS=20 BATCH=20 CONDS="$CONDS" bash "$WS/tools/eval/stat_eval.sh"
  sleep 10
  until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/stat_$1.log" 2>/dev/null; do sleep 60; done
  sed -n '/collected/,$p' "$WS/eval_out/course/stat_$1.log"
}

step "wait collection"
until grep -qE '^\[mc\] (END|no packed|ship mismatch|stack running)' "$WS/eval_out/course/multi_chain_mrun.log" 2>/dev/null \
      || ! pgrep -f 'multi_chai[n].sh' >/dev/null; do sleep 60; done
tail -6 "$WS/eval_out/course/multi_chain_mrun.log"
[ -f "$P/index.jsonl" ] || { echo "[sw] packed_mrun 없음"; exit 1; }
find "$P" -name reasoning.jsonl | grep -q . || python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$P" | tail -1

step "wait server + ship"
until rs true 2>/dev/null; do echo "[sw] $(date +%T) 서버 접속 불가 — 5 분 뒤 재시도"; sleep 300; done
rsync -a "$P/" "$SRV":'~/sunhong/nav-vla/data/course/packed_mrun/' || exit 2
NL=$(find "$P" -name reasoning.jsonl | wc -l); NR=$(rs "find ~/sunhong/nav-vla/data/course/packed_mrun -name reasoning.jsonl | wc -l")
echo "[sw] shipped local $NL server $NR"; [ "$NL" = "$NR" ] || exit 2
scp -q "$WS/server/code/course/convert_mrun.sh" "$WS/server/code/course/launch_mrun.sh" "$SRV":'~/sunhong/nav-vla/code/course/' || exit 2
rs "df -h ~ | tail -1"

step "convert m120 m80 m40"
for n in 120 80 40; do
  rs "cd ~/sunhong/nav-vla && N=$n OUT=m$n bash code/course/convert_mrun.sh 2>&1 | grep -E 'stanley|groups|segment rows|CONVERT|Error|Traceback' | tail -4" || exit 3
done

step "train r48c (m120, GPU1) + r48b (m80, GPU0)"
rs -n "cd ~/sunhong/nav-vla && RUN=r48c DATA=m120 GPU=1 bash code/course/launch_mrun.sh" || exit 4
rs -n "cd ~/sunhong/nav-vla && RUN=r48b DATA=m80 GPU=0 bash code/course/launch_mrun.sh" || exit 4
wait_train r48c || exit 5
rs -n "cd ~/sunhong/nav-vla && RUN=r48a DATA=m40 GPU=1 bash code/course/launch_mrun.sh" || exit 4

# r48b 가 GPU0 을 쓰는 동안엔 평가 정책 서버(GPU0)를 띄우지 않는다
B_OK=1; wait_train r48b || B_OK=0
step "stat r48c (120 laps)"
stat_run r48c
[ "$B_OK" = 1 ] && { step "stat r48b (80 laps)"; stat_run r48b; }
wait_train r48a && { step "stat r48a (40 laps)"; stat_run r48a; }
rs "df -h ~ | tail -1"
echo "[sw] END $(date '+%F %T')"

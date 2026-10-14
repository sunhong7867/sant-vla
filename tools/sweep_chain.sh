#!/bin/bash
# 박스 회피 시연 수 스윕 (2026-10-01). 상황 문구 없이(모델 스스로 인지) 박스 v1 시연 5/10/20/40/80 개.
#   수집(박스, v1 만, 위치 무작위, performance 프로필) → 80 개 미달이면 보충 배치 → balanced 복구
#   → 라벨 → 서버 → sw5..sw80 변환 → 학습(sw80 GPU0 + sw40 GPU1, 이후 sw20→sw10→sw5 GPU1 줄)
#   → 각 모델 끝나는 대로 self_perception_eval (서빙 GPU0) → 표.
#   bash tools/sweep_chain.sh ; tail -f eval_out/course/sweep_chain.log
# 단계 건너뛰기: SKIP_COLLECT=1 (packed_boxv1* 가 이미 있을 때), ATTACH=boxv1 (그 수집이 이미 도는 중)
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/sweep_chain.log
if [ "${SW_CHILD:-0}" != 1 ]; then
  SW_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi
SRV=autolab_sw@115.145.211.157
D=$WS/src/sant_vla_pkg/data_course_multiobj
NS="80 40 20 10 5"
step() { echo; echo "======== [$(date +%T)] $1 ========"; }
balanced() { powerprofilesctl set balanced 2>/dev/null; echo "[sweep] power profile -> $(powerprofilesctl get 2>/dev/null)"; }
die() { balanced; echo "[sweep] END $(date '+%F %T') FAIL $1"; exit "${2:-1}"; }
count_v1() {  # 통과한 박스 v1 수 (packed_boxv1, 보충 packed_boxv1b; _heldout 제외)
  cat "$D"/packed_boxv1/index.jsonl "$D"/packed_boxv1b/index.jsonl 2>/dev/null | grep -c '"cf_variant_id": "v1"'
}
collect() {  # $1=TAG $2=groups $3=seed
  step "collect $1 ($2 groups, seed $3)"
  # ATTACH=<tag>: 이미 돌고 있는 그 수집에 붙기만 한다 (체인 재기동용)
  [ "${ATTACH:-}" = "$1" ] || TAG=$1 TRAIN_MODELS=ob_box HELDOUT_MODELS=ob_person TRAIN_GROUPS=$2 HELDOUT_GROUPS=0 \
    V1_ONLY=1 SEED_TRAIN=$3 bash "$WS/tools/div_run.sh"
  sleep 5
  until grep -qE "ALL_DONE|없음|RAM 중단|이미 있음" "$WS/eval_out/course/div_run_$1.log" 2>/dev/null; do sleep 60; done
  tail -4 "$WS/eval_out/course/div_run_$1.log"
  echo "[sweep] box v1 so far: $(count_v1)"
}

if [ "${SKIP_COLLECT:-0}" != 1 ]; then
  step "preflight"
  [ -n "${ATTACH:-}" ] || { pgrep -af 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]|avoidance_tria[l]' && die "stack running" 2; }
  AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo); echo "RAM avail ${AV}G"
  awk -v a="$AV" 'BEGIN{exit !(a<4)}' && die "RAM ${AV}G < 4G" 2
  powerprofilesctl set performance; echo "[sweep] power profile -> $(powerprofilesctl get)"
  collect boxv1 260 20261020
  HAVE=$(count_v1)
  if [ "$HAVE" -lt 80 ]; then
    # 첫 배치 통과율로 보충량 계산 (+30 % 여유, 최대 260)
    RATE=$(awk -v h="$HAVE" 'BEGIN{r=h/260; if (r<0.15) r=0.15; print r}')
    MORE=$(awk -v h="$HAVE" -v r="$RATE" 'BEGIN{m=int((80-h)/r*1.3)+1; if (m>260) m=260; print m}')
    collect boxv1b "$MORE" 20261021
  fi
  balanced
fi
HAVE=$(count_v1)
echo "[sweep] box v1 total: $HAVE"
[ "$HAVE" -ge 80 ] || { NS=$(for n in 80 40 20 10 5; do [ "$n" -le "$HAVE" ] && echo -n "$n "; done); echo "[sweep] 80 미달 — N = $NS"; }
[ -n "$NS" ] || die "no box v1" 3

step "server disk"
# 학습 1 개 = 체크포인트 1.1 G (save-freq 8000), 5 개 + 코퍼스 ≈ 8 G. 모자라면 비워질 때까지 대기.
while :; do
  FREE=$(ssh "$SRV" "df -BG --output=avail ~ | tail -1 | tr -dc 0-9")
  [ -n "$FREE" ] && [ "$FREE" -ge "${NEED_G:-8}" ] && break
  echo "[sweep] $(date +%T) 서버 디스크 ${FREE}G < ${NEED_G:-8}G — 대기"; sleep 300
done
echo "[sweep] server free ${FREE}G"

step "labels + ship"
for p in "$D"/packed_boxv1 "$D"/packed_boxv1b; do
  [ -f "$p/index.jsonl" ] || continue
  python3 "$WS/src/sant_vla_pkg/scripts/label_reasoning.py" "$p" || die "label fail $p" 3
  rsync -a "$p/" "$SRV":"~/sunhong/nav-vla/data/course/$(basename "$p")/" || die "rsync fail" 4
done
scp -q "$WS/server/code/course/convert_sweep.sh" "$WS/server/code/course/launch_sweep.sh" \
  "$SRV":'~/sunhong/nav-vla/code/course/' || die "scp fail" 4

step "convert"
for n in $NS; do
  ssh "$SRV" "cd ~/sunhong/nav-vla && bash code/course/convert_sweep.sh $n 2>&1 | grep -v 'Svt\|mp4 @\|Map:' | tail -5" || die "convert sw$n" 5
done

step "train"
FIRST=$(echo $NS | awk '{print $1}'); SECOND=$(echo $NS | awk '{print $2}')
REST=$(echo $NS | cut -d' ' -f3-)
ssh "$SRV" "cd ~/sunhong/nav-vla && GPU=0 bash code/course/launch_sweep.sh $FIRST" || die "launch $FIRST" 6
if [ -n "$SECOND" ]; then
  # GPU1 줄: SECOND 다음 REST 를 순서대로 (서빙이 GPU0 을 쓰므로 GPU0 은 첫 모델만).
  # ssh -f: 없으면 원격 백그라운드가 세션을 붙잡아 체인이 여기서 멈춘다 (2026-10-01 18:33~18:42)
  ssh -f -n "$SRV" "cd ~/sunhong/nav-vla && setsid nohup bash -c 'for n in $SECOND $REST; do GPU=1 bash code/course/launch_sweep.sh \$n; sleep 60; until grep -qE \"done in|Traceback\" logs/course/navvla_reasoning_sw\$n.log; do sleep 60; done; done' > logs/course/sweep_queue.log 2>&1 < /dev/null &"
fi
sleep 240
ssh "$SRV" "grep -hE 'dataset:|box|twin|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_sw*.log | head -8"

step "eval (as models finish)"
for n in $NS; do
  until ssh "$SRV" "grep -qE 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_sw$n.log" 2>/dev/null; do sleep 120; done
  ssh "$SRV" "grep -E 'done in|Traceback' ~/sunhong/nav-vla/logs/course/navvla_reasoning_sw$n.log | tail -1"
  ssh "$SRV" "grep -q 'done in' ~/sunhong/nav-vla/logs/course/navvla_reasoning_sw$n.log" || { echo "[sweep] sw$n train fail — skip"; continue; }
  # sw80 평가 중 GPU0 이 학습과 겹치지 않게: 첫 모델은 GPU0 학습이 끝난 뒤에야 여기 온다
  RUN=sw$n SIT=0 bash "$WS/tools/eval/self_perception_eval.sh"
  sleep 10
  until grep -qE 'ALL_DONE [0-9]' "$WS/eval_out/course/self_sw$n.log" 2>/dev/null; do sleep 30; done
  echo "== sw$n"; grep -E '^== |->' "$WS/eval_out/course/self_sw$n.log" | grep -v '\.log'
done

step "summary"
python3 - "$WS" $NS <<'PY'
import re, sys
ws, ns = sys.argv[1], sys.argv[2:]
print("N    avoid(우리 차선 4+사람 4)  keep(옆 차선 4)")
for n in ns:
    try:
        txt = open(f"{ws}/eval_out/course/self_sw{n}.log").read()
    except OSError:
        continue
    cells = re.split(r"^== ", txt, flags=re.M)
    av = tot_av = kp = tot_kp = 0
    for c in cells:
        head = c.split("\n", 1)[0]
        if "@" not in head or ".log" in head:
            continue
        res = re.findall(r"-> (\w+)", c)
        if "lane1" in head:
            tot_kp += len(res); kp += res.count("SUCCESS")
        else:
            tot_av += len(res); av += res.count("SUCCESS")
    print(f"sw{n:<3} {av}/{tot_av}                     {kp}/{tot_kp}")
PY
echo "[sweep] END $(date '+%F %T') ok"

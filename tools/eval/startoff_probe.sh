#!/bin/bash
# 출발 거리 실험 (2026-10-02) — 빈 차선에서 꺾는 습관이 "트랙 위 자리" 를 따라가는지 "출발 후 거리" 를 따라가는지.
# 같은 기준점(가상 장애물 none, 스폰 없음)에 대해 출발만 OFFS(lane frac, 0.155 ≈ 22 m)로 바꿔 1 회씩.
#   자리 습관이면: 출발이 달라도 기준점 기준 같은 곳에서 꺾는다.
#   거리 습관이면: 출발 후 같은 거리에서 꺾는다(기준점 기준 꺾는 곳이 출발과 함께 움직인다).
# r45 체인과 겹치지 않게: 체인이 "train r45" 단계에 들어간 뒤(노트북 유휴) 시작하고, stat_r45 가 시작됐으면 시작하지 않는다.
# gz GUI 클라이언트를 같은 파티션에 붙여 사용자가 볼 수 있게 한다(정책 스택은 --no-gui = 회피 감독 없음).
#   RUN=r44 bash tools/eval/startoff_probe.sh ; tail -f eval_out/course/startoff_r44.log
#   분석: python3 tools/eval/startoff_analyze.py r44
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
RUN=${RUN:-r44}
LOG=$WS/eval_out/course/startoff_${RUN}.log
if [ "${SO_CHILD:-0}" != 1 ]; then
  SO_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-89}
export GZ_PARTITION=${ISO_PARTITION:-startoff}
export NAVVLA_SITUATION=0 CURV_BOOST_SLOW=1.0 TRACE_FRAC=1
ANCHORS=${ANCHORS:-"0.8886 0.5737"}      # r44 빈 차선에서 2.14 m / 1.53 m 꺾은 자리
OFFS=${OFFS:-"0.07 0.155 0.30 0.45"}     # ≈ 10 / 22 / 42 / 63 m 상류
OUT=$WS/eval_out/course/startoff/$RUN
mkdir -p "$OUT"
CHAIN=$WS/eval_out/course/r45_chain.log
echo "[so] $(date '+%F %T') RUN=$RUN domain=$ROS_DOMAIN_ID partition=$GZ_PARTITION anchors=$ANCHORS offs=$OFFS"

if [ "${NO_WAIT:-0}" != 1 ]; then
  echo "[so] r45 체인이 학습 단계에 들어갈 때까지 대기"
  until grep -q 'train r45' "$CHAIN" 2>/dev/null; do sleep 60; done
  sleep 30
fi
[ -e "$WS/eval_out/course/stat_r45.log" ] && { echo "[so] stat_r45 이미 시작 — 겹치므로 중단"; exit 1; }
if pgrep -f 'gz si[m]|episode_recorde[r]' > /dev/null; then echo "[so] 다른 시뮬/수집이 아직 떠 있음 — 중단"; exit 1; fi
AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
awk -v a="$AV" 'BEGIN{exit !(a>=6.0)}' || { echo "[so] 가용 RAM ${AV}G < 6G — 중단"; exit 1; }
echo "[so] $(date +%T) 가용 RAM ${AV}G — 기동"

source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash
REMOTE_CKPT=runs/course/navvla_reasoning_${RUN}/checkpoints/last/pretrained_model NAVVLA_RACE=qualifying \
  "$WS/smolvla_demo.sh" --no-gui > "$OUT/bringup.log" 2>&1 || { tail -20 "$OUT/bringup.log"; echo "[so] BRINGUP_FAIL"; exit 3; }
grep -q "REMOTE_SERVING" "$WS/eval_out/demo/remote_start.log" || { echo "[so] 원격 서빙 미확인"; "$WS/smolvla_demo.sh" down > /dev/null 2>&1; exit 3; }
echo "[so] $(date +%T) START — gz GUI 띄움 (partition $GZ_PARTITION)"
__NV_PRIME_RENDER_OFFLOAD=1 __GLX_VENDOR_LIBRARY_NAME=nvidia setsid nohup gz sim -g > "$OUT/gui.log" 2>&1 < /dev/null &
sleep 15
gz service -s /gui/follow --reqtype gz.msgs.StringMsg --reptype gz.msgs.Boolean --timeout 3000 \
  --req 'data: "ego_vehicle"' > /dev/null 2>&1 || true

# r45 평가가 먼저 시작되면 그쪽 smolvla_demo 가 이 스택을 내린다 — 그때는 우리 down 으로 그쪽을 죽이지 않게 바로 빠진다.
chain_eval_started() { [ -e "$WS/eval_out/course/stat_r45.log" ]; }
for a in $ANCHORS; do
  for o in $OFFS; do
    chain_eval_started && { echo "[so] stat_r45 시작됨 — 스택 정리 없이 중단"; exit 4; }
    sf=$(python3 -c "print(round(float('$a') - float('$o'), 4))")
    tag="a${a}_o${o}"
    echo "[so] $(date +%T) 기준점 $a, 출발 $sf (상류 frac $o)"
    python3 "$WS/tools/eval/avoidance_trial.py" --models none --obstacles "lane2:$a" \
      --start-frac "$sf" --speed slowly --no-supervisor --timeout 150 > "$OUT/$tag.log" 2>&1
    grep -E '"result"|lat_at_min' "$OUT/$tag.log" | tr -d ' \n'; echo
    sleep 3
  done
done

# 출발선(예선 스폰, lane2 frac 0.7931)에서 한 바퀴 — 기준점 3 곳(0.8886 / 0.1713 / 0.5737, 출발 후 약 14 / 56 / 116 m)을
# 달리는 중에 지날 때도 꺾는지. 가상 기준점 0.70(출발 후 134 m, 출발선과 직선 13.8 m, 도중 최근접 11.5 m > PASS_RADIUS 8)
# 을 지나면 끝. TRACE 마지막 칸 = 트랙 frac.
for k in $(seq 1 "${LAP_N:-2}"); do
  chain_eval_started && { echo "[so] stat_r45 시작됨 — 스택 정리 없이 중단"; exit 4; }
  echo "[so] $(date +%T) 출발선 한 바퀴 #$k"
  python3 "$WS/tools/eval/avoidance_trial.py" --models none --obstacles "lane2:0.70" \
    --start-frac 0.7931 --speed slowly --no-supervisor --timeout 300 > "$OUT/lap_$k.log" 2>&1
  grep -E '"result"' "$OUT/lap_$k.log" | tr -d ' \n'; echo
  sleep 3
done

echo "[so] $(date +%T) 스택 종료"
chain_eval_started && { echo "[so] stat_r45 시작됨 — 스택 정리 생략"; exit 4; }
"$WS/smolvla_demo.sh" down > /dev/null 2>&1
rm -rf ~/.gz/sim/log
python3 "$WS/tools/eval/startoff_analyze.py" "$RUN"
echo "[so] DONE $(date +%T)"

#!/usr/bin/env bash
# 2026-10-10: 조합 일반화 ①층 폐루프 검증.
#   오프라인 결과: c0 0.89 / c1 0.81 / cn 0.34 (짝 70, c1-cn CI [+0.376,+0.595])
#   docs/experiments/reports/20261010_0212_composition-generalization-holdout-result.md
#
# 홀드아웃 칸 = ring_goal x lane2 x fast. c1 은 그 칸을 한 번도 보지 않았다.
# 각 짝: 같은 start_pose 로 리셋 -> lane1 문장 주행 -> 같은 자리 리셋 -> lane2 문장 주행.
# probe_policy_counterfactual.py 가 SAME 짝(바닥)까지 같이 돌려 D_shape 바닥을 짝마다 준다.
#
#   RUNS="c1 cn" NG=12 bash tools/comp_closedloop.sh ; tail -f eval_out/course/comp_cl.log
#   분석: python3 tools/comp_cl_analyze.py
set -u
WS=/home/sh/ROS2_project/sant-vla
L=$WS/eval_out/course/comp_cl.log
if [ "${CC_CHILD:-0}" != 1 ]; then
  CC_CHILD=1 setsid nohup bash "$0" "$@" > "$L" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $L"; exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-compcl}
export KEEP_TRIALS=100000
set +u; source /opt/ros/jazzy/setup.bash; source $WS/install/setup.bash; set -u   # ROS setup 은 미정의 변수를 건드린다
RUNS=${RUNS:-"c1 cn"}; NG=${NG:-12}; STEP=${STEP:-015000}
DUR=${DUR:-30}; SEED=${SEED:-20261010}
OUT=$WS/eval_out/course/comp_cl; mkdir -p "$OUT"
note() { echo "[ccl $(date '+%F %T')] $*"; }

note "=== START runs='$RUNS' NG=$NG step=$STEP dur=${DUR}s ==="

# 기동 전 확인: 이미 떠 있는 스택이 있으면 중복 기동 금지 (check-before-sim-launch)
# 괄호 패턴이라 이 스크립트의 자기 명령줄은 매칭되지 않는다 (pkill-self-match-trap)
n=$(pgrep -fc 'gz[ ]sim' || true)
[ "${n:-0}" -gt 0 ] && { note "이미 gz sim $n 개 — 중복 기동 금지. 정리 후 다시 실행"; pgrep -af 'gz[ ]sim'; exit 2; }

# 짝 선택: 시드 고정이라 두 체크포인트가 같은 짝·같은 자리를 받는다
python3 - "$SEED" "$NG" <<'PY' > "$OUT/selected.json"
import json, random, sys
seed, ng = int(sys.argv[1]), int(sys.argv[2])
d = json.load(open("/home/sh/ROS2_project/sant-vla/eval_out/course/comp_cl/pairs.json"))
d.sort(key=lambda r: r["group"])
random.Random(seed).shuffle(d)
json.dump(d[:ng], open("/dev/stdout", "w"), ensure_ascii=False, indent=1)
PY
note "짝 $(python3 -c "import json;print(len(json.load(open('$OUT/selected.json'))))") 개 선택"

ram_ok() { awk '/MemAvailable/{exit !($2/1048576 >= 5.2)}' /proc/meminfo; }
t_end=$(( $(date +%s) + ${RAM_WAIT_H:-6} * 3600 ))
until ram_ok; do
  [ "$(date +%s)" -gt "$t_end" ] && { note "RAM_WAIT_TIMEOUT"; exit 3; }
  note "가용 RAM $(awk '/MemAvailable/{printf "%.1f", $2/1048576}' /proc/meminfo)G < 5.2G — 5 분 대기"
  sleep 300
done

for R in $RUNS; do
  C=runs/course/navvla_reasoning_${R}/checkpoints/${STEP}/pretrained_model
  note "--- $R 기동 (원격 서빙 $C) ---"
  POLICY_GUIDE=${POLICY_GUIDE:-1.0} REMOTE_CKPT=$C NAVVLA_RACE=qualifying \
    "$WS/smolvla_demo.sh" --no-gui > "$OUT/${R}_bringup.log" 2>&1 \
    || { tail -20 "$OUT/${R}_bringup.log"; note "$R BRINGUP_FAIL"; exit 3; }
  grep -q "REMOTE_SERVING" "$WS/eval_out/demo/remote_start.log" \
    || { note "$R 원격 서빙 미확인 — 중단"; "$WS/smolvla_demo.sh" down >/dev/null 2>&1; exit 3; }
  grep -E "max_speed|refill_at" "$OUT/${R}_bringup.log" | head -2
  sleep 5

  i=0
  while read -r g; do
    i=$((i+1))
    GID=$(echo "$g" | python3 -c 'import json,sys;print(json.load(sys.stdin)["group"])')
    X=$(echo "$g"  | python3 -c 'import json,sys;print("%.4f"%json.load(sys.stdin)["pose"][0])')
    Y=$(echo "$g"  | python3 -c 'import json,sys;print("%.4f"%json.load(sys.stdin)["pose"][1])')
    YAW=$(echo "$g"| python3 -c 'import json,sys;print("%.4f"%json.load(sys.stdin)["pose"][2])')
    SA=$(echo "$g" | python3 -c 'import json,sys;print(json.load(sys.stdin)["lane1"])')
    SB=$(echo "$g" | python3 -c 'import json,sys;print(json.load(sys.stdin)["lane2"])')
    note "[$R $i] $GID  ($X, $Y, $YAW)"
    note "      A(lane1,분포내): $SA"
    note "      B(lane2,홀드아웃): $SB"
    python3 "$WS/src/sant_vla_pkg/scripts/probe_policy_counterfactual.py" \
      --x "$X" --y "$Y" --yaw "$YAW" --duration "$DUR" --repeats 1 \
      --case-label "DIFFERENT lane (holdout cell)" \
      --run-id "${R}_${GID}" --start-label "$GID" \
      --say-a "$SA" --say-b "$SB" \
      --out "$OUT/${R}_${GID}.json" 2>&1 | grep -E "D_shape|ended|watchdog|too few"
  done < <(python3 -c "
import json
for r in json.load(open('$OUT/selected.json')): print(json.dumps(r, ensure_ascii=False))")

  note "--- $R 정리 ---"
  "$WS/smolvla_demo.sh" down > "$OUT/${R}_down.log" 2>&1
  sleep 20
done

note "=== END ==="
python3 "$WS/tools/comp_cl_analyze.py" 2>&1 || note "분석 실패"

#!/bin/bash
# lane2 70 회피 코퍼스 재수집 → r38/r39 학습 체인을 한 번에, 터미널을 닫아도 살아남게 실행.
#   bash tools/ramp70_run.sh            # 백그라운드로 떠나고 로그 경로만 출력
#   tail -f eval_out/course/ramp70_run.log
#
# 2026-09-29 첫 수집은 다른 세션의 캡처가 같은 gz 에 obstacle1 을 놓아 전량 폐기
# (packed_ramp70_contaminated). 그래서:
#   - ROS_DOMAIN_ID / GZ_PARTITION 을 분리해 다른 도구가 이 시뮬에 붙지 못하게 한다
#   - gz 창 없이(GZ_GUI=false) 돌려 RAM 을 아낀다
#   - 가용 RAM 이 RAM_FLOOR_G 밑으로 내려가면 수집을 멈춘다(프리즈 대신 중단)
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
LOG=$WS/eval_out/course/ramp70_run.log
mkdir -p "$WS/eval_out/course"
if [ "${RAMP70_CHILD:-0}" != 1 ]; then
  RAMP70_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi

export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-ramp70}
RAM_FLOOR_G=${RAM_FLOOR_G:-0.8}
D=$WS/src/sant_vla_pkg/data_course_multiobj
echo "[run] $(date '+%F %T') domain=$ROS_DOMAIN_ID partition=$GZ_PARTITION floor=${RAM_FLOOR_G}G"
[ -e "$D/packed_ramp70" ] && { echo "[run] $D/packed_ramp70 이미 있음 — 옮기고 다시"; exit 2; }

TAG=ramp70 SWERVE=1 FIXED_INDEX=70 START_WIN=20,23 EGO_LANE=lane2 OB_VARIANTS=v0,v1 \
  SWERVE_TRIGGER=10 SWERVE_RAMP=9 CONTROLLER=stanley GZ_GUI=false \
  TRAIN_MODELS=hatchback_red,hatchback_blue,hatchback_yellow,prius_hybrid,ob_box,ob_cone,ob_barrier \
  HELDOUT_MODELS=ob_barrel,ob_person TRAIN_GROUPS=96 HELDOUT_GROUPS=6 \
  SEED_TRAIN=20261002 SEED_HELD=20261003 \
  bash "$WS/tools/collect_multiobj_avoid.sh" &
CPID=$!

ABORT=0
while kill -0 "$CPID" 2>/dev/null; do
  AVAIL=$(awk '/MemAvailable/ {print $2/1048576}' /proc/meminfo)
  if awk -v a="$AVAIL" -v f="$RAM_FLOOR_G" 'BEGIN{exit !(a<f)}'; then
    echo "[run] $(date +%T) 가용 RAM ${AVAIL}G < ${RAM_FLOOR_G}G — 수집 중단"
    pat='collect_corpu'; pkill -INT -f "${pat}s.py"
    ABORT=1
    sleep 20; kill -TERM "$CPID" 2>/dev/null   # 홀드아웃 단계로 넘어가지 않게
    break
  fi
  sleep 10
done
wait "$CPID"; RC=$?
echo "[run] $(date +%T) collect rc=$RC abort=$ABORT"

# 수집 스크립트가 중간에 빠지면(홀드아웃 스폰 실패 등) 스택이 남는다 — 여기서 정리
"$WS/smolvla_demo.sh" down > /dev/null 2>&1
pat='route_oracle_nod'; pkill -f "${pat}e"
pat='episode_recorde'; pkill -f "${pat}r"
for _ in $(seq 1 15); do
  pgrep -f 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]' >/dev/null || break
  sleep 1
done
echo "[run] 스택 정리 후 잔존: $(pgrep -c -f 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]')"

[ "$ABORT" = 1 ] && { echo "[run] RAM 중단 — 학습 체인 생략"; exit 4; }
[ -f "$D/packed_ramp70/index.jsonl" ] || { echo "[run] packed_ramp70 없음 — 학습 체인 생략"; exit 5; }
python3 - "$D/packed_ramp70/index.jsonl" <<'EOF'
import json, sys, collections
c = collections.Counter(json.loads(l)["cf_variant_id"] for l in open(sys.argv[1]))
print("[run] packed_ramp70:", dict(c))
EOF
bash "$WS/tools/ramp70_train_chain.sh"
echo "[run] $(date '+%F %T') ALL_DONE rc=$?"

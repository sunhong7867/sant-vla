#!/bin/bash
# 말로 지정한 물체로 가기 수집 (2026-10-03, 단기강좌 실습). 시야 안 물체 3~4 개(학습 플릿), 같은 출발에서 목표만 다른 짝,
# 차선 위 목표는 "곧장" vs "차선 따라" 짝. 오라클 = route_oracle point / lane_point. div_run.sh 의 격리·RAM 감시·정리 재사용.
#   TAG=gpilot NGOTO=10 bash tools/goto_run.sh        # 시범
#   TAG=goto NGOTO=700 bash tools/goto_run.sh         # 본 수집
#   GZ_GUI=true TAG=gpilot NGOTO=10 bash tools/goto_run.sh   # 시뮬 창 보면서 (RAM 하한 2.0G)
#   FLOOR_GROUPS=4 ...                                # 노이즈 하한 실측 그룹 (verify 가 요구)
#   GOTO_SECTORS=1 TAG=sec NGOTO=10 bash tools/goto_run.sh   # 3분류 방향 실습 수집
#   tail -f eval_out/course/div_run_<TAG>.log
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
TAG=${TAG:-goto}
LOG=$WS/eval_out/course/div_run_${TAG}.log
mkdir -p "$WS/eval_out/course"
if [ "${DIV_CHILD:-0}" != 1 ]; then
  DIV_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi

export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-div}
# GZ_GUI=true 로 켜면 gz 창이 1~2G 를 더 쓴다. 0.8G 하한은 창을 띄운 상태에서는
# 시스템이 먼저 멈춘 뒤에 걸리므로, GUI 를 켤 때는 하한을 올려 먼저 중단시킨다.
if [ "${GZ_GUI:-false}" = true ]; then RAM_FLOOR_G=${RAM_FLOOR_G:-2.0}
else RAM_FLOOR_G=${RAM_FLOOR_G:-0.8}; fi
D=$WS/src/sant_vla_pkg/data_course_multiobj
echo "[run] $(date '+%F %T') domain=$ROS_DOMAIN_ID partition=$GZ_PARTITION floor=${RAM_FLOOR_G}G"
[ -e "$D/packed_${TAG}" ] && { echo "[run] $D/packed_${TAG} 이미 있음 — 옮기고 다시"; exit 2; }

TAG=$TAG GOTO_V2=${GOTO_V2:-0} GOTO_SECTORS=${GOTO_SECTORS:-0} GOTO_GROUPS=${NGOTO:-10} GOTO_SPLIT=${GOTO_SPLIT:-train} GOTO_LANE_FRAC=${LANE_FRAC:-0.3} \
  CONTROLLER=stanley GZ_GUI=${GZ_GUI:-false} POSE_SOURCE=cli FLOOR_GROUPS=${FLOOR_GROUPS:-0} \
  TRAIN_MODELS=${TRAIN_MODELS:-go_cone_red,go_cone_yellow,go_cone_blue,go_cone_white,ob_box,ob_barrel,ob_barrier,hatchback_red,hatchback_blue,go_dog,go_horse,go_hydrant,go_chair,go_trashbin} \
  HELDOUT_MODELS=${HELDOUT_MODELS:-go_cone_green,go_dino_trex,ob_person,hatchback_green} TRAIN_GROUPS=0 HELDOUT_GROUPS=0 \
  SEED_TRAIN=${SEED_TRAIN:-20261080} \
  bash "$WS/tools/collect_multiobj_avoid.sh" &
CPID=$!

ABORT=0
while kill -0 "$CPID" 2>/dev/null; do
  AVAIL=$(awk '/MemAvailable/ {print $2/1048576}' /proc/meminfo)
  if awk -v a="$AVAIL" -v f="$RAM_FLOOR_G" 'BEGIN{exit !(a<f)}'; then
    echo "[run] $(date +%T) 가용 RAM ${AVAIL}G < ${RAM_FLOOR_G}G — 수집 중단"
    bash "$WS/tools/kill_partition_stack.sh" -INT 'collect_corpu[s].py'
    ABORT=1
    sleep 20; kill -TERM "$CPID" 2>/dev/null   # 홀드아웃 단계로 넘어가지 않게
    break
  fi
  sleep 10
done
wait "$CPID"; RC=$?
echo "[run] $(date +%T) collect rc=$RC abort=$ABORT"

# 수집 스크립트가 중간에 빠지면(홀드아웃 스폰 실패 등) 스택이 남는다 — 여기서 정리
bash "$WS/tools/kill_partition_stack.sh" -15 >/dev/null; sleep 2
bash "$WS/tools/kill_partition_stack.sh" -9 >/dev/null
for _ in $(seq 1 15); do
  pgrep -f 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]' >/dev/null || break
  sleep 1
done
echo "[run] 스택 정리 후 잔존: $(pgrep -c -f 'gz si[m]|route_oracle_nod[e]|episode_recorde[r]')"

[ "$ABORT" = 1 ] && { echo "[run] RAM 중단"; exit 4; }
[ -f "$D/packed_${TAG}/index.jsonl" ] || { echo "[run] packed_${TAG} 없음"; exit 5; }
python3 - "$D/packed_${TAG}/index.jsonl" <<'EOF2'
import json, sys, collections
c = collections.Counter(json.loads(l)["cf_variant_id"] for l in open(sys.argv[1]))
print("[run] packed:", dict(c))
EOF2
echo "[run] $(date '+%F %T') ALL_DONE"

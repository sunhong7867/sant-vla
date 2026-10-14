#!/bin/bash
# 다장애물 주행 수집 (2026-10-02, 선배 방식): 1·2차선 어디서나 출발, 한 바퀴에 장애물 3 개를 양 차선 무작위로,
# 우리 차선 장애물은 꺾는 거리 9~14 m·차선 전환 6~13 m·복귀 4~8 m 를 장애물마다 무작위(사람 운전 흉내).
# div_run.sh 의 격리·RAM 감시·정리를 그대로 쓴다. 기본 v1(장애물 있는 판)만 — 바퀴 안에 빈 구간이 섞여 있음.
#   TAG=multipilot NRUNS=6 bash tools/multi_run.sh        # 시범
#   TAG=mrun NRUNS=120 bash tools/multi_run.sh            # 본 수집 (약 3 h)
#   tail -f eval_out/course/div_run_<TAG>.log
# 학습 체인은 돌리지 않는다(수집만).
#
# 2026-09-29 첫 수집은 다른 세션의 캡처가 같은 gz 에 obstacle1 을 놓아 전량 폐기
# (packed_ramp70_contaminated). 그래서:
#   - ROS_DOMAIN_ID / GZ_PARTITION 을 분리해 다른 도구가 이 시뮬에 붙지 못하게 한다
#   - gz 창 없이(GZ_GUI=false) 돌려 RAM 을 아낀다
#   - 가용 RAM 이 RAM_FLOOR_G 밑으로 내려가면 수집을 멈춘다(프리즈 대신 중단)
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
TAG=${TAG:-mrun}
LOG=$WS/eval_out/course/div_run_${TAG}.log
mkdir -p "$WS/eval_out/course"
if [ "${DIV_CHILD:-0}" != 1 ]; then
  DIV_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"
  exit 0
fi

export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-div}
RAM_FLOOR_G=${RAM_FLOOR_G:-0.8}
D=$WS/src/sant_vla_pkg/data_course_multiobj
echo "[run] $(date '+%F %T') domain=$ROS_DOMAIN_ID partition=$GZ_PARTITION floor=${RAM_FLOOR_G}G"
[ -e "$D/packed_${TAG}" ] && { echo "[run] $D/packed_${TAG} 이미 있음 — 옮기고 다시"; exit 2; }

TAG=$TAG SWERVE=1 MULTI_GROUPS=${NRUNS:-120} OB_VARIANTS=${OB_VARIANTS:-v1} \
  MULTI_TRIGGER=${MULTI_TRIGGER:-} MULTI_RAMP=${MULTI_RAMP:-} \
  SWERVE_TRIGGER=10 SWERVE_RAMP=9 CONTROLLER=stanley GZ_GUI=false POSE_SOURCE=cli \
  TRAIN_MODELS=${TRAIN_MODELS:-ob_box,ob_barrel,ob_cone,ob_barrier,hatchback_red} \
  HELDOUT_MODELS=${HELDOUT_MODELS:-ob_person,hatchback_green} TRAIN_GROUPS=0 HELDOUT_GROUPS=0 \
  SEED_TRAIN=${SEED_TRAIN:-20261070} \
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

[ "$ABORT" = 1 ] && { echo "[run] RAM 중단"; exit 4; }
[ -f "$D/packed_${TAG}/index.jsonl" ] || { echo "[run] packed_${TAG} 없음"; exit 5; }
python3 - "$D/packed_${TAG}/index.jsonl" <<'EOF2'
import json, sys, collections
c = collections.Counter(json.loads(l)["cf_variant_id"] for l in open(sys.argv[1]))
print("[run] packed:", dict(c))
EOF2
echo "[run] $(date '+%F %T') ALL_DONE"

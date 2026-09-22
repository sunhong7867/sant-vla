#!/bin/bash
# 다중 물체 회피 홀드아웃 실험 — 수집 스크립트 (2026-09-22).
#
# 질문: 회피를 "차량"으로만 배우면 다른 물체엔 반응하지 않는가, 여러 종류의
# 물체로 배우면 "차선 위에 뭔가 있으면 피한다"로 일반화되는가.
#
# 구성 (v9 회피 축 재사용, 물체 종류만 바뀜):
#   train   : TRAIN_MODELS 를 순환하며 v0(빈 차선)/v1(우리 차선, 회피)/v2(옆 차선,
#             유지) 대조 3종 수집
#   heldout : HELDOUT_MODELS (train 에 없는 물체) 로 같은 대조 3종 수집 —
#             학습에는 절대 넣지 말 것. 개방루프 평가·라벨 대조용
#
# 사용:
#   bash tools/collect_multiobj_avoid.sh                  # 기본 구성
#   TRAIN_GROUPS=4 HELDOUT_GROUPS=2 bash tools/collect_multiobj_avoid.sh   # 파일럿
#   DRY=1 bash tools/collect_multiobj_avoid.sh            # 시뮬 없이 플랜만 출력
#   TRAIN_MODELS=hatchback_red,hatchback_blue HELDOUT_MODELS=ob_person \
#       bash tools/collect_multiobj_avoid.sh              # 대조군: 차량만 학습
#
# 비교 실험을 한 쌍으로 돌리려면 TAG 를 바꿔 두 번 실행한다:
#   TAG=carsonly TRAIN_MODELS=hatchback_red,hatchback_blue,hatchback_yellow ...
#   TAG=multi    TRAIN_MODELS=hatchback_red,ob_box,ob_barrel,ob_cone,ob_barrier ...
# 둘 다 HELDOUT_MODELS=ob_person 으로 두면 "사람"에 대한 반응 차이가 실험 결과다.
#
# 후속: packed_<TAG> 로 학습 → tools/eval/avoidance_trial.py --models ob_person
#       --no-supervisor 로 폐루프 확인 (학습 없이 물체만 바꾼 정책 반응).
#
# 절차·함정은 collect_v9_full.sh 와 같다: 장애물은 한 번만 스폰하고 teleport 만,
# pkill 은 자기매치 방지 패턴, 클록 100 Hz, 배치마다 레코더 재기동.
# (set -u 금지: ROS setup.bash 가 미정의 변수를 참조한다)
WS=/home/sh/ROS2_project/sant-vla
TAG=${TAG:-multi}
OUT=$WS/eval_out/multiobj_$TAG
DATA=$WS/src/sant_vla_pkg/data_multiobj
TRAIN_MODELS=${TRAIN_MODELS:-hatchback_red,hatchback_blue,ob_box,ob_barrel,ob_cone,ob_barrier}
HELDOUT_MODELS=${HELDOUT_MODELS:-ob_person,hatchback_green}
TRAIN_GROUPS=${TRAIN_GROUPS:-36}     # 6종 x 6 스타트 = 물체당 6 그룹 (18 에피소드)
HELDOUT_GROUPS=${HELDOUT_GROUPS:-8}
SEED_TRAIN=${SEED_TRAIN:-20260922}
SEED_HELD=${SEED_HELD:-20260923}
DRY=${DRY:-0}
COLLECT=$WS/src/sant_vla_pkg/scripts/collect_corpus.py

source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

# 모델 디렉터리 존재 확인 (오타로 빈 플릿을 2시간 수집하는 사고 방지)
for m in ${TRAIN_MODELS//,/ } ${HELDOUT_MODELS//,/ }; do
  [ -d "$WS/src/simulation_pkg/models/$m" ] || { echo "[multiobj] 모델 없음: $m"; exit 2; }
done
for m in ${HELDOUT_MODELS//,/ }; do
  case ",$TRAIN_MODELS," in *",$m,"*) echo "[multiobj] $m 이 train 과 heldout 양쪽에 있음 — 홀드아웃이 아님"; exit 2;; esac
done

if [ "$DRY" = "1" ]; then
  echo "[multiobj] DRY: train fleet=$TRAIN_MODELS groups=$TRAIN_GROUPS"
  python3 $COLLECT --driver oracle --groups 0 --speed-groups 0 --floor-groups 0 \
    --ring-groups 0 --obstacle-groups "$TRAIN_GROUPS" --obstacle-models "$TRAIN_MODELS" \
    --group-prefix "${TAG}t_" --split train --seed "$SEED_TRAIN" --dry-run | tail -15
  echo "[multiobj] DRY: heldout fleet=$HELDOUT_MODELS groups=$HELDOUT_GROUPS"
  python3 $COLLECT --driver oracle --groups 0 --speed-groups 0 --floor-groups 0 \
    --ring-groups 0 --obstacle-groups "$HELDOUT_GROUPS" --obstacle-models "$HELDOUT_MODELS" \
    --group-prefix "${TAG}h_" --split heldout --seed "$SEED_HELD" --dry-run | tail -15
  exit 0
fi

mkdir -p "$OUT" "$DATA"
AVAIL=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
[ "$AVAIL" -ge 3 ] || { echo "[multiobj] 가용 RAM ${AVAIL}G < 3G — 앱을 닫고 재시도"; exit 4; }

# 실행 중 스택 정리 (패턴은 자기 자신에 매치되지 않도록 분할)
pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='route_oracle_nod';  pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
pat='collect_corpu';     pkill -f "${pat}s.py"        2>/dev/null
for _ in $(seq 1 10); do
  pgrep -f "gz si[m]|route_oracle_nod[e]|episode_recorde[r]" >/dev/null || break
  sleep 1
done
ros2 daemon stop >/dev/null 2>&1
sleep 3
rm -rf ~/.gz/sim/log
rm -f /dev/shm/fastrtps_* /dev/shm/sem.fastrtps_* /dev/shm/fastdds_* /dev/shm/sem.fastdds_* 2>/dev/null

echo "[multiobj] 시뮬 기동 (clock 100 Hz)..."
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py \
  use_camera:=true use_perception_pipeline:=false use_driver:=false \
  use_policy:=false use_debug_visualizers:=false use_vla_camera:=false \
  clock_hz:=100.0 \
  > "$OUT/sim.log" 2>&1 < /dev/null &
for _ in $(seq 1 24); do
  N=$(timeout 5 ros2 topic list 2>/dev/null | grep -c "camera/image_raw")
  [ "${N:-0}" -ge 1 ] && break
  sleep 5
done
[ "${N:-0}" -ge 1 ] || { echo "[multiobj] SIM_FAIL — $OUT/sim.log (GLX BadValue 면 nvidia 드라이버)"; exit 3; }

spawn_fleet() {  # $1=comma list — 한 번만 스폰, 이후 collect_corpus 가 teleport
  echo "[multiobj] 장애물 플릿 상주 스폰: $1"
  FLEET="$1" python3 - <<'PYEOF' || return 1
import os, sys
sys.path.insert(0, "/home/sh/ROS2_project/sant-vla/src/simulation_pkg")
from simulation_pkg import basic
models = [m for m in os.environ["FLEET"].split(",") if m]
for i, m in enumerate(models):
    basic.load_model(f"v9_{m}", m, (60.0 + 8.0 * i, 60.0, 0.01265,
                                    0.0, 0.0, 0.0), skip_if_exists=True)
print("spawned", len(models))
PYEOF
}
remove_fleet() {
  FLEET="$1" python3 - <<'PYEOF'
import os, sys
sys.path.insert(0, "/home/sh/ROS2_project/sant-vla/src/simulation_pkg")
from simulation_pkg import basic
for m in [m for m in os.environ["FLEET"].split(",") if m]:
    try: basic.remove_model(f"v9_{m}")
    except Exception as e: print("remove failed", m, e)
PYEOF
}

echo "[multiobj] 오라클 기동..."
setsid nohup ros2 run sant_vla_pkg route_oracle_node --ros-args \
  -p use_sim_time:=true > "$OUT/oracle.log" 2>&1 < /dev/null &
sleep 3

run_batch() {  # $1=groups $2=prefix $3=split $4=seed $5=pack_dir $6=fleet
  setsid nohup ros2 run sant_vla_pkg episode_recorder_node --ros-args \
    -p out_dir:="$DATA" -p use_sim_time:=true \
    > "$OUT/recorder_$2.log" 2>&1 < /dev/null &
  sleep 5
  echo "[multiobj] 수집: $2 ${1}그룹 split=$3 fleet=$6 ($(date +%H:%M))..."
  python3 $COLLECT \
    --driver oracle --groups 0 --speed-groups 0 --floor-groups 0 \
    --ring-groups 0 --obstacle-groups "$1" --obstacle-models "$6" \
    --group-prefix "$2" --split "$3" --seed "$4" --out-dir "$DATA" \
    > "$OUT/collect_$2.log" 2>&1
  RC=$?
  tail -6 "$OUT/collect_$2.log"
  pat='episode_recorde'; pkill -f "${pat}r" 2>/dev/null
  for _ in $(seq 1 8); do pgrep -f "episode_recorde[r]" >/dev/null || break; sleep 1; done
  SESS=$(ls -dt "$DATA"/session_*/ep_0000 2>/dev/null | head -1 | xargs dirname)
  if [ -n "$SESS" ] && [ "$RC" -eq 0 ]; then
    echo "[multiobj] finalize: $SESS -> $5"
    PACK_OUT=$5 RESAMPLE_EXTRA="--max-interp-err-m 0.06" \
      bash $WS/src/sant_vla_pkg/scripts/finalize_corpus.sh "$SESS" \
      > "$OUT/finalize_$2.log" 2>&1 \
      && echo "[multiobj] finalize OK" || echo "[multiobj] finalize FAIL — $OUT/finalize_$2.log"
  fi
  return $RC
}

# train 플릿과 heldout 플릿은 같은 월드에 동시에 두지 않는다: heldout 물체가
# 파킹 스팟에라도 존재하면 "학습 중 한 번도 본 적 없음"을 보장할 수 없다.
spawn_fleet "$TRAIN_MODELS" || { echo "[multiobj] OBSTACLE_SPAWN_FAIL"; exit 5; }
run_batch $TRAIN_GROUPS   "${TAG}t_" train   $SEED_TRAIN "$DATA/packed_${TAG}" "$TRAIN_MODELS"
remove_fleet "$TRAIN_MODELS"
sleep 2
spawn_fleet "$HELDOUT_MODELS" || { echo "[multiobj] OBSTACLE_SPAWN_FAIL (heldout)"; exit 5; }
run_batch $HELDOUT_GROUPS "${TAG}h_" heldout $SEED_HELD  "$DATA/packed_${TAG}_heldout" "$HELDOUT_MODELS"
remove_fleet "$HELDOUT_MODELS"

pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='route_oracle_nod';  pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
sleep 3
rm -rf ~/.gz/sim/log
echo "[multiobj] DONE ($(date +%H:%M)) — train=$DATA/packed_${TAG} heldout=$DATA/packed_${TAG}_heldout"

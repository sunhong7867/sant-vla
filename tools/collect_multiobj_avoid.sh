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
#   TAG=multi_fix V1_ONLY=1 TRAIN_GROUPS=24 HELDOUT_GROUPS=0 SEED_TRAIN=20260923 \
#       bash tools/collect_multiobj_avoid.sh              # v1(회피)만 보충 (tf 갭 드롭 보정)
#   TAG=multi_hard V1_ONLY=1 OB_ACCEL=1.5 OB_STOP_MARGIN=9 TRAIN_GROUPS=36 HELDOUT_GROUPS=6 \
#       bash tools/collect_multiobj_avoid.sh              # 강한 제동 시연 (청크당 감속 크게)
#   TAG=swerve SWERVE=1 FIXED_INDEX=142 TRAIN_GROUPS=24 HELDOUT_GROUPS=6 \
#       bash tools/collect_multiobj_avoid.sh              # 정지 없는 직접 차선변경, 위치 고정
#   TAG=ramp SWERVE=1 FIXED_INDEX=142 EGO_LANE=lane2 OB_VARIANTS=v0,v1 \
#       SWERVE_TRIGGER=10 SWERVE_RAMP=9 CONTROLLER=stanley TRAIN_GROUPS=36 HELDOUT_GROUPS=0 \
#       bash tools/collect_multiobj_avoid.sh              # 램프 차선변경(2026-09-29): 2차선→1차선만, Stanley
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
OUT=$WS/eval_out/course/multiobj_$TAG
DATA=$WS/src/sant_vla_pkg/data_course_multiobj
TRAIN_MODELS=${TRAIN_MODELS:-hatchback_red,hatchback_blue,ob_box,ob_barrel,ob_cone,ob_barrier}
HELDOUT_MODELS=${HELDOUT_MODELS:-ob_person,hatchback_green}
TRAIN_GROUPS=${TRAIN_GROUPS:-36}     # 6종 x 6 스타트 = 물체당 6 그룹 (18 에피소드)
HELDOUT_GROUPS=${HELDOUT_GROUPS:-8}
SEED_TRAIN=${SEED_TRAIN:-20260922}
SEED_HELD=${SEED_HELD:-20260923}
DRY=${DRY:-0}
V1_ONLY=${V1_ONLY:-0}                # 1: 회피 변형(v1)만 — 드롭된 v1 을 보충하는 repair 배치
COLLECT=$WS/src/sant_vla_pkg/scripts/collect_corpus.py
V1_FLAG=""; [ "$V1_ONLY" = 1 ] && V1_FLAG="--obstacle-v1-only"
# 제동 강도: OB_ACCEL 은 오라클 accel_limit 과 collect_corpus 의 제동거리 계산에
# 같이 들어간다. 기본 0.55/12 m 시연은 청크당 −0.28 m/s 로 너무 완만했다(r29/r30).
OB_ACCEL=${OB_ACCEL:-0.55}
OB_STOP_MARGIN=${OB_STOP_MARGIN:-12.0}
SWERVE=${SWERVE:-0}                  # 1: 정지 없이 15 m 전방에서 바로 차선 변경
FIXED_INDEX=${FIXED_INDEX:-}         # 장애물 차선 인덱스 고정 (lane2 frac 0.35 = 142)
SWERVE_TRIGGER=${SWERVE_TRIGGER:-}   # 회피 시작 중심거리(m), 비우면 collect_corpus 기본 8
SWERVE_RAMP=${SWERVE_RAMP:-}         # 차선 전환 램프 길이(m), 비우면 0 = 즉시 교체(packed_swerve)
EGO_LANE=${EGO_LANE:-}               # lane2 = 2차선에서만 출발 (→ 1차선으로 회피)
OB_VARIANTS=${OB_VARIANTS:-}         # 예: v0,v1 (v2 옆 차선 대조 제외)
CONTROLLER=${CONTROLLER:-pure_pursuit}  # stanley = r26 순항 선생과 같은 제어기 (램프 필요)
EXTRA_FLAGS=""
[ "$SWERVE" = 1 ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-swerve-only"
[ -n "$SWERVE_TRIGGER" ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-swerve-trigger-m $SWERVE_TRIGGER"
[ -n "$SWERVE_RAMP" ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-swerve-ramp-m $SWERVE_RAMP"
[ -n "$EGO_LANE" ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-ego-lane $EGO_LANE"
[ -n "$OB_VARIANTS" ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-variants $OB_VARIANTS"
if [ "$CONTROLLER" = stanley ] && [ "$SWERVE" = 1 ] && [ -z "$SWERVE_RAMP" ]; then
  echo "[multiobj] Stanley 는 램프 없이 차선변경 못 함 — SWERVE_RAMP 를 지정"; exit 2
fi
[ -n "$FIXED_INDEX" ] && EXTRA_FLAGS="$EXTRA_FLAGS --ob-fixed-index $FIXED_INDEX"

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
    --ring-groups 0 --obstacle-groups "$TRAIN_GROUPS" --obstacle-models "$TRAIN_MODELS" $V1_FLAG $EXTRA_FLAGS \
    --group-prefix "${TAG}t_" --split train --seed "$SEED_TRAIN" --dry-run | tail -15
  echo "[multiobj] DRY: heldout fleet=$HELDOUT_MODELS groups=$HELDOUT_GROUPS"
  python3 $COLLECT --driver oracle --groups 0 --speed-groups 0 --floor-groups 0 \
    --ring-groups 0 --obstacle-groups "$HELDOUT_GROUPS" --obstacle-models "$HELDOUT_MODELS" $V1_FLAG $EXTRA_FLAGS \
    --group-prefix "${TAG}h_" --split heldout --seed "$SEED_HELD" --dry-run | tail -15
  exit 0
fi

mkdir -p "$OUT" "$DATA"
MIN_RAM_G=${MIN_RAM_G:-3}   # 사용자 앱을 못 닫는 날은 2.5 까지 낮춰 봄(스왑 있을 때만)
AVAIL=$(awk '/MemAvailable/ {print $2/1048576}' /proc/meminfo)
awk -v a="$AVAIL" -v m="$MIN_RAM_G" 'BEGIN{exit !(a<m)}' && { echo "[multiobj] 가용 RAM ${AVAIL}G < ${MIN_RAM_G}G — 앱을 닫고 재시도"; exit 4; }

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
  # race_scenarios.static_model 로 스폰: 센서·플러그인·카메라/라이다 링크를 뗀
  # 정적 모델. prius_hybrid(ego 와 같은 차)를 basic.load_model 로 올리면 카메라
  # 토픽까지 달고 나와 ego 카메라와 충돌한다. 프리미티브(ob_*)도 같은 경로.
  echo "[multiobj] 장애물 플릿 상주 스폰(정적): $1"
  FLEET="$1" python3 - <<'PYEOF' || return 1
import json, os, sys, time
import xml.etree.ElementTree as ET
from pathlib import Path
from sant_vla_pkg.race_scenarios import static_model
from sant_vla_pkg.gazebo_services import pose_message, request
from sant_vla_pkg.gz_pose import list_models, resolve_gz_bin
models = [m for m in os.environ["FLEET"].split(",") if m]
cache = Path(os.path.expanduser("~/ROS2_project/sant-vla/eval_out/demo/scene_models"))
cache.mkdir(parents=True, exist_ok=True)
present = set(list_models(resolve_gz_bin()))
for i, m in enumerate(models):
    name = f"v9_{m}"
    if name in present:
        print("exists", name); continue
    f = cache / f"{name}.sdf"
    ET.ElementTree(static_model(m, name)).write(f, encoding="unicode")
    pose = (60.0 + 8.0 * i, 60.0, 0.01265, 0.0, 0.0, 0.0)
    request("/world/default/create", "gz.msgs.EntityFactory",
            f"sdf_filename: {json.dumps(str(f))} name: {json.dumps(name)} "
            f"allow_renaming: false pose: {{{pose_message(pose)}}}")
deadline = time.monotonic() + 15
want = {f"v9_{m}" for m in models}
while time.monotonic() < deadline and not want <= set(list_models(resolve_gz_bin())):
    time.sleep(0.3)
missing = want - set(list_models(resolve_gz_bin()))
if missing:
    print("MISSING", sorted(missing)); sys.exit(1)
print("spawned", len(models))
PYEOF
}
remove_fleet() {
  FLEET="$1" python3 - <<'PYEOF'
import json, os, time
from sant_vla_pkg.gazebo_services import request
from sant_vla_pkg.gz_pose import list_models, resolve_gz_bin
for m in [m for m in os.environ["FLEET"].split(",") if m]:
    name = f"v9_{m}"
    try:
        request("/world/default/remove", "gz.msgs.Entity", f"name: {json.dumps(name)} type: MODEL")
    except Exception as e:
        print("remove failed", name, e)
deadline = time.monotonic() + 10
while time.monotonic() < deadline and any(n.startswith("v9_") for n in list_models(resolve_gz_bin())):
    time.sleep(0.3)
print("fleet removed")
PYEOF
}

echo "[multiobj] 오라클 기동..."
# lookahead_gain 0.6: v10p 가 전 매트릭스 무접촉으로 실측한 값. 기본 0.9 는 v9 의
# 차선중심 회귀(중앙값 0.54~0.88 m) 원인 후보였다. 즉시 차선 교체는 Stanley 가
# 3.15 m 오차를 한 번에 봐서 못 쓰지만, lane_ramp_m 램프(2026-09-29)가 있으면
# CONTROLLER=stanley 로 r26 순항 선생과 같은 제어기를 쓸 수 있다.
setsid nohup ros2 run sant_vla_pkg route_oracle_node --ros-args -p lookahead_gain:=${LG:-0.6} -p accel_limit:=$OB_ACCEL \
  -p controller:=$CONTROLLER \
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
    --ring-groups 0 --obstacle-groups "$1" --obstacle-models "$6" $V1_FLAG \
    --ob-accel "$OB_ACCEL" --ob-stop-margin "$OB_STOP_MARGIN" $EXTRA_FLAGS \
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
if [ "$HELDOUT_GROUPS" -gt 0 ]; then
  spawn_fleet "$HELDOUT_MODELS" || { echo "[multiobj] OBSTACLE_SPAWN_FAIL (heldout)"; exit 5; }
  run_batch $HELDOUT_GROUPS "${TAG}h_" heldout $SEED_HELD  "$DATA/packed_${TAG}_heldout" "$HELDOUT_MODELS"
  remove_fleet "$HELDOUT_MODELS"
fi

pat='gz si';             pkill -9 -f "${pat}m"        2>/dev/null
pat='driving_sim.launc'; pkill -f "${pat}h"           2>/dev/null
pat='route_oracle_nod';  pkill -f "${pat}e"           2>/dev/null
pat='episode_recorde';   pkill -f "${pat}r"           2>/dev/null
sleep 3
rm -rf ~/.gz/sim/log
bash $WS/tools/cleanup_artifacts.sh | tail -3
echo "[multiobj] DONE ($(date +%H:%M)) — train=$DATA/packed_${TAG} heldout=$DATA/packed_${TAG}_heldout"

#!/bin/bash
# v8g 학습 완료 대기 → 체크포인트 반입 → 시뮬 기동 → 4종 프로브 → 정리
set -o pipefail
WS=/home/sh/ROS2_project/sant-vla
SRV=autolab_sw@115.145.211.157
OUT=$WS/eval_out
step() { echo; echo "======== [$(date +%H:%M)] $1 ========"; }

step "학습 완료 대기 (10분 폴링)"
for _ in $(seq 1 60); do
  DONE=$(ssh -o ConnectTimeout=15 "$SRV" \
    'grep -c "End of training" ~/sunhong/nav-vla/logs/navvla_smolvla_v8g.log 2>/dev/null' || echo 0)
  [ "${DONE:-0}" -ge 1 ] && break
  # 죽었는지 확인: 진행 로그가 20분 이상 멈추면 실패로 간주
  sleep 600
done
[ "${DONE:-0}" -ge 1 ] || { echo TRAIN_WAIT_TIMEOUT; exit 2; }

step "체크포인트 검증+반입"
SZ=$(ssh "$SRV" 'stat -c%s ~/sunhong/nav-vla/runs/navvla_smolvla_v8g/checkpoints/060000/pretrained_model/model.safetensors 2>/dev/null' || echo 0)
[ "${SZ:-0}" -gt 800000000 ] || { echo CKPT_UNHEALTHY size=$SZ; exit 3; }
rsync -a "$SRV":'~/sunhong/nav-vla/runs/navvla_smolvla_v8g/checkpoints/060000/pretrained_model/' \
  $WS/models/ckpt_v8g_60k/ || { echo PULL_FAIL; exit 3; }

step "시뮬 기동"
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash
p='gz si'; pkill -9 -f "${p}m" 2>/dev/null; p='driving_sim.launc'; pkill -f "${p}h" 2>/dev/null
sleep 3; rm -rf ~/.gz/sim/log
setsid nohup ros2 launch simulation_pkg driving_sim.launch.py use_camera:=true \
  use_perception_pipeline:=false use_driver:=false use_policy:=false \
  use_debug_visualizers:=false use_vla_camera:=false \
  > $OUT/v8g_sim.log 2>&1 < /dev/null &
sleep 25

step "4종 프로브 (직행 근/원거리 + CW + CCW)"
bash $WS/tools/eval/v8g_axis_probe.sh $WS/models/ckpt_v8g_60k v8g \
  || { echo PROBE_FAIL; bash $WS/tools/eval/teardown_probe_stack.sh; exit 4; }

step "정리"
bash $WS/tools/eval/teardown_probe_stack.sh
echo "V8G_CHAIN_DONE $(date +%H:%M)"

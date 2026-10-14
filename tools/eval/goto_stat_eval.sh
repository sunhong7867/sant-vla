#!/bin/bash
# 말로 지정한 물체로 가기 폐루프 평가 (2026-10-03). 스택 기동 → 단계별 goto_trial → 종료 → 요약.
#   RUN=r50 STEP=010000 TIERS="T1" N=30 bash tools/eval/goto_stat_eval.sh ; tail -f eval_out/course/goto_<RUN>_<STEP>.log
#   STEP=last 면 checkpoints/last. REWRITE=1 이면 T4 를 Qwen 재작성으로도 한 번 더(T4rw).
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
RUN=${RUN:?RUN=r50}; STEP=${STEP:-last}
LOG=$WS/eval_out/course/goto_${RUN}_${STEP}.log
if [ "${GE_CHILD:-0}" != 1 ]; then
  GE_CHILD=1 setsid nohup bash "$0" "$@" > "$LOG" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $LOG"; exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-goto}
export KEEP_TRIALS=100000
source /opt/ros/jazzy/setup.bash; source $WS/install/setup.bash
TIERS=${TIERS:-"T1 T2 T3a T3b T3c T4"}; N=${N:-30}; SEED=${SEED:-20261090}
OUT=$WS/eval_out/course/goto_eval; mkdir -p "$OUT"
# CKPT 를 밖에서 줄 수 있게 (2026-10-07): 베이스 r26 은 runs/course 밖에 있어
# runs/navvla_reasoning_r26/... 으로 직접 지정해야 한다.
CKPT=${CKPT:-runs/course/navvla_reasoning_${RUN}/checkpoints/${STEP}/pretrained_model}
TAG=${TAG:-${RUN}_${STEP}}   # output name; e.g. TAG=r52_030000_g3 with POLICY_GUIDE=3
echo "[ge] $(date '+%F %T') RUN=$RUN STEP=$STEP tiers=$TIERS N=$N ckpt=$CKPT"
# 2026-10-04: 사용자 앱(크롬·GPT)으로 가용 RAM 이 smolvla_demo 기준(5G) 아래면
# 바로 실패하지 말고 확보될 때까지 대기(최대 RAM_WAIT_H 시간, 5 분 간격).
ram_ok() { awk '/MemAvailable/{exit !($2/1048576 >= 5.2)}' /proc/meminfo; }
t_end=$(( $(date +%s) + ${RAM_WAIT_H:-24} * 3600 ))
until ram_ok; do
  [ "$(date +%s)" -gt "$t_end" ] && { echo "[ge] RAM_WAIT_TIMEOUT"; exit 3; }
  echo "[ge] $(date +%T) 가용 RAM $(awk '/MemAvailable/{printf "%.1f", $2/1048576}' /proc/meminfo)G < 5.2G — 5 분 대기"
  sleep 300
done
# XTRACK_GAIN 0.0 (2026-10-12): no pose-based lane-centring assist in goto evaluations
XTRACK_GAIN=${XTRACK_GAIN:-0.0} POLICY_GUIDE=${POLICY_GUIDE:-1.0} REMOTE_CKPT=$CKPT NAVVLA_RACE=qualifying "$WS/smolvla_demo.sh" --no-gui > "$OUT/${TAG}_bringup.log" 2>&1 \
  || { tail -20 "$OUT/${TAG}_bringup.log"; echo "[ge] BRINGUP_FAIL"; exit 3; }
grep -q "REMOTE_SERVING" "$WS/eval_out/demo/remote_start.log" || { echo "[ge] 원격 서빙 미확인"; exit 3; }
sleep 5
# 티어 항목 = TIER[:pos|:qpos|:qwen] (2026-10-04, r52): pos = 오라클 방향 문장(정책 단독),
# qpos = 이름·설명 문장 -> Qwen rewrite_pos -> 정책, qwen = Qwen 이름 재작성 -> 정책
for t in $TIERS; do
  echo "[ge] $(date +%T) tier $t"
  base=${t%%:*}; suf=""; [ "$t" != "$base" ] && suf=${t#*:}
  extra=""
  case "$suf" in pos) extra="--words pos";; qpos) extra="--rewrite qwen_pos";; qwen) extra="--rewrite qwen";; esac
  # 2026-10-12 point-goal tiers (P2/P3a/P3b): the harness publishes the ego-relative goal;
  # ":zero" = goal channel pinned to (0,0) (P2-ctrl b). GOAL_MODE env overrides the default.
  case "$base" in P4*) extra="$extra --goal-mode vlm";; P*) extra="$extra --goal-mode ${GOAL_MODE:-rel}";; esac
  [ "$suf" = zero ] && extra="--goal-mode zero"
  if [[ "$base" == P4* ]]; then
    # P4: perception node (VLM boxes -> bearing, LiDAR -> distance) drives /vla_goal.
    # ollama on the lab server reaches us through the demo tunnel (11501 -> 11500).
    # driving_sim.launch.py bridges no LiDAR; bridge the ego gpu_lidar for the node (GZ_PARTITION is exported)
    if ! pgrep -f 'scan@sensor_msg[s]' > /dev/null; then
      setsid nohup ros2 run ros_gz_bridge parameter_bridge /scan@sensor_msgs/msg/LaserScan@gz.msgs.LaserScan \
        --ros-args -r __node:=scan_bridge_p4 -p use_sim_time:=true > "$OUT/${TAG}_scan_bridge.log" 2>&1 < /dev/null &
    fi
    if ! pgrep -f 'goal_from_scene_nod[e]' > /dev/null; then
      setsid nohup python3 "$WS/src/sant_vla_pkg/sant_vla_pkg/goal_from_scene_node.py" --ros-args \
        -p use_sim_time:=true -p ollama_host:=http://127.0.0.1:11501 -p scan_topic:=/scan \
        -p hfov_deg:=62.2 ${GOAL_NODE_ARGS:-} > "$OUT/${TAG}_goal_node.log" 2>&1 < /dev/null &
      sleep 4
    fi
  fi
  python3 "$WS/tools/eval/goto_trial.py" --tier "$base" --n "$N" --seed "$SEED" $extra \
    --out "$OUT/${TAG}_${base}${suf}.jsonl" 2>&1 | grep -E '^\[(T|E|P|S)|Error|Traceback' 
  if [[ "$base" == P4* ]]; then pkill -f 'goal_from_scene_nod[e]'; pkill -f 'scan@sensor_msg[s]'; sleep 1; fi
  if [ "$t" = T4 ] && [ "${REWRITE:-0}" = 1 ]; then
    echo "[ge] $(date +%T) tier T4 + Qwen rewrite"
    python3 "$WS/tools/eval/goto_trial.py" --tier T4 --n "$N" --seed "$SEED" --rewrite qwen \
      --out "$OUT/${RUN}_${STEP}_T4rw.jsonl" 2>&1 | grep -E '^\[T'
  fi
done
"$WS/smolvla_demo.sh" down > /dev/null 2>&1
python3 "$WS/tools/eval/goto_analyze.py" "$OUT" "${TAG}"
echo "[ge] ALL_DONE $(date +%T)"

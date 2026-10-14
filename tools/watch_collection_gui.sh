#!/bin/bash
# 헤드리스 수집(multi_run.sh, GZ_GUI=false)에 gz GUI 창만 붙여서 본다 (2026-10-12).
# 서버(시뮬)는 건드리지 않는다 — 창을 닫아도 수집은 계속된다. 시뮬이 재기동되면 창이 끊기니 다시 실행.
#   bash tools/watch_collection_gui.sh            # 기본 partition=div (multi_run.sh)
#   PART=stat bash tools/watch_collection_gui.sh  # stat_eval 평가 시뮬
#   PART=default bash tools/watch_collection_gui.sh  # partition 없이 띄운 smolvla_demo.sh --no-gui
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
PART=${PART:-div}
pgrep -f 'gz sim -r -[s]' >/dev/null || { echo "헤드리스 시뮬 서버가 없음"; exit 1; }
if pgrep -f 'gz sim -[g]' >/dev/null; then echo "GUI 창이 이미 떠 있음 (pid $(pgrep -f 'gz sim -[g]' | head -1))"; exit 0; fi
AV=$(awk '/MemAvailable/ {printf "%.1f", $2/1048576}' /proc/meminfo)
awk -v a="$AV" 'BEGIN{exit !(a<3.0)}' && { echo "가용 RAM ${AV}G < 3G — 수집 중단(0.8G) 위험, 창을 띄우지 않음"; exit 2; }
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"
if [ "$PART" = default ]; then unset GZ_PARTITION; else export GZ_PARTITION=$PART; fi
export GZ_SIM_RESOURCE_PATH=$WS/src/simulation_pkg/models:$WS/install/simulation_pkg/share/simulation_pkg/models:$WS/install/simulation_pkg/share/simulation_pkg:/opt/ros/jazzy/share
setsid nohup gz sim -g > "$WS/eval_out/course/watch_gui_${PART}.log" 2>&1 < /dev/null &
echo "GUI 기동 (pid $!, partition=$PART, RAM ${AV}G) — 로그 eval_out/course/watch_gui_${PART}.log"

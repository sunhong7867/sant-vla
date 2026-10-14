#!/bin/bash
# 회피 트라이얼 확대 영상 (2026-09-30). 월드 top_camera 를 장애물 위로 옮겨 내려다보며 녹화.
#   bash tools/eval/record_clip.sh            # 백그라운드, 로그 eval_out/course/clips/record.log
#   CLIPS="lane2:avoid lane1:crash" CKPT=... CURV_BOOST_SLOW=1.0 bash tools/eval/record_clip.sh
#   CLIPS="lane2:r41_person_avoid:ob_person" ...   # 세 번째 칸 = 장애물 모델(기본 ob_box)
#   CLIPS="lane2:sw80_70_empty:none:0.1725:sw80" ORACLE=0 ...  # 넷째 = 장애물 frac, 다섯째 = 체크포인트 RUN
#     (2026-10-01) frac 0.1725/0.35 는 카메라 자동 배치(접근 22 m 전체가 보이게), none = 빈 차선
# 기본: r40 + 좌표 정답 문구(--oracle-situation), curv_boost_slow 1.0, 박스 1회씩
#   lane2:0.1725 = 우리 차선 박스(회피) / lane1:0.1725 = 옆 차선 박스(clear 인데 넘어가 충돌)
# 출력: eval_out/course/clips/<name>.mp4 (+ frames_<name>/, trial_<name>.log)
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
OUT=$WS/eval_out/course/clips
mkdir -p "$OUT"
if [ "${CLIP_CHILD:-0}" != 1 ]; then
  CLIP_CHILD=1 setsid nohup bash "$0" "$@" > "$OUT/record.log" 2>&1 < /dev/null &
  echo "started (pid $!) — tail -f $OUT/record.log"
  exit 0
fi
export ROS_DOMAIN_ID=${ISO_DOMAIN:-87}
export GZ_PARTITION=${ISO_PARTITION:-clip}
export NAVVLA_SITUATION=0                      # 문구는 하네스(오라클)가 붙인다
ORACLE=${ORACLE:-1}                            # 0 = 문구 없음(모델 스스로)
export CURV_BOOST_SLOW=${CURV_BOOST_SLOW:-1.0}
CKPT=${CKPT:-runs/course/navvla_reasoning_r40/checkpoints/last/pretrained_model}
CLIPS=${CLIPS:-"lane2:avoid lane1:crash"}
# 카메라: 인덱스 70(-15.99,-12.84) 앞 약 15 m ~ 뒤 3 m 를 가로로. 높이 15 m, 수직 하향
CAM_X=${CAM_X:--17.5} CAM_Y=${CAM_Y:--6.5} CAM_Z=${CAM_Z:-15.0}
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

for clip in $CLIPS; do
  IFS=: read -r lane name model frac run <<< "$clip"; model=${model:-ob_box}; frac=${frac:-0.1725}
  CK=$CKPT; [ -n "$run" ] && CK=runs/course/navvla_reasoning_${run}/checkpoints/last/pretrained_model
  CX=$CAM_X CY=$CAM_Y CZ=$CAM_Z
  if [ -n "$run" ]; then
    case $frac in
      0.1725) CX=-17.0 CY=-3.6 CZ=21.0 ;;   # 인덱스 70: 왼쪽 직선, 출발(인덱스 7)~장애물+3 m
      0.35)   CX=-4.5 CY=-21.0 CZ=25.0 ;;   # 인덱스 142: 왼쪽 아래 굽이를 돌아 아래 직선
    esac
  fi
  OR=""; [ "$ORACLE" = 1 ] && OR="--oracle-situation"
  SF=$(python3 -c "print(max(0.0, $frac - 0.155))")
  echo "[clip] $(date +%T) $name ($lane, $model) — 스택 기동"
  REMOTE_CKPT=$CK NAVVLA_RACE=qualifying "$WS/smolvla_demo.sh" --no-gui > "$OUT/bringup_$name.log" 2>&1 \
    || { tail -5 "$OUT/bringup_$name.log"; echo "[clip] BRINGUP_FAIL"; continue; }
  setsid nohup ros2 run ros_gz_bridge parameter_bridge \
    /top_camera@sensor_msgs/msg/Image@gz.msgs.Image --ros-args -r /top_camera:=/top_camera/image_raw \
    > "$OUT/topbridge_$name.log" 2>&1 < /dev/null &
  BR=$!
  CAM_X=$CX CAM_Y=$CY CAM_Z=$CZ python3 - <<'PY'
import math, os
from sant_vla_pkg.gazebo_services import pose_message, request
pose = (float(os.environ["CAM_X"]), float(os.environ["CAM_Y"]), float(os.environ["CAM_Z"]), 0.0, math.pi / 2, 0.0)
print(request("/world/default/set_pose", "gz.msgs.Pose", f'name: "top_camera" {pose_message(pose)}'))
PY
  sleep 4
  rm -rf "$OUT/frames_$name"
  python3 "$WS/tools/eval/record_topic_frames.py" /top_camera/image_raw "$OUT/frames_$name" &
  REC=$!
  sleep 2
  python3 "$WS/tools/eval/avoidance_trial.py" --models "$model" --obstacles "$lane:$frac" \
    --start-frac "$SF" --speed slowly --no-supervisor $OR --timeout 150 \
    > "$OUT/trial_$name.log" 2>&1
  grep -E '"result"|oracle:' "$OUT/trial_$name.log"
  sleep 2
  kill -INT $REC; wait $REC
  kill $BR 2>/dev/null
  pat='parameter_bridge /top_camer'; pkill -f "${pat}a" 2>/dev/null
  FPS=$(cat "$OUT/frames_$name/fps.txt" 2>/dev/null || echo 10)
  ffmpeg -y -loglevel error -framerate "$FPS" -i "$OUT/frames_$name/%05d.jpg" \
    -c:v libx264 -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" "$OUT/$name.mp4" \
    && echo "[clip] $OUT/$name.mp4 ($(ls "$OUT/frames_$name" | grep -c jpg) frames @ ${FPS} fps)"
  "$WS/smolvla_demo.sh" down > /dev/null 2>&1
  sleep 5
done
echo "[clip] ALL_DONE $(date +%T)"

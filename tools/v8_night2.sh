#!/bin/bash
# v8 재수집(클록 수정판) → finalize → 서버 반입 → 변환 → 60K 학습 개시, 전체 체인
WS=/home/sh/ROS2_project/sant-vla
OUT=$WS/eval_out/v8_collect
bash $WS/tools/collect_v8_overnight.sh > "$OUT/collect_run2.log" 2>&1 \
  || { echo NIGHT2_COLLECT_FAIL; exit 1; }
bash $WS/tools/v8_finish_and_train.sh > "$OUT/finish_train2.log" 2>&1 \
  || { echo NIGHT2_FINISH_FAIL; exit 2; }
echo NIGHT2_DONE

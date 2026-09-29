#!/bin/bash
# 홀드아웃 물체 폐루프 회피 평가 — 감독 OFF, 정책 자체 반응만.
#
#   bash tools/eval/multiobj_heldout_eval.sh r29                       # r29 last 체크포인트
#   CKPT=runs/navvla_reasoning_r28/checkpoints/last/pretrained_model \   # 주행 모델(runs/ 직속)은 CKPT 로 지정
#     bash tools/eval/multiobj_heldout_eval.sh r28                     # 베이스라인(다중물체 미학습)
#   MODELS=ob_person,ob_barrel N=2 bash tools/eval/multiobj_heldout_eval.sh r29 quick
#
# 기본: 홀드아웃 3종(사람·드럼통·초록 해치백) + 학습 물체 2종(박스=양성 대조,
# prius=ego 동일) × 지점 2곳(직선 lane2@0.35 / 곡선 lane2@0.45) × N=3 회.
# 결과: eval_out/multiobj_eval/<tag>.jsonl + 요약표. 스택은 smolvla_demo.sh 로
# --no-gui 기동(chat_gui 없음 = 회피 감독 없음), 끝나면 내린다.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS=/home/sh/ROS2_project/sant-vla
TAG=${1:?tag (r29 등)}
CKPT=${CKPT:-runs/course/navvla_reasoning_${TAG%%_*}/checkpoints/last/pretrained_model}
MODELS=${MODELS:-ob_person,ob_barrel,hatchback_green,ob_box,prius_hybrid}
SPOTS=${SPOTS:-lane2:0.35,lane2:0.45}
N=${N:-3}
# 출발은 장애물 24 m 뒤(frac 0.17 ≈ 24 m). avoidance_trial 기본(-0.06 ≈ 8.5 m)은
# 감독 데모용이라 시연 정지선(중심 12 m + 제동거리) 안쪽에서 출발해 버린다 —
# 정책은 첫 프레임부터 "가까운 장애물"만 본다(r28 첫 실행에서 발견, 2026-09-23).
START_OFF=${START_OFF:-0.17}
OUT=$WS/eval_out/course/multiobj_eval
mkdir -p "$OUT" "$OUT/trials"
LOG=$OUT/$TAG.jsonl
source /opt/ros/jazzy/setup.bash
source $WS/install/setup.bash

echo "[eval] 스택 기동 (no-gui, ckpt=$CKPT)"
REMOTE_CKPT=$CKPT NAVVLA_RACE=qualifying "$WS/smolvla_demo.sh" --no-gui > "$OUT/${TAG}_bringup.log" 2>&1 \
  || { tail -20 "$OUT/${TAG}_bringup.log"; echo "[eval] BRINGUP_FAIL"; exit 3; }
grep -q "REMOTE_SERVING" "$WS/eval_out/demo/remote_start.log" || { echo "[eval] 원격 서빙 미확인"; exit 3; }
sleep 5

: > "$LOG"
for model in ${MODELS//,/ }; do
  for spot in ${SPOTS//,/ }; do
    for k in $(seq 1 "$N"); do
      echo "[eval] $(date +%H:%M:%S) $model @ $spot #$k"
      sf=$(python3 -c "print(max(0.0, float('${spot#*:}') - $START_OFF))")
      python3 "$WS/tools/eval/avoidance_trial.py" --models "$model" --obstacles "$spot" \
        --start-frac "$sf" --no-supervisor --timeout 150 > "$OUT/${TAG}_last_trial.log" 2>&1
      cp "$OUT/${TAG}_last_trial.log" "$OUT/trials/${TAG}_${model}_${spot/:/_}_$k.log"
      python3 - "$OUT/${TAG}_last_trial.log" "$model" "$spot" "$k" "$TAG" >> "$LOG" <<'PY'
import json, sys
txt = open(sys.argv[1], encoding="utf-8", errors="replace").read()
i = txt.find("{\n \"result\"")
rep = {}
if i >= 0:
    j = txt.find("\n}\n", i)
    try: rep = json.loads(txt[i:j+2])
    except Exception as e: rep = {"result": "PARSE_FAIL", "detail": str(e)}
else:
    rep = {"result": "NO_REPORT", "detail": txt[-300:]}
ob = (rep.get("obstacles") or [{}])[0]
row = {"tag": sys.argv[5], "model": sys.argv[2], "spot": sys.argv[3], "trial": int(sys.argv[4]),
       "result": rep.get("result"), "detail": rep.get("detail"), "elapsed_s": rep.get("elapsed_s"),
       "min_d": ob.get("min_d"), "lat_at_min": ob.get("lat_at_min")}
print(json.dumps(row, ensure_ascii=False))
print("   ->", row["result"], row.get("detail") or "", "min_d", row.get("min_d"), "lat", row.get("lat_at_min"), file=sys.stderr)
PY
      sleep 3
    done
  done
done

echo; echo "[eval] 요약 ($TAG)"
python3 - "$LOG" <<'PY'
import json, sys, collections
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
tab = collections.defaultdict(list)
for r in rows: tab[(r["model"], r["spot"])].append(r["result"])
print(f"{'model':16s} {'spot':12s} SUCCESS COLLISION STUCK OFF_TRACK TIMEOUT other")
for (m, s), res in tab.items():
    c = collections.Counter(res)
    other = sum(v for k, v in c.items() if k not in ("SUCCESS","COLLISION","STUCK","OFF_TRACK","TIMEOUT"))
    print(f"{m:16s} {s:12s} {c['SUCCESS']:7d} {c['COLLISION']:9d} {c['STUCK']:5d} {c['OFF_TRACK']:9d} {c['TIMEOUT']:7d} {other:5d}")
PY

echo "[eval] 스택 종료"
"$WS/smolvla_demo.sh" down > /dev/null 2>&1
bash "$WS/tools/cleanup_artifacts.sh" | tail -3
echo "[eval] DONE — $LOG"

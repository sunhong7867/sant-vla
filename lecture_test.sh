#!/bin/bash
# 단기강좌 장애물 테스트 — 기존 데모 스택(Driving Studio GUI) 위에서 장애물만 바꿔 띄운다.
#
#   sh lecture_test.sh                         # ego 와 같은 prius_hybrid 2대, 회피 감독 ON
#   sh lecture_test.sh --model ob_person       # 학습에 없던 물체(마네킹)로 교체
#   sh lecture_test.sh --avoidance off         # 감독(VLM 목격→문장 교체) OFF: 정책 자체 반응만
#   sh lecture_test.sh --obstacles lane2:0.25,lane1:0.45 --start-frac 0.15
#   sh lecture_test.sh --ckpt models/ckpt_r30   # 학생 학습 모델로
#   sh lecture_test.sh --scenario-only         # 시나리오 JSON 만 갱신 (스택 안 띄움)
#   sh lecture_test.sh --goto                  # 목표 지점 이동 (2026-10-13): 점 목표 모델 g5d 15k + Qwen2.5-VL 목표 노드, 감독 OFF, 장애물 없이 시작
#                                              #   GUI: [앞에 물체 3개] → "빨간 꼬깔로 가줘" / "공룡으로 가줘" / "상자 오른쪽에 서줘"
#                                              #   Qwen 이 화면에서 물체를 찾고 라이다로 거리를 재서 정책에 방향·거리를 준다. 정차는 코드 게이트.
#   sh lecture_test.sh --goto-smolvla          # 목표 찾기도 SmolVLA 로 (Qwen 없음, L5/L7 위치 층; 학습한 이름·색만)
#   sh lecture_test.sh --goto-sector           # 예전 섹터 모델 s3 (문장 방향 단어 방식)
#                                              #   전방 카메라 클릭 후 WASD = 수동주행, 다른 곳 클릭 = 해제
#   sh lecture_test.sh down                    # 전체 종료
#
# 하는 일:
#   1. race_scenarios.json 에 "lecture" 시나리오를 (재)작성 — ego 출발 위치 + 장애물 N개.
#      GUI 의 경기 선택기에도 "강좌 · 장애물 테스트" 로 나타나고 리셋 버튼으로 재배치된다.
#   2. NAVVLA_RACE=lecture 로 smolvla_demo.sh 를 그대로 실행 (GUI·정책 서버·브리지 전부 기존 것).
#
# 장애물 모델: prius_hybrid(=ego 와 동일 모델·색, 기본) / hatchback_* / ob_box / ob_barrel /
#   ob_cone / ob_barrier / ob_person. --model 에 콤마로 여러 개 주면 장애물 순서대로 배정.
#   race_scenarios.static_model 이 센서·플러그인을 떼고 정적 모델로 스폰한다.
# 위치: lane:frac (frac = 차선 경로상 0..1, 주행 방향 순). ego 는 lane2, 첫 장애물 frac-0.08.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
MODELS=prius_hybrid
OBSTACLES=lane2:0.25,lane1:0.45
START_FRAC=""
START_LANE=lane2
AVOID=on
SCENARIO_ONLY=0
DEMO_ARGS=()

if [ "${1:-}" = "down" ] || [ "${1:-}" = "check" ]; then
  exec "$WS/smolvla_demo.sh" "$1"
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --model|--models) MODELS="$2"; shift 2 ;;
    --obstacles) OBSTACLES="$2"; shift 2 ;;
    --start-frac) START_FRAC="$2"; shift 2 ;;
    --start-lane) START_LANE="$2"; shift 2 ;;
    --avoidance) AVOID="$2"; shift 2 ;;
    --scenario-only) SCENARIO_ONLY=1; shift ;;
    --goto) AVOID=off; OBSTACLES=""; START_FRAC=${START_FRAC:-0.1}
            # g5d 평가(goto_stat_eval.sh)와 같은 서빙 설정: 차선 보정 0
            export REMOTE_CKPT=${REMOTE_CKPT:-runs/course/navvla_reasoning_g5d/checkpoints/015000/pretrained_model}
            # g5d 는 해설 헤드를 학습하지 않았다(ce 0) → 해설이 'numerable…' 반복이 되므로 끈다
            export NAVVLA_POINT_GOAL=1 XTRACK_GAIN=${XTRACK_GAIN:-0.0} POLICY_GUIDE=${POLICY_GUIDE:-1.0} NAVVLA_REASONING_EVERY=${NAVVLA_REASONING_EVERY:-0}; shift ;;
    --goto-smolvla) AVOID=off; OBSTACLES=""; START_FRAC=${START_FRAC:-0.1}
            # 2026-10-13 L5: 목표 찾기도 SmolVLA(얼린 VLM + 위치 층, Qwen 없음). 학습한 이름만, 나머지는 되묻기
            export REMOTE_CKPT=${REMOTE_CKPT:-runs/course/navvla_reasoning_g5d/checkpoints/015000/pretrained_model}
            # 2026-10-14 L7: 색 문장("파란색 물체")도 학습한 위치 층. 학습한 색-물체 조합만(다른 물체로 일반화 0 %)
            export NAVVLA_L5_HEAD=${NAVVLA_L5_HEAD:-head_color_all.pt}
            export NAVVLA_POINT_GOAL=1 NAVVLA_PERCEIVER=smolvla XTRACK_GAIN=${XTRACK_GAIN:-0.0} POLICY_GUIDE=${POLICY_GUIDE:-1.0} NAVVLA_REASONING_EVERY=${NAVVLA_REASONING_EVERY:-0}; shift ;;
    --goto-sector) AVOID=off; OBSTACLES=""; START_FRAC=${START_FRAC:-0.1}
            export REMOTE_CKPT=${REMOTE_CKPT:-runs/course/navvla_reasoning_s3/checkpoints/015000/pretrained_model}; shift ;;
    --ckpt) DEMO_ARGS+=(--ckpt "$2"); shift 2 ;;
    --no-gui|--legacy-gui) DEMO_ARGS+=("$1"); shift ;;
    -h|--help) sed -n 2,25p "$0"; exit 0 ;;
    *) echo "[lecture] 알 수 없는 인자: $1"; exit 2 ;;
  esac
done
case "$AVOID" in on|off) ;; *) echo "[lecture] --avoidance 는 on|off"; exit 2 ;; esac

for m in ${MODELS//,/ }; do
  [ -f "$WS/src/simulation_pkg/models/$m/model.sdf" ] || { echo "[lecture] 모델 없음: $m"; exit 2; }
done

echo "[lecture] 시나리오 작성: models=$MODELS obstacles=$OBSTACLES ego=$START_LANE@${START_FRAC:-auto} avoidance=$AVOID"
MODELS="$MODELS" OBSTACLES="$OBSTACLES" START_FRAC="$START_FRAC" START_LANE="$START_LANE" \
python3 - "$WS" <<'PY' || exit 3
import json, math, os, sys
ws = sys.argv[1]
cfg = os.path.join(ws, "src/sant_vla_pkg/config")
paths = json.load(open(os.path.join(cfg, "track_paths.json")))
scen_path = os.path.join(cfg, "race_scenarios.json")
scenarios = json.load(open(scen_path))
Z = 0.01265

def lane_pose(lane, frac):
    pts = paths[lane]
    i = max(0, min(len(pts) - 1, int(frac * len(pts))))
    x, y = pts[i]
    nx, ny = pts[(i + 1) % len(pts)]
    return x, y, math.atan2(ny - y, nx - x)

def body_yaw(model, travel):
    # prius 메시는 차체 yaw 가 주행 방향 +90° (ego 텔레포트와 같은 규약);
    # 해치백·프리미티브는 collect_corpus 의 teleport 규약대로 주행 방향 그대로.
    return travel + math.pi / 2 if model.startswith("prius") else travel

models = [m for m in os.environ["MODELS"].split(",") if m]
specs = [p for p in os.environ["OBSTACLES"].split(",") if p]
entities = []
for i, spec in enumerate(specs):
    lane, frac = spec.split(":")
    model = models[i % len(models)]
    x, y, tr = lane_pose(lane, float(frac))
    # kind 는 모델과 무관하게 "vehicle": 감독의 좌표 백스톱(obstacles.json)이
    # vehicle 만 등록하므로, 사람·박스도 어느 차선에 있는지 알 수 있어야 한다.
    entities.append({"entity": f"obstacle{i+1}", "model": model,
                     "pose": [round(x, 4), round(y, 4), Z, 0.0, 0.0, round(body_yaw(model, tr), 6)],
                     "kind": "vehicle", "lane_hint": lane, "frac": float(frac)})
start_lane = os.environ["START_LANE"]
sf = os.environ["START_FRAC"]
start_frac = float(sf) if sf else (max(0.0, min(float(s.split(":")[1]) for s in specs) - 0.08) if specs else 0.1)
ex, ey, etr = lane_pose(start_lane, start_frac)
scenarios["lecture"] = {
    "label": "강좌 · 장애물 테스트",
    "description": f"{start_lane}@{start_frac:.2f} 출발 · 장애물 {len(entities)}개 ({','.join(models)})",
    "source": "lecture_test.sh",
    "ego_pose": [round(ex, 4), round(ey, 4), Z, 0.0, 0.0, round(etr + math.pi / 2, 6)],
    "lane": start_lane,
    "entities": entities,
}
tmp = scen_path + ".tmp"
with open(tmp, "w") as f:
    json.dump(scenarios, f, ensure_ascii=False, indent=2)
os.replace(tmp, scen_path)
print(f"[lecture] ego ({ex:.2f},{ey:.2f}) {start_lane}@{start_frac:.2f}")
for e in entities:
    print(f"[lecture] {e['entity']}: {e['model']} {e['lane_hint']}@{e['frac']:.2f} at ({e['pose'][0]:.2f},{e['pose'][1]:.2f})")
PY

# install 된 config 를 읽는 경로가 있을 수 있어(ament share) 사본도 갱신
INST="$WS/install/sant_vla_pkg/share/sant_vla_pkg/config/race_scenarios.json"
[ -f "$INST" ] && [ ! -L "$INST" ] && cp "$WS/src/sant_vla_pkg/config/race_scenarios.json" "$INST"

[ "$SCENARIO_ONLY" = 1 ] && { echo "[lecture] 시나리오만 갱신함 (GUI 경기 선택기: 강좌 · 장애물 테스트)"; exit 0; }

GUI_ARGS="-p lecture_mode:=true -p avoid_enable:=$([ "$AVOID" = on ] && echo true || echo false)"
echo "[lecture] 데모 스택 기동 (NAVVLA_RACE=lecture, chat_gui: $GUI_ARGS)"
NAVVLA_RACE=lecture NAVVLA_GUI_ARGS="$GUI_ARGS" exec "$WS/smolvla_demo.sh" "${DEMO_ARGS[@]}"

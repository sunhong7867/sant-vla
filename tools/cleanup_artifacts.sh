#!/bin/bash
# 실행 잔여물 정리 — 수집·평가·학습 스크립트가 끝날 때마다 자동 호출된다.
#
#   bash tools/cleanup_artifacts.sh            # 안전 등급만 (기본, 자동 호출용)
#   bash tools/cleanup_artifacts.sh --server   # + 서버(완료 런의 중간 체크포인트·스테이징)
#   bash tools/cleanup_artifacts.sh --sessions # + 로컬 30 Hz 원본 세션 (packed 가 있는 것만)
#   bash tools/cleanup_artifacts.sh --all --dry-run
#
# 등급을 나눈 이유: 캐시·로그는 언제 지워도 재생성되지만, `session_*` 는 30 Hz
# 원본이라 packed(10 Hz)로 다시 만들 수 없다. 그래서 --sessions 는 명시 요청일 때만.
# 학습 중인 런(runs/*/checkpoints/last 없음)은 어느 등급에서도 건드리지 않는다.
[ -n "${BASH_VERSION:-}" ] || exec bash "$0" "$@"
WS="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
SRV=${VLA_SRV:-autolab_sw@115.145.211.157}
DO_SERVER=0; DO_SESSIONS=0; DRY=0
KEEP_SCENE=${KEEP_SCENE:-3}      # 최근 데모 해설 로그 세션 보존 개수
KEEP_TRIALS=${KEEP_TRIALS:-40}   # 최근 폐루프 트라이얼 로그 보존 개수

while [ $# -gt 0 ]; do
  case "$1" in
    --server)   DO_SERVER=1; shift ;;
    --sessions) DO_SESSIONS=1; shift ;;
    --all)      DO_SERVER=1; DO_SESSIONS=1; shift ;;
    --dry-run|-n) DRY=1; shift ;;
    -h|--help)  sed -n 2,14p "$0"; exit 0 ;;
    *) echo "[cleanup] 알 수 없는 인자: $1"; exit 2 ;;
  esac
done

freed=0
say() { echo "[cleanup] $*"; }
# 지우기 전 크기를 재서 합산한다 (dry-run 이면 크기만 보고).
drop() {  # $1=경로 $2=설명
  [ -e "$1" ] || return 0
  local kb; kb=$(du -sk "$1" 2>/dev/null | cut -f1); [ -n "$kb" ] || return 0
  freed=$((freed + kb))
  if [ "$DRY" = 1 ]; then
    [ "${QUIET:-0}" = 1 ] || printf '  [dry] %8.1f MB  %s (%s)\n' "$(echo "$kb" | awk '{print $1/1024}')" "$1" "$2"
  else
    rm -rf "$1"
    [ "${QUIET:-0}" = 1 ] || printf '  %8.1f MB  %s (%s)\n' "$(echo "$kb" | awk '{print $1/1024}')" "$1" "$2"
  fi
}

say "안전 등급 정리 (로컬)"
# gz 시뮬 로그 — 매 기동마다 새로 쌓인다. 스크립트들이 이미 지우지만 중단 시 남음.
drop "$HOME/.gz/sim/log" "gz 시뮬 로그"
# 런치가 만드는 런타임 월드 사본
for f in /tmp/simulation_pkg_runtime_*.world /tmp/simulation_pkg_runtime_gui*.config; do
  drop "$f" "런타임 월드 사본"
done
# 수집·평가가 만든 정적 모델 SDF 캐시 (다음 실행에서 다시 생성)
drop "$WS/eval_out/demo/scene_models" "정적 모델 SDF 캐시"
# 파이썬 캐시
while read -r d; do drop "$d" "pycache"; done < <(find "$WS/src" "$WS/tools" "$WS/server" -name "__pycache__" -type d -prune 2>/dev/null)
# 데모 해설 로그 세션 — 최근 $KEEP_SCENE 개만 남긴다 (프레임 PNG 가 쌓인다)
while read -r d; do drop "$d" "옛 해설 로그"; done < <(ls -dt "$WS/src/sant_vla_pkg/logs/scene_reasoning"/session_* 2>/dev/null | tail -n +$((KEEP_SCENE + 1)))
# 폐루프 트라이얼 개별 로그 — 요약 jsonl 은 남기고 원본 로그만 최근 것만
while read -r f; do drop "$f" "옛 트라이얼 로그"; done < <(ls -t "$WS/eval_out/course/multiobj_eval/trials"/*.log 2>/dev/null | tail -n +$((KEEP_TRIALS + 1)))
# ROS 로그 (ros2 launch 가 ~/.ros/log 에 쌓는다)
QUIET=1; while read -r d; do drop "$d" "ROS 런치 로그"; done < <(ls -dt "$HOME/.ros/log"/* 2>/dev/null | tail -n +6); QUIET=0

if [ "$DO_SESSIONS" = 1 ]; then
  say "30 Hz 원본 세션 (packed 가 존재하는 것만)"
  for S in "$WS/src/sant_vla_pkg/data_course_multiobj"/session_* \
           "$WS/src/sant_vla_pkg"/data_*/session_*; do
    [ -d "$S" ] || continue
    base=$(basename "$S")
    # 이 세션에서 나온 packed 에피소드가 하나라도 있어야 지운다
    if ls -d "$(dirname "$S")"/packed_*/"${base}__ep_"* >/dev/null 2>&1; then
      drop "$S" "packed 있음 → 원본 불필요"
    else
      say "  보존: $base (대응 packed 없음)"
    fi
  done
fi

if [ "$DO_SERVER" = 1 ]; then
  say "서버 정리 ($SRV)"
  ssh -o ConnectTimeout=10 "$SRV" "DRY=$DRY bash -s" <<'REMOTE'
cd ~/sunhong/nav-vla || exit 1
freed=0
drop() {
  [ -e "$1" ] || return 0
  kb=$(du -sk "$1" 2>/dev/null | cut -f1); [ -n "$kb" ] || return 0
  freed=$((freed + kb))
  if [ "$DRY" = 1 ]; then printf '  [dry] %6s MB  %s (%s)\n' "$((kb/1024))" "$1" "$2"
  else rm -rf "$1"; printf '  %6s MB  %s (%s)\n' "$((kb/1024))" "$1" "$2"; fi
}
# 스테이징 심볼릭 디렉터리 — convert 스크립트가 매번 다시 만든다
for d in $(ls -d data/packed_v*_staging data/course/packed_v*_staging 2>/dev/null | sort -u); do drop "$d" "변환 스테이징"; done
# 완료된 런의 중간 체크포인트: last 가 가리키는 것만 남긴다.
# 학습 중인 런은 last 심볼릭이 아직 없거나 로그가 갱신 중 → 건드리지 않는다.
for r in runs/*/ runs/course/*/; do
  [ -d "$r/checkpoints" ] || continue
  keep=$(readlink "$r/checkpoints/last" 2>/dev/null)
  [ -n "$keep" ] || { echo "  건너뜀: $r (last 없음 = 학습 중일 수 있음)"; continue; }
  log="logs/$(basename "$r").log"; [ -f "$log" ] || log="logs/course/$(basename "$r").log"
  if [ -f "$log" ] && ! grep -q "done in" "$log" 2>/dev/null; then
    echo "  건너뜀: $r (로그에 done 없음 = 학습 중)"; continue
  fi
  for c in "$r/checkpoints"/*/; do
    n=$(basename "$c")
    [ "$n" = "$keep" ] || [ "$n" = "last" ] || drop "$c" "중간 체크포인트 (last=$keep 보존)"
  done
done
# ollama 서빙 로그가 GB 단위로 자란다 — 비운다(파일은 유지)
for f in logs/ollama_serve.log logs/vla_serve_remote.log; do
  [ -f "$f" ] || continue
  kb=$(du -sk "$f" | cut -f1)
  [ "$kb" -gt 51200 ] && { freed=$((freed+kb)); [ "$DRY" = 1 ] || : > "$f"; printf '  %6s MB  %s (truncate)\n' "$((kb/1024))" "$f"; }
done
echo "[cleanup] 서버 회수: $((freed/1024)) MB"
df -h ~ | tail -1
REMOTE
fi

say "로컬 회수: $(awk -v k="$freed" 'BEGIN{printf "%.1f", k/1024}') MB"
df -h / | tail -1

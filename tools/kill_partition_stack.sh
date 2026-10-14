#!/bin/bash
# 같은 격리 파티션(GZ_PARTITION) / 도메인(ROS_DOMAIN_ID)의 시뮬 스택만 정리 (2026-10-03).
# 다른 세션이 다른 도메인으로 띄운 gz 를 같이 죽이지 않기 위해: 프로세스 환경변수를 보고 고른다.
#   GZ_PARTITION=div ROS_DOMAIN_ID=87 bash tools/kill_partition_stack.sh [-9] [pgrep 패턴(브래킷 형식)]
SIG=${1:--15}
PAT=${2:-'gz si[m]|driving_sim.launc[h]|route_oracle_nod[e]|episode_recorde[r]|collect_corpu[s].py|parameter_bridg[e]|ros_gz_brid[g]e'}
mine() {  # $1=pid → 0 이면 우리 파티션
  local env; env=$(tr '\0' '\n' < /proc/$1/environ 2>/dev/null) || return 1
  { [ -n "$GZ_PARTITION" ] && grep -qx "GZ_PARTITION=$GZ_PARTITION" <<< "$env"; } && return 0
  { [ -n "$ROS_DOMAIN_ID" ] && grep -qx "ROS_DOMAIN_ID=$ROS_DOMAIN_ID" <<< "$env"; } && return 0
  return 1
}
n=0
for pid in $(pgrep -f "$PAT"); do
  [ "$pid" = "$$" ] && continue
  mine "$pid" && { kill "$SIG" "$pid" 2>/dev/null && n=$((n + 1)); }
done
echo "[kill_partition_stack] partition=${GZ_PARTITION:-?} domain=${ROS_DOMAIN_ID:-?} signalled $n"

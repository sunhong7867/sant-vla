#!/bin/bash
# 프로브 스택 정리(파일 스크립트 — pkill 자기매치 방지). 시뮬까지 내린다.
p='gz si'; pkill -9 -f "${p}m" 2>/dev/null
p='driving_sim.launc'; pkill -f "${p}h" 2>/dev/null
p='vla_policy_serve'; pkill -f "${p}r" 2>/dev/null
p='vla_bridge_nod'; pkill -f "${p}e" 2>/dev/null
p='parameter_bridg'; pkill -f "${p}e" 2>/dev/null
for _ in $(seq 1 10); do
  pgrep -f "gz si[m]|vla_bridge_nod[e]|vla_policy_serve[r]" >/dev/null || break
  sleep 1
done
rm -rf ~/.gz/sim/log
echo TEARDOWN_OK

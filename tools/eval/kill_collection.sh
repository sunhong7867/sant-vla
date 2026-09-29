#!/bin/bash
# 수집 스택 전체 종료 (파일 스크립트: pkill 자기매치 방지).
# collect_corpus → recorder → oracle → gz 순으로 내리고 리핑을 기다린다.
p='collect_corpu';       pkill -f "${p}s.py"     2>/dev/null
p='collect_multiobj_avoi'; pkill -f "${p}d.sh"   2>/dev/null
p='episode_recorde';     pkill -f "${p}r"        2>/dev/null
p='route_oracle_nod';    pkill -f "${p}e"        2>/dev/null
p='gz si';               pkill -9 -f "${p}m"     2>/dev/null
p='driving_sim.launc';   pkill -f "${p}h"        2>/dev/null
p='ackermann_cmd_adapte'; pkill -f "${p}r"       2>/dev/null
p='clock_throttl';       pkill -f "${p}e"        2>/dev/null
p='parameter_bridg';     pkill -f "${p}e"        2>/dev/null
for _ in $(seq 1 12); do
  pgrep -f "collect_corpu[s]|episode_recorde[r]|route_oracle_nod[e]|gz si[m]|driving_sim.launc[h]|clock_throttl[e]|ackermann_cmd_adapte[r]" >/dev/null || break
  sleep 1
done
rm -rf ~/.gz/sim/log
for q in 'collect_corpu[s]' 'episode_recorde[r]' 'route_oracle_nod[e]' 'gz si[m]'; do
  printf '%-22s %s\n' "$q" "$(pgrep -c -f "$q")"
done
echo COLLECTION_KILLED

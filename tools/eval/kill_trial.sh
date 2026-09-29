#!/bin/bash
# avoidance_trial.py 프로세스만 종료 (파일 스크립트: pkill 자기매치 방지)
p='avoidance_tria'; pkill -f "${p}l.py" 2>/dev/null
for _ in $(seq 1 5); do pgrep -f "avoidance_tria[l].py" >/dev/null || break; sleep 1; done
echo "trial procs: $(pgrep -c -f 'avoidance_tria[l].py')"

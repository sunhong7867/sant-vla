#!/bin/bash
# Invoked over SSH on the configured lab host. Arguments are shell-quoted by caller.
set -euo pipefail
cd "$HOME/sunhong/nav-vla"
CKPT=$1
REASONING_EVERY=${2:-4}
test -f "$CKPT/model.safetensors" || { echo "모델 파일 없음: $CKPT/model.safetensors"; exit 2; }
test -f "$CKPT/config.json" || { echo "모델 설정 없음: $CKPT/config.json"; exit 2; }
mkdir -p logs
LOG=logs/vla_serve_remote.log
PID_FILE=logs/driving_studio_policy.pid
if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && [ -r "/proc/$OLD_PID/cmdline" ] &&
     tr '\0' ' ' < "/proc/$OLD_PID/cmdline" | grep -q 'code/vla_policy_server.py'; then
    kill "$OLD_PID" 2>/dev/null || true
    for _ in $(seq 1 20); do kill -0 "$OLD_PID" 2>/dev/null || break; sleep 0.2; done
  fi
fi
setsid nohup env CUDA_VISIBLE_DEVICES=0 ./venv/bin/python -u code/vla_policy_server.py \
  --checkpoint "$CKPT" --endpoint tcp://127.0.0.1:5555 --warmup 4 \
  --reasoning-every "$REASONING_EVERY" > "$LOG" 2>&1 < /dev/null &
POLICY_PID=$!
echo "$POLICY_PID" > "$PID_FILE"
for _ in $(seq 1 90); do
  if grep -q 'serving on' "$LOG"; then
    ./venv/bin/python - "$CKPT" <<'PY'
import json,sys
from pathlib import Path
config=json.loads((Path(sys.argv[1])/'config.json').read_text())
print('STATE_DIM='+str(config['input_features']['observation.state']['shape'][0]))
PY
    echo REMOTE_SERVING
    exit 0
  fi
  if ! kill -0 "$POLICY_PID" 2>/dev/null; then tail -25 "$LOG"; exit 3; fi
  sleep 1
done
echo '정책 서버 준비 시간 초과'
tail -25 "$LOG"
kill "$POLICY_PID" 2>/dev/null || true
exit 4

#!/bin/bash
# v3g = packed_v3 + packed_v3y (차선 2 x 속도 3 x 의도 2 격자) -> 조합 일반화 홀드아웃.
# 2026-10-09. 두 데이터셋을 만든다:
#   v3g_full = 전부 (천장 c0)
#   v3g_hold = ring_goal x lane2 x fast 제외 (c1 / cn)
# 기존 convert_*.sh 의 link_all 은 reasoning.jsonl 을 요구하는데 packed_v3 는 0/229 라
# 조용히 0 기여한다(10-08 g4 무효의 원인). 여기서는 그 요구를 빼고, 0 기여면 중단한다.
# 해설 헤드는 쓰지 않으므로 빈 reasoning_labels.jsonl + --ce-weight 0 으로 학습한다.
set -e
cd ~/sunhong/nav-vla
S=data/course/packed_v3g_staging
rm -rf "$S" data/course/lerobot/v3g_full data/course/lerobot/v3g_hold
mkdir -p "$S"
python3 - "$S" <<'PY'
import os, sys
dst = sys.argv[1]
tot = 0
for src in ("data/course/packed_v3", "data/course/packed_v3y"):
    if not os.path.isdir(src):
        raise SystemExit(f"CONVERT_ABORT: {src} 없음")
    n = 0
    for name in sorted(os.listdir(src)):
        d = os.path.join(src, name)
        if not os.path.isdir(d):
            continue
        if not (os.path.exists(os.path.join(d, "meta.json"))
                and os.path.exists(os.path.join(d, "resampled_10hz.jsonl"))):
            continue
        link = os.path.join(dst, name)
        if os.path.exists(link):
            raise SystemExit(f"CONVERT_ABORT: 이름 충돌 {name}")
        os.symlink(os.path.abspath(d), link)
        n += 1
    print(f"  {src} -> {n}")
    if n == 0:
        raise SystemExit(f"CONVERT_ABORT: {src} 가 0 기여")
    tot += n
print(f"  staging total {tot}")
PY
HOLD="--exclude-slot intent_id=ring_goal --exclude-slot lane=lane2 --exclude-slot speed_level=fast"
for v in full hold; do
  ex=""; [ "$v" = hold ] && ex="$HOLD"
  echo "=== v3g_$v ==="
  ./venv/bin/python code/to_lerobot.py "$S" \
    --repo-id "navvla/v3g_$v" --out "data/course/lerobot/v3g_$v" \
    --standstill-state --standstill-cap 3.5 $ex
  : > "data/course/lerobot/v3g_$v/reasoning_labels.jsonl"   # 해설 라벨 없음 -> --ce-weight 0
  du -sh "data/course/lerobot/v3g_$v"
done
df -h /home/autolab_sw/sunhong | tail -1
echo CONVERT_V3G_OK

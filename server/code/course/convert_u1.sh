#!/bin/bash
# u1 = packed_v3 + packed_v3y (c0 와 같은 차선 x 속도 x 의도 격자, 홀드아웃 없음) + packed_mrun (다장애물 주행)
#      + packed_mrunc (짧은 간격 연속 회피 보충).
# 2026-10-12. ③ 회피를 ①②(차선 주행·문장 차선 선택)에 붙여 학습 — c0 가 "회피만 빠진 대조군".
# v3/v3y 는 reasoning.jsonl 이 없다(0/229) -> 사이드카는 mrun 에피소드만 채운다(obstacle-boost 용, --ce-weight 0).
set -e
cd ~/sunhong/nav-vla
OUT=${OUT:-u1}
S=data/course/packed_${OUT}_staging
rm -rf "$S" "data/course/lerobot/$OUT"
mkdir -p "$S"
python3 - "$S" <<'PY'
import os, sys
dst = sys.argv[1]
tot = 0
for src, need_reason in (("data/course/packed_v3", False), ("data/course/packed_v3y", False),
                         ("data/course/packed_mrun", True), ("data/course/packed_mrunc", True)):
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
        if need_reason and not os.path.exists(os.path.join(d, "reasoning.jsonl")):
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
./venv/bin/python code/to_lerobot.py "$S" --repo-id "navvla/$OUT" --out "data/course/lerobot/$OUT" \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py "data/course/lerobot/$OUT" "$S" 2>&1 | grep -v 'no reasoning.jsonl'
rm -rf ~/.cache/huggingface/datasets/parquet   # 변환 캐시 (재생성 가능)
du -sh "data/course/lerobot/$OUT"
df -h /home/autolab_sw/sunhong | tail -1
echo CONVERT_U1_OK

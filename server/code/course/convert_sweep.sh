#!/bin/bash
# 박스 회피 시연 수 스윕 코퍼스 (2026-10-01). sw<N> = Stanley 순항 + packed_div 의 v0·v2(물체 7종, v1 전부 제외)
# + packed_boxv1* 의 박스 v1 중 N 개. N 개는 시드 고정 셔플의 앞 N 개라 5 ⊂ 10 ⊂ 20 ⊂ 40 ⊂ 80 (중첩).
# 다른 물체 v1 을 빼서 "회피" 를 가르치는 시연은 박스 N 개뿐이다.
#   bash code/course/convert_sweep.sh 80
set -e
N=${1:?N}
cd ~/sunhong/nav-vla
S=data/course/packed_sw${N}_staging
rm -rf "$S" data/course/lerobot/sw${N}
mkdir -p "$S"
N=$N S=$S python3 - <<'PY'
import json, os, random
N, dst = int(os.environ["N"]), os.environ["S"]
def link(d):
    os.symlink(os.path.abspath(d), os.path.join(dst, os.path.basename(d)))
n = 0
for name in sorted(os.listdir("data/packed_stanley")):
    d = os.path.join("data/packed_stanley", name)
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
        link(d); n += 1
print("stanley", n)
n = 0
for l in open("data/course/packed_div/index.jsonl"):
    r = json.loads(l)
    d = os.path.join("data/course/packed_div", r["episode"])
    if r["cf_variant_id"] in ("v0", "v2") and os.path.exists(os.path.join(d, "reasoning.jsonl")):
        link(d); n += 1
print("div v0/v2", n)
box = []
for idx in ("data/course/packed_boxv1/index.jsonl", "data/course/packed_boxv1b/index.jsonl"):
    if not os.path.exists(idx):
        continue
    for l in open(idx):
        r = json.loads(l)
        d = os.path.join(os.path.dirname(idx), r["episode"])
        if r["cf_variant_id"] == "v1" and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            box.append(d)
box.sort()
random.Random(20261001).shuffle(box)
if len(box) < N:
    raise SystemExit(f"box v1 {len(box)} < {N}")
for d in box[:N]:
    link(d)
print("box v1", N, "of", len(box))
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id navvla/sw${N} --out data/course/lerobot/sw${N} \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/sw${N} "$S"
echo CONVERT_SW${N}_OK

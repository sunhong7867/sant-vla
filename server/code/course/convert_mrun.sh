#!/bin/bash
# 다장애물 주행 스윕용 변환 (2026-10-02): Stanley 순항 109 + packed_mrun 의 앞 N 바퀴(그룹 id 순).
#   N=40 OUT=m40 bash code/course/convert_mrun.sh   → data/course/lerobot/m40
# 옛 박스 짝 데이터는 넣지 않는다 — "바퀴 수만" 바꾼 스윕.
set -e
cd ~/sunhong/nav-vla
N=${N:?N=40}; OUT=${OUT:?OUT=m40}; SRC=${SRC:-data/course/packed_mrun}
S=data/course/packed_${OUT}_staging
rm -rf "$S" "data/course/lerobot/$OUT"
mkdir -p "$S"
S=$S N=$N SRC=$SRC python3 - <<'PY'
import collections, json, os
dst, n_keep, src = os.environ["S"], int(os.environ["N"]), os.environ["SRC"]
def link(d):
    os.symlink(os.path.abspath(d), os.path.join(dst, os.path.basename(d)))
n = 0
for name in sorted(os.listdir("data/packed_stanley")):
    d = os.path.join("data/packed_stanley", name)
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
        link(d); n += 1
print("stanley", n)
rows = [json.loads(l) for l in open(os.path.join(src, "index.jsonl"))]
groups = sorted({r["cf_group_id"] for r in rows})[:n_keep]
c = collections.Counter()
for r in rows:
    d = os.path.join(src, r["episode"])
    if r["cf_group_id"] in groups and os.path.exists(os.path.join(d, "reasoning.jsonl")):
        link(d); c[r["intent_slots"]["lane"]] += 1
        for o in r["intent_slots"].get("obstacles") or []:
            c["ours" if o["in_our_lane"] else "other"] += 1
print(src, "groups", len(groups), dict(c))
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id "navvla/$OUT" --out "data/course/lerobot/$OUT" \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py "data/course/lerobot/$OUT" "$S"
rm -rf ~/.cache/huggingface/datasets/parquet   # 변환 캐시 (재생성 가능)
echo CONVERT_MRUN_OK

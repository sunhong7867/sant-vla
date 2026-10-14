#!/bin/bash
# 점 목표 원시 동작 변환 (2026-10-12, docs/experiments/goto_object/20261012_1850_point-goal-primitive-prereg.md).
# go-to-object 코퍼스만 (Stanley 순항 없음) → state 6 = [v, w, steer, goal_bearing, goal_dist, standstill].
#   OUT=g5d SRCS='data/course/packed_gv2b data/course/packed_sec data/course/packed_sec1 data/course/packed_sec2' \
#     bash code/course/convert_g5d.sh      → data/course/lerobot/g5d
set -e
cd ~/sunhong/nav-vla
OUT=${OUT:-g5d}
SRCS=${SRCS:-"data/course/packed_gv2b data/course/packed_sec data/course/packed_sec1 data/course/packed_sec2"}
S=data/course/packed_${OUT}_staging
rm -rf "$S" "data/course/lerobot/$OUT"
mkdir -p "$S"
S=$S SRCS="$SRCS" python3 - <<'PY'
import collections, json, os
dst = os.environ["S"]
def link(d):
    os.symlink(os.path.abspath(d), os.path.join(dst, os.path.basename(d)))
empty, total = [], 0
for src in os.environ["SRCS"].split():
    c = collections.Counter()
    if not os.path.exists(os.path.join(src, "index.jsonl")):
        print(src, "없음"); empty.append(src + " (index.jsonl 없음)"); continue
    n_ep = n_lab = n_goal = 0
    for l in open(os.path.join(src, "index.jsonl")):
        r = json.loads(l)
        d = os.path.join(src, r["episode"])
        n_ep += 1
        g = (r["intent_slots"].get("goto") or {})
        if g.get("target") is None or not g.get("objects"):
            continue                      # no point goal -> cannot label, skip
        n_goal += 1
        if os.path.exists(os.path.join(d, "reasoning.jsonl")):
            link(d); n_lab += 1; c[g.get("mode", "?")] += 1
    total += n_lab
    print(f"{src}: {n_lab}/{n_ep} 연결 (점 목표 {n_goal}) {dict(c)}")
    if n_lab == 0:
        empty.append(f"{src} ({n_ep} 에피소드 중 0개 — label_reasoning.py 를 먼저 돌려야 한다)")
if empty:
    raise SystemExit("CONVERT_ABORT: 기여 0인 소스: " + "; ".join(empty))
print("STAGED", total)
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id "navvla/$OUT" --out "data/course/lerobot/$OUT" \
  --goal-from-goto --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py "data/course/lerobot/$OUT" "$S"
rm -rf ~/.cache/huggingface/datasets/parquet
grep -o '"observation.state"[^}]*}' "data/course/lerobot/$OUT/meta/info.json" | head -c 300; echo
echo CONVERT_G5D_OK

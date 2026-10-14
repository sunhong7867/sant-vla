#!/bin/bash
# 말로 지정한 물체로 가기 변환 (2026-10-03): Stanley 순항 109(일반 주행 유지) + packed_goto(+ 시범 gpilot).
#   OUT=g1 bash code/course/convert_goto.sh   → data/course/lerobot/g1
set -e
cd ~/sunhong/nav-vla
OUT=${OUT:-g1}; SRCS=${SRCS:-"data/course/packed_goto data/course/packed_gpilot"}
S=data/course/packed_${OUT}_staging
rm -rf "$S" "data/course/lerobot/$OUT"
mkdir -p "$S"
S=$S SRCS="$SRCS" python3 - <<'PY'
import collections, json, os
dst = os.environ["S"]
def link(d):
    os.symlink(os.path.abspath(d), os.path.join(dst, os.path.basename(d)))
n = 0
for name in sorted(os.listdir("data/packed_stanley")):
    d = os.path.join("data/packed_stanley", name)
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "reasoning.jsonl")):
        link(d); n += 1
print("stanley", n)
# 2026-10-08: a source that contributes ZERO episodes used to print "{}" and
# let the conversion finish OK. packed_sec had no reasoning.jsonl (the labeller
# was never run on the sector corpus), so g4 silently became the 109 Stanley
# cruise episodes only — and s1/s0 were trained on it for 2 h and compared as
# if they had seen sector data. Fail loudly instead.
empty = []
for src in os.environ["SRCS"].split():
    c = collections.Counter()
    if not os.path.exists(os.path.join(src, "index.jsonl")):
        print(src, "없음"); empty.append(src + " (index.jsonl 없음)"); continue
    n_ep = n_lab = 0
    for l in open(os.path.join(src, "index.jsonl")):
        r = json.loads(l)
        d = os.path.join(src, r["episode"])
        n_ep += 1
        if os.path.exists(os.path.join(d, "reasoning.jsonl")):
            link(d); n_lab += 1
            c[(r["intent_slots"].get("goto") or {}).get("mode", "?")] += 1
    print(f"{src}: {n_lab}/{n_ep} 에피소드 연결 {dict(c)}")
    if n_lab == 0:
        empty.append(f"{src} ({n_ep} 에피소드 중 0개 — label_reasoning.py 를 먼저 돌려야 한다)")
if empty:
    raise SystemExit("CONVERT_ABORT: 기여 0인 소스: " + "; ".join(empty))
PY
# EXTRA_TOLEROBOT (2026-10-08): 섹터 코퍼스는 --sector-per-frame 이 필요하다
./venv/bin/python code/to_lerobot.py "$S" --repo-id "navvla/$OUT" --out "data/course/lerobot/$OUT" \
  --standstill-state --standstill-cap 3.5 ${EXTRA_TOLEROBOT:-}
./venv/bin/python code/build_reasoning_sidecar.py "data/course/lerobot/$OUT" "$S"
rm -rf ~/.cache/huggingface/datasets/parquet
echo CONVERT_GOTO_OK

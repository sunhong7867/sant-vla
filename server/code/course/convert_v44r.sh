#!/bin/bash
# v44r (2026-10-02) = v43r + packed_boxv1(박스 v1 109, 짝 없음). 회피 128 : 옆 차선 직진 77 : 빈 차선 70 —
# 사용자 지적: r43 은 회피 19 vs 직진 256 으로 너무 적어 꺾지 않았다. 반반에 가깝게.

set -e
cd ~/sunhong/nav-vla
S=data/course/packed_v44r_staging
rm -rf "$S" data/course/lerobot/v44r
mkdir -p "$S"
S=$S python3 - <<'PY'
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
for src, keep in (("data/course/packed_div", ("v0", "v2")), ("data/course/packed_boxtri", ("v0", "v1", "v2")),
                  ("data/course/packed_boxv1", ("v1",))):
    c = collections.Counter()
    for l in open(os.path.join(src, "index.jsonl")):
        r = json.loads(l)
        d = os.path.join(src, r["episode"])
        if r["cf_variant_id"] in keep and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            link(d); c[r["cf_variant_id"]] += 1
    print(src, dict(c))
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id navvla/v44r --out data/course/lerobot/v44r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v44r "$S"
echo CONVERT_V43R_OK

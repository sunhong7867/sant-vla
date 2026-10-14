#!/bin/bash
# v46r (2026-10-02) = v45r 와 같은 구성에 packed_boxpair2(ep_0037 무결성 실패로 제외 후 155 ep) 를 확실히 포함. Stanley 순항 + packed_div 의 v0·v2(물체 7종, v1 제외) + packed_boxtri 전부 + packed_boxpair 전부.
# packed_boxpair(+2, 재부팅으로 나눠 수집): 같은 출발·같은 위치의 v1(우리 차선 회피) + v2(옆 차선 직진) 짝, ego PosePublisher 라벨(POSE_SOURCE=cli).
# 짝 없는 packed_boxv1 은 뺐다 — r44 에서 빈 차선도 꺾게 만든 원인(docs/experiments/avoidance/20261002_1225).
# packed_boxtri: 박스 묶음 수집 — 같은 출발·같은 위치에서 v0(빈 차선 직진)/v1(우리 차선 회피)/v2(옆 차선 직진).
# 스윕(sw<N>, v1 만)에서 빈 차선도 인덱스 70 에서 꺾던 위치 습관을 짝 시연으로 끊는다.
set -e
cd ~/sunhong/nav-vla
S=data/course/packed_v46r_staging
rm -rf "$S" data/course/lerobot/v46r
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
                  ("data/course/packed_boxpair", ("v1", "v2")), ("data/course/packed_boxpair2", ("v1", "v2"))):
    c = collections.Counter()
    if not os.path.exists(os.path.join(src, "index.jsonl")):
        print(src, "없음 — 건너뜀"); continue
    for l in open(os.path.join(src, "index.jsonl")):
        r = json.loads(l)
        d = os.path.join(src, r["episode"])
        if r["cf_variant_id"] in keep and os.path.exists(os.path.join(d, "reasoning.jsonl")):
            link(d); c[r["cf_variant_id"]] += 1
    print(src, dict(c))
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id navvla/v46r --out data/course/lerobot/v46r \
  --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py data/course/lerobot/v46r "$S"
echo CONVERT_V45R_OK

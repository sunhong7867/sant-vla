#!/bin/bash
# g5d 데이터 줄이기 (2026-10-15, docs/experiments/goto_object/20261015_1757_g5d-data-size-prereg.md).
# g5d 스테이징(795 ep 심볼릭 링크)에서 시드 고정 무작위 N 개 → 같은 변환(state 6).
# 순열이 같으므로 N=200 은 N=100 을 포함한다.
#   N=100 OUT=g5s100 bash code/course/convert_g5d_subset.sh   → data/course/lerobot/g5s100
set -e
cd ~/sunhong/nav-vla
N=${N:?N=100}; OUT=${OUT:?OUT=g5s100}; SEED=${SEED:-20261015}
SRC=data/course/packed_g5d_staging
S=data/course/packed_${OUT}_staging
[ "$(ls "$SRC" | wc -l)" = 795 ] || { echo "CONVERT_ABORT: $SRC 가 795 ep 가 아님"; exit 8; }
rm -rf "$S" "data/course/lerobot/$OUT"
mkdir -p "$S"
SRC=$SRC S=$S N=$N SEED=$SEED python3 - <<'PY'
import collections, os, random
src, dst, n = os.environ["SRC"], os.environ["S"], int(os.environ["N"])
eps = sorted(os.listdir(src))
random.Random(int(os.environ["SEED"])).shuffle(eps)
pick = eps[:n]
for e in pick:
    os.symlink(os.path.realpath(os.path.join(src, e)), os.path.join(dst, e))
c = collections.Counter(os.path.basename(os.path.dirname(os.path.realpath(os.path.join(src, e)))) for e in pick)
print("STAGED", len(pick), dict(c))
PY
./venv/bin/python code/to_lerobot.py "$S" --repo-id "navvla/$OUT" --out "data/course/lerobot/$OUT" \
  --goal-from-goto --standstill-state --standstill-cap 3.5
./venv/bin/python code/build_reasoning_sidecar.py "data/course/lerobot/$OUT" "$S"
rm -rf ~/.cache/huggingface/datasets/parquet
grep -o '"observation.state"[^}]*}' "data/course/lerobot/$OUT/meta/info.json" | head -c 300; echo
echo CONVERT_SUBSET_OK

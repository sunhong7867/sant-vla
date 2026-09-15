#!/bin/bash
# Counterbalanced ICCE-Asia 2026 closed-loop diagnostic.
#
# 2 wording regimes x 2 reset lanes x 2 instruction orders.  Each invocation
# records SAME(A,A) and DIFFERENT(A,B), i.e. four physical rollouts, for 32
# rollouts total.  The v6 training contract is enforced explicitly.
set -euo pipefail

WS="${WS:-$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)}"
CKPT="${CKPT:-$WS/models/ckpt_v6_60k}"
RUNNER="$WS/tools/eval/ring_map_probe.sh"
DURATION_S="${DURATION_S:-30}"
OVERWRITE="${OVERWRITE:-0}"

INNER_TRAIN="Start driving in the inner lane, at a normal speed."
OUTER_TRAIN="Start driving in the outer lane, at a normal speed."
INNER_TEST="Roam the track in the innermost lane, at a regular speed."
OUTER_TEST="Roam the track in the outermost lane, at a regular speed."

run_case() {
  local prefix=$1 start_label=$2 start_y=$3 regime=$4 order=$5 say_a=$6 say_b=$7
  local output="$WS/eval_out/${prefix}_map.json"
  if [ -e "$output" ] && [ "$OVERWRITE" != 1 ]; then
    echo "SKIP existing $output"
    return
  fi
  DURATION="$DURATION_S" REPEATS=1 MAX_SPEED=2.25 SPEED_SCALE=1.0 \
    SPEED_SLEW=0.08 TRACK_MODE=replay REFILL_AT=0.3 SPLICE_OVERLAP=5 \
    FORCE_ZERO_STEER_STATE=true POLICY_SEED=0 START_X=-1.49 \
    START_Y="$start_y" START_YAW=-1.571 START_LABEL="$start_label" \
    SAY_A="$say_a" SAY_B="$say_b" \
    CASE_LABEL="DIFFERENT instruction ($regime, $order)" \
    bash "$RUNNER" "$CKPT" "$prefix"
}

# Canonical top-straight centers from track_paths.json: lane2 (outer) and
# lane1 (inner), respectively.
run_case icce26_bal_familiar_outer_ab outer 24.54784 familiar AB "$INNER_TRAIN" "$OUTER_TRAIN"
run_case icce26_bal_familiar_outer_ba outer 24.54784 familiar BA "$OUTER_TRAIN" "$INNER_TRAIN"
run_case icce26_bal_familiar_inner_ab inner 21.39627 familiar AB "$INNER_TRAIN" "$OUTER_TRAIN"
run_case icce26_bal_familiar_inner_ba inner 21.39627 familiar BA "$OUTER_TRAIN" "$INNER_TRAIN"

run_case icce26_bal_test_outer_ab outer 24.54784 test-wording AB "$INNER_TEST" "$OUTER_TEST"
run_case icce26_bal_test_outer_ba outer 24.54784 test-wording BA "$OUTER_TEST" "$INNER_TEST"
run_case icce26_bal_test_inner_ab inner 21.39627 test-wording AB "$INNER_TEST" "$OUTER_TEST"
run_case icce26_bal_test_inner_ba inner 21.39627 test-wording BA "$OUTER_TEST" "$INNER_TEST"

echo "ICCE26_BALANCED_DONE"

# Data audit notes for v26

The tables and figures are generated from the CSV/JSONL files included in `data/`. No new parser or closed-loop experiment was added in v26; the revision keeps the v25 subtype breakdown, reduces repeated caveats, and foregrounds the LLM-only capacity/refusal negative finding.

Key values preserved:

- LC-Utt v1.0: 150 utterances, 6 top-level categories x 25 utterances.
- C6 subtype split: C6a non-driving OOS = 15 utterances (`u126`--`u140`); C6b refusal/keep-current = 10 utterances (`u141`--`u150`).
- L1 8B LLM-only: exact 0.927, total C6 FP-OOS 6/25, all 6 in C6b.
- L1 8B GuardedLC: exact 0.967, total C6 FP-OOS 0/25.
- L2 8B LLM-only: L2 0.993, command FP-OOS 1/25, reset 14.
- L2 8B GuardedLC: L2 1.000 on evaluated valid-reset sample, command FP-OOS 0/25, reset 12.
- Robustness: subset50 repeated executions, 10 unique C6 utterances per capacity repeated under 9 timing/replicate conditions.

v26 preserves the repeated-run interpretation: repeated robustness runs are timing-stability evidence and are not treated as 270 independent language samples.

## C6 subtype check

The C6 subtype table reports parser-level FP-OOS:

- C6a non-driving OOS: LLM-only 0/15 at 0.6B, 4B, and 8B; GuardedLC 0/15 at all capacities.
- C6b refusal/keep-current: LLM-only 1/10, 3/10, and 6/10 for 0.6B, 4B, and 8B; GuardedLC 0/10 at all capacities.

This supports the v26 interpretation that the zero-FP result is evaluated failure-mode interception, not a population-level safety guarantee. By construction, the C6b subtype coincides with the rule-trusted C6 partition and C6a coincides with the LLM-routed C6 partition, so subtype localization and routing interception should not be treated as independent evidence.


## Held-out refusal stress-test seed

`data/adversarial_refusal_heldout_v0.jsonl` contains 30 proposed paraphrased refusal utterances for a future L1-only held-out stress test. These rows are not included in any reported v26 metric and should not be merged with LC-Utt v1.0 without clearly labeling the result as a separate held-out diagnostic slice.

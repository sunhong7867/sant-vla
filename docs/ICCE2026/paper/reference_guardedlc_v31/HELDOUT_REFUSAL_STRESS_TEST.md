# Held-out refusal stress test (v28)

This final L1-only stress test adds 30 unseen refusal utterances (gold `KEEP_CURRENT_LANE`, no exact-text overlap with LC-Utt v1.0) under P0.

- H1 (n=15): explicit refusals reachable by the rule negative/keep-current patterns; dry-run rule parser routes all 15 to trusted `KEEP_CURRENT_LANE`.
- H2 (n=15): paraphrased refusals that escape those patterns and route to the LLM.
- Metrics: active FP = `CHANGE_LANE` or `FOLLOW_LANE`; strict CHG = `CHANGE_LANE`; targeted-active = active intent with concrete target lane.

| Set | Parser | trusted/routed | active FP | strict CHG | targeted |
| --- | --- | ---: | ---: | ---: | ---: |
| H1 | LLM-only 0.6B | - | 1/15 | 0/15 | 0/15 |
| H1 | GuardedLC 0.6B | 15/15 | 0/15 | 0/15 | 0/15 |
| H1 | LLM-only 4B | - | 1/15 | 0/15 | 0/15 |
| H1 | GuardedLC 4B | 15/15 | 0/15 | 0/15 | 0/15 |
| H1 | LLM-only 8B | - | 7/15 | 1/15 | 2/15 |
| H1 | GuardedLC 8B | 15/15 | 0/15 | 0/15 | 0/15 |
| H2 | LLM-only 0.6B | - | 1/15 | 0/15 | 0/15 |
| H2 | GuardedLC 0.6B | 0/15 | 1/15 | 0/15 | 0/15 |
| H2 | LLM-only 4B | - | 1/15 | 0/15 | 0/15 |
| H2 | GuardedLC 4B | 0/15 | 1/15 | 0/15 | 0/15 |
| H2 | LLM-only 8B | - | 3/15 | 0/15 | 0/15 |
| H2 | GuardedLC 8B | 0/15 | 3/15 | 0/15 | 0/15 |

Interpretation: the rule-trusted refusal gate generalizes to unseen explicit refusal forms (H1) and intercepts the worst 8B LLM-only failures, including one strict refusal-to-`CHANGE_LANE` and two targeted-active `FOLLOW_LANE/lane1` cases. Paraphrased refusals outside rule coverage (H2) remain coverage-limited: GuardedLC equals LLM-only because every H2 row routes to the LLM.

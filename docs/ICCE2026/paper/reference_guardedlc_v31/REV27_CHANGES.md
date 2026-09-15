# v27 changes from v26

- Reclassified L1 FP-OOS as **active-intent FP-OOS** rather than direct lane-change command FP.
- Added strict C6b refusal-to-`CHANGE_LANE` counts to the C6 subtype table. In the reported P0 rows, strict refusal-to-change is 0/10 for rule, LLM-only, and GuardedLC.
- Revised the abstract, introduction, contributions, metrics, discussion, and conclusion to state that the observed refusal failure is mostly `FOLLOW_LANE` instead of `KEEP_CURRENT_LANE`, not refusal-to-`CHANGE_LANE`.
- Added `tables/table_iv_prompt_sensitivity.tex` and `data/prompt_c6b_active.csv` summarizing LLM-only C6b active-intent errors across P0--P3.
- Clarified that L2 command FP-OOS is the actual command-publication safety event and that many L1 active-intent errors do not publish motion after stateful resolution.
- Retained the adversarial refusal held-out protocol as future work only.

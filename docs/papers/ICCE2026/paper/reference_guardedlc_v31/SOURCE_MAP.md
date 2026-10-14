# Source map

- `tables/table_i_dataset.tex`: `data/lc_utt.jsonl`
- `tables/table_ii_l1_main.tex`: `data/L1_0.6b.csv`, `data/L1_4b.csv`, `data/L1_8b.csv`, `data/stats_l1_boot.csv`, `data/stats_l1_fpoos.csv`
- `tables/table_iii_c6_subtype.tex`: `data/c6_subtype_fpoos.csv`, derived from row-level C6 traces in `data/L1_0.6b.csv`, `data/L1_4b.csv`, and `data/L1_8b.csv`; strict refusal-to-`CHANGE_LANE` counts are from the same traces
- `tables/table_iv_prompt_sensitivity.tex`: `data/prompt_c6b_active.csv`, derived from prompt-ablation C6b active-intent FP-OOS summaries
- `tables/table_iii_category_l1.tex`: `data/L1_4b.csv`, `data/L1_8b.csv` (category exact-match and GuardedLC fallback/LLM-route counts)
- `tables/table_iv_l2_nominal.tex`: `data/L2_nominal.csv`, `data/stats_l2_boot.csv`, `data/stats_l2_fpoos.csv`
- `tables/table_v_l2_robustness.tex`: `data/L2_robust.csv`, `data/L2_robust_table.csv`, `data/stats_robust_boot.csv`, `data/stats_robust_fpoos.csv`
- Held-out refusal stress test in v28 manuscript text: `data/lc_utt_heldout_refusal.jsonl`, `data/heldout_refusal_summary.csv`, and `HELDOUT_REFUSAL_STRESS_TEST.md`
- `figs/fig1_pipeline.*`: GuardedLC pipeline diagram
- `figs/fig2_pareto.*`: L1 exact-match / latency from `data/L1_*.csv`
- `figs/fig4_l2_robustness.*`: L2 robustness sweep figure from `data/L2_robust*.csv`
- `figs/fig3_oos_safety.*`: retained from v23 but not used in v28 main text; C6 safety evidence is now reported as subtype and prompt-sensitivity tables plus the held-out stress-test paragraph.

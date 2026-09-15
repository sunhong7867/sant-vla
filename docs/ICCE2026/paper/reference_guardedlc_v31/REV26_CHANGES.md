# v26 changes from v25

- Elevated the non-circular negative finding: LLM-only average exact-match improves with Qwen3 capacity, while refusal/keep-current FP-OOS rises from 1/10 to 3/10 to 6/10.
- Reordered the contribution list so the capacity-vs-failure-type finding appears first.
- Compressed circularity caveats: IV-C now uses one sentence stating that C6 subtype localization and routing interception are the same observation viewed through two labels; the stronger limitation remains in Threats to Validity.
- Reduced L2 emphasis: Layer-2 results are framed mainly as evidence of downstream absorption and rescue-gap value.
- Toned down latency claims: latency is used only as relative call-reduction evidence because hardware metadata were not logged.
- Sharpened differentiation from RouteLLM and RoboGuard in Related Work.
- Added `data/adversarial_refusal_heldout_v0.jsonl` and `ADVERSARIAL_REFUSAL_HELDOUT.md` as a not-yet-evaluated protocol for the next empirical revision. No held-out results are claimed in the paper.

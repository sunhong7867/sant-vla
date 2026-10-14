# Revision v28 changes

- Added the held-out refusal stress-test result to the abstract, contributions, L1 sensitivity discussion, scope discussion, threats, and conclusion.
- The held-out test uses 30 unseen refusal utterances under P0: 15 H1 explicit rule-covered refusals and 15 H2 paraphrased rule-escaping refusals.
- Main H1 result: 8B LLM-only has 7/15 active FP-OOS, including one strict `CHANGE_LANE` and two targeted-active `FOLLOW_LANE/lane1`; GuardedLC has 0/15 at every capacity by keeping H1 on the trusted rule path.
- Main H2 result: GuardedLC equals LLM-only because all H2 utterances route to the LLM; active FP-OOS is 1/15, 1/15, 3/15 for 0.6B/4B/8B and targeted-active is 0/15.
- Removed the standalone practical-implications subsection to preserve the 6-page IEEE layout after adding the stress-test evidence.
- Kept the v27 correction that FP-OOS is active-intent type error, not necessarily a lane-change command.

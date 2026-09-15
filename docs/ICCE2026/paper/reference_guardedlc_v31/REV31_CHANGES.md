# REV31 changes

- Added a broader-system Related Work paragraph using all three reviewer-suggested references:
  - mobile ad hoc network real-time traffic under node-density changes;
  - the Segment Anything review for perception-side generality and deployment limits;
  - AES voice cryptography for security/latency/energy trade-offs.
- Positioned those works as complementary context, not as direct benchmarks for the language-to-intent boundary.
- Expanded the GuardedLC implementation description to make the actual runtime path explicit: rule/LLM parsing, canonicalization, stateful resolution, command gating, and the ROS2 lane controller.
- Explicitly stated that the evaluation is text-only and excludes independent user collection, ASR errors, microphone capture, and real in-cabin interaction.
- Strengthened Threats to Validity and Conclusion without adding unsupported experiments or claims.
- Removed the generic `caption` package so IEEEtran controls caption formatting; table titles now use native IEEE small caps.
- Shortened all table captions to concise title form.
- Added the three new bibliography entries after their first appearance and retained numeric citation order.

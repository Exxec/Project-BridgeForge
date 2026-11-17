- Probe 0.3.3: every combat round now fights its own hulls (ROADMAP-3 93.39). The mission definition only reads the round counter,
  and a battle's end advances it. 0.3.2 advanced the counter on every definition, and the game defines the mission again after
  each battle. With two rounds, the second battle therefore fought round 1's hulls again and round 2's never fought (G1-LIVE3, G2,
  G2B-LIVE-0985a-20261117).
- `probe-group report` adds `combat_rounds` (the rounds that started a battle and the ones missing, with their hull ranges) and
  prints a WARN for a round that never fought.
- The live harness confirms that each battle started (93.37, 95.12(a)). A restart whose clicks start nothing gets a screenshot
  beside the log and one retry, and two misses end as LIVE_STUCK naming the retry. After a battle, Continue waits for the game to
  define the mission again.

# Project charter

The supplied design brief is the authoritative charter for Project Bridgeforge. Its core constraints are captured here for the repository:

- Understand first, modify second, validate always.
- Never modify the input mod in place; work on copies or emit patches only.
- Prefer deterministic, data-driven analysis and migrations.
- Classify findings as `SAFE`, `REVIEW`, `MANUAL`, or `UNKNOWN`, with explicit confidence.
- Never equate compilation with behavioral correctness.
- Start with the 0.95.x–0.98.x corridor and a CLI-first scanner.

Bridgeforge is not a runtime profiler. Runtime profiling, attribution, benchmarking, and regression comparison belong to the independently deployable Starsector Performance Workbench. The programs may exchange only explicit, versioned report metadata; neither program requires the other.

The complete user-supplied brief remains the source design record supplied to this project.

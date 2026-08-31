# Bytecode boundary

Bridgeforge bytecode support is an inspection and comparison capability first.
The helper reads class-file bytes through pinned ASM 9.7.1; it never defines,
loads, or executes a mod class. Its vendored JAR SHA-256 is
`8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281`.

`bytecode-inspect` emits JSON only. `bytecode_diff` compares symbolic class
inventories and explicitly labels control-flow and exception-table invariants
as `NOT_ASSESSED`. No bytecode rewrite command exists yet.

Future application phases must reject descriptor, instruction, branch, frame,
signature, invokedynamic, and class-version changes unless separately designed,
verified, and approved.

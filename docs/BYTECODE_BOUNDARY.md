# Bytecode boundary

Bridgeforge bytecode support is an inspection and comparison capability first.
The helper reads class-file bytes through pinned ASM 9.7.1; it never defines,
loads, or executes a mod class. Its vendored JAR SHA-256 is
`8cadd43ac5eb6d09de05faecca38b917a040bb9139c7edeb4cc81c740b713281`.

`bytecode-inspect` emits JSON only. `bytecode-diff` compares symbolic class
inventories, method opcode sequences, instruction and branch counts, and
exception-table counts.

`bytecode-apply` is deliberately narrow: it writes a distinct output copy and
accepts only explicitly approved, exact same-descriptor method/field remaps or
exact type-opcode remaps backed by evidence. The semantic verifier rejects
class-name, class-version, field, method, instruction-count, opcode-sequence,
branch-count, exception-table, or reference-shape changes. JAR application
also verifies that every unselected archive member is byte-for-byte unchanged.

The rewriter uses ASM's reader-preserving `ClassWriter(reader, 0)` mode; it
does not recompute frames. Descriptor, instruction, branch, frame, signature,
invokedynamic, and class-version changes remain out of scope unless separately
designed, verified, and approved.

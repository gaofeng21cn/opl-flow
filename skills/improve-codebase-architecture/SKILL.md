---
name: improve-codebase-architecture
description: "Use when the user asks to find architecture deepening opportunities, consolidate shallow modules, improve testability, or simplify navigation using the repository's domain language, CONTEXT.md, ADRs, and real dependency structure."
---

# Improve Codebase Architecture

Find changes that reduce caller knowledge and concentrate behavior behind a smaller, more stable interface. Repository vocabulary and ADRs remain authoritative; the module/depth/seam terms are an analysis lens, not mandatory renames.

## Process

1. Read the relevant `CONTEXT.md`, context map, ADRs, repository instructions, and current implementation.
2. Trace the real callers, dependencies, invariants, and tests with available structural tools. Do not require subagents or a specific report renderer.
3. Look for shallow pass-through modules, leaked sequencing or representation, duplicated caller knowledge, tightly coupled files, speculative seams, and tests that must bypass the public interface.
4. Apply the deletion test: if removing a module makes complexity disappear, it was probably indirection; if complexity spreads back across callers, the module may be earning its keep.
5. Rank only actionable candidates as `Strong`, `Worth exploring`, or `Speculative`.

For each candidate, provide files, current friction, proposed boundary, hidden complexity, caller/test impact, ADR conflict, migration risk, and verification path. Use prose, a table, or a diagram only when it materially improves understanding; HTML is optional, never mandatory.

Use [LANGUAGE.md](LANGUAGE.md) for analysis vocabulary and [DEEPENING.md](DEEPENING.md) for dependency/test strategy. Read [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md) only when alternative interface designs are needed.

For review-only requests, stop after a ranked recommendation. For authorized implementation, make the smallest selected change, update domain vocabulary or an ADR only when a real decision requires it, and verify behavior through the resulting interface.

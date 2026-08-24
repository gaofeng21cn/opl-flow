# Interface Design

Use this reference when a selected deepening candidate has materially different interface shapes.

## Process

1. State the constraints, callers, invariants, error modes, dependency category, and behavior the interface must hide.
2. Produce two or three genuinely different designs. Use independent subagents only when available and useful; otherwise design them directly.
3. For each design, show the interface, one usage example, hidden implementation, dependency strategy, and trade-offs.
4. Compare designs by caller knowledge, leverage, locality, misuse resistance, migration cost, and test surface.
5. Recommend one design or a concrete hybrid. Do not leave the user with an unranked menu.

Use repository domain terms for names. Use [LANGUAGE.md](LANGUAGE.md) and [DEEPENING.md](DEEPENING.md) only as analysis aids.

# Challenge a design against the domain

Start with the decision the user wants to settle. Read the affected callers,
the project's glossary and any relevant ADRs. Follow the repository's naming
convention. Both `GLOSSARY.md` and older `CONTEXT.md` trees are in use. If a
glossary map exists, use it to select the relevant context.

Resolve questions the code can answer before interviewing the user. For each
open decision, describe a concrete scenario, explain the recommendation, and
ask one question at a time. For example, when a plan promises partial order
cancellation, check what the order and payment APIs actually allow. Distinguish
a requested behavior change from a disagreement about a term.

When documentation changes are in scope, record resolved terms in the existing
glossary. For a new glossary, use [the glossary format](CONTEXT-FORMAT.md).
Record a decision in the project's ADR format when it is costly to reverse,
surprising to a future reader, and rests on a real trade-off.
[ADR format](ADR-FORMAT.md)

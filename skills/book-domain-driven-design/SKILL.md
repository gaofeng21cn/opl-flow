---
name: book-domain-driven-design
description: "Use when the user explicitly asks for the Domain-Driven Design or Evans lens on ubiquitous language, bounded contexts, aggregates, invariants, context relationships, or anti-corruption boundaries."
---

# Apply The DDD Lens

Treat the repository's domain language and owner surfaces as authority. Use DDD vocabulary only when it clarifies the model.

- Keep one Ubiquitous Language inside each Bounded Context and make context differences explicit.
- Put business invariants and lifecycle rules in the domain model rather than controllers, persistence, or integration code.
- Use Entities for identity, Value Objects for descriptive value, and Domain Services only when behavior has no natural object home.
- Draw Aggregate boundaries around invariants and consistency needs; expose only roots.
- Keep persistence, UI, messaging, and external schemas outside the model or behind translation.
- Choose cross-context relationships deliberately; use an anti-corruption layer when another model would distort the local one.
- Test valid and invalid transitions in domain language.
- Protect the Core Domain from generic infrastructure and supporting complexity.

Do not introduce DDD ceremony where a plain data structure or focused module already expresses the rules clearly.

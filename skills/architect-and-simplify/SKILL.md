---
name: architect-and-simplify
description: Use when the user asks to map a codebase, improve architectural boundaries, simplify an over-engineered system, stress-test a design against domain language, or apply an architecture lens.
---

# Architect And Simplify

Choose one architecture mode, gather evidence from the real dependency and
authority structure, and produce the smallest useful decision or change. This
skill routes to focused leaf skills; it does not duplicate their manuals.

## Choose One Mode

- `map`: explain the relevant modules, owners, callers, state, and boundaries.
  Use `$zoom-out` when available.
- `improve`: deepen an interface, reduce caller knowledge, or concentrate
  invariants. Use `$improve-codebase-architecture` when available.
- `simplify-audit`: run a deletion-first, read-only over-engineering audit. Use
  the upstream-managed `$ponytail-audit`; do not mutate during the audit.
- `grill`: challenge a plan against the repository vocabulary and documented
  decisions. Use `$grill-with-docs` and preserve its interactive boundary.

Optional architecture lenses are `$book-aposd`, `$book-clean-architecture`, and
`$book-domain-driven-design`. Select at most one unless the user explicitly
requests a comparison. DDIA, legacy-code, and Release It remain independent
data, change-enabling, and production-failure lenses; use them only under their
own triggers.

## Ground The Analysis

1. Read repository instructions, domain vocabulary, ADRs, contracts, source,
   tests, and generated or vendored boundaries relevant to the request.
2. Trace actual callers and consumers. Prefer structural evidence for
   definitions and dependency paths, and literal search for exact references.
3. Distinguish an owning abstraction from a pass-through wrapper, a deliberate
   boundary from accidental fragmentation, and source authority from a cache or
   projection.
4. Preserve correctness, security, data integrity, accessibility, public
   contracts, and evidence needed for a real terminal claim.

## Decide

For each actionable candidate provide the current friction, evidence, proposed
owner or boundary, deletion or consolidation effect, migration risk, and
verification path. Rank it as `Strong`, `Worth exploring`, or `Speculative`.

Prefer, in order:

1. remove the requirement or surface;
2. reuse the current owner, standard library, native platform, or installed
   dependency;
3. merge shallow indirection into its real owner;
4. add the minimum custom abstraction that actually hides recurring complexity.

Use a table or diagram only when it materially clarifies several relationships.
For review-only or `simplify-audit` requests, stop at recommendations. When
implementation is authorized, make only the selected change and verify through
the resulting public interface.

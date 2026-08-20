---
name: dsh-doc-standards
description: Use when choosing documentation placement and hierarchy, separating tutorials from references, auditing a documentation corpus, or responding to document-size and generated-doc failures; adapts DeepSeek Harness documentation discipline to the target repository.
---

# Apply Documentation Standards

Use `$opl-doc` as the semantic owner. Follow the target repository's current
documentation taxonomy, navigation, generators, language pairing, and checks;
this Skill does not impose DeepSeek Harness paths, budgets, or Agent Notes.

## Structure Before Prose

1. Identify the document's subject, intended reader, current owner, navigation
   position, and direct child topics.
2. Keep full detail about its own subject, summarize direct children, and move
   deeper material to the owning descendant with a useful link.
3. Classify the document by use. A tutorial leads through ordered work to an
   observable result; a reference supports lookup within an explicit scope.
4. Split substantial mixed forms. Keep a small secondary form in a clearly
   labeled section when splitting would make the result harder to use.
5. Update generated documentation through its source or generator, never by
   editing the projection.

## Audit Semantically

Use size budgets and word counts to find candidates, not to decide correctness.
Remove duplicate current narratives, hand-maintained catalogs that already have
an owner, authoring-session narration, review choreography, and stale status
inventories. Preserve every load-bearing proposition and every current
limitation, negative guarantee, failure mode, ownership boundary, or maintainer
trap. Keep one current owner per topic and replace useful duplicates with links.

Before moving or deleting a document, inspect inbound references and perform
the source, navigation, redirect or alias, and link changes atomically as the
target repository requires. Exclude frozen history from editorial maintenance.

## Verify

Run the repository's focused documentation generator, link checker, site build,
language-pair check, lint or format gate, and `git diff --check` in proportion to
the change. Report the governed topics, their current owners, removed or reduced
duplicates, and any authority or evidence gap.

---
name: "opl-doc"
description: "Use when developer documentation must be aligned with live repository truth, duplicate current narratives consolidated, or documentation for removed code and workflows retired."
---

# OPL Doc

Keep developer documentation useful by aligning it with the repository's real
sources of truth. Treat this as semantic governance, not a prescribed document
layout, a second project-management system, or an automated truth generator.

## Establish Authority

1. Read the latest user instruction and the repository's `AGENTS.md` first.
2. Identify the semantic topic being governed and its current owner. A topic
   may be architecture, status, an interface, an invariant, a release boundary,
   an active gap, or another decision-bearing subject.
3. Verify current-state claims against the strongest live surfaces available:
   machine-readable contracts and schemas, source and callers, tests and
   validators, then runtime or external owner readback. Treat prose as a claim
   unless the repository explicitly assigns it decision authority.
4. Keep user-owned target state and explicit product decisions distinct from
   implementation currentness. Do not infer the intended design only from the
   code that happens to exist today.
5. If authority remains materially ambiguous, preserve the competing claims,
   name the missing evidence, and ask only when choosing would change the
   requested outcome.

Do not require a fixed set of files such as `docs/project.md`, `status.md`, or
`architecture.md`. Follow the target repository's existing taxonomy and owner
boundaries.

## Govern By Meaning

Audit the relevant sections, not whole files as indivisible units. Classify
each section as one of:

- `current_truth`: a concise statement owned here and supported by live facts;
- `active_gap`: work that still separates the current state from an explicit
  target state;
- `support_detail`: unique explanatory material that belongs near, but does
  not compete with, the current owner;
- `history_or_provenance`: evidence that explains a decision or prevents a
  retired surface from being revived;
- `stale_or_conflicting`: content contradicted by a stronger owner or a live
  implementation surface.

For each semantic topic, leave one current owner. Update that owner, reduce
other current narratives to useful pointers or unique support detail, and
remove stale text. Preserve history only when it has an actual provenance or
no-resurrection purpose; do not turn active documentation into a chronological
execution log.

### Govern Decision Records By Future Value

When the repository has ADRs, RFCs, Agent Notes, design records, postmortems,
or another decision corpus, use its existing lifecycle and storage layout. Do
not introduce a fixed note triplet, archive manifest, hash ledger, or parallel
status system merely to govern retention.

Judge retention by future decision value, never by age, length, word count, or
an archive quota. Keep a shipped record active while its rationale,
alternatives, ownership boundary, negative guarantee, durable or wire
semantics, security rule, or reintroduction condition is likely to guide future
work. Demote or archive completed history only after current source and
documentation own the behavior and the remaining record is unlikely to affect
a future decision. A live proposal remains active or is honestly rejected; a
rejected record remains only while it prevents a plausible, recurring mistake.

Before deleting or superseding a record, identify the current owner, distinguish
full from partial supersession, transfer every unique load-bearing proposition
to that owner, and repair inbound references. Preserve partial supersessions
when an independently current contract, rationale, alternative, compatibility
obligation, or reintroduction condition survives.

Write from the repository's current vantage. A reader at the current revision
must be able to resolve every internal reference and verify every current-state
claim without a task transcript, review conversation, or uncommitted plan.
Route durable history to its owning history or provenance surface instead of
narrating it in current documentation.

When trimming or reconciling prose, preserve every load-bearing proposition:
actor and action, condition and ordering, `must`/`may`/`never` modality, negative
guarantees and exceptions, ownership, side effects, failure modes, and
consequences. Shorter prose is an improvement only when those facts remain
accurate and clear.

Apply the same standard to developer-facing JSDoc, code and test comments,
prompts, descriptions, diagnostics, and visible technical strings when they are
inside the requested scope. Keep non-obvious caller contracts, lifecycle and
ownership rules, failure behavior, security constraints, and maintainer traps;
remove code restatement, review choreography, disposable derivation, and
authoring-session narration. Treat model- or user-visible wording as behavior
and run the owning behavioral check when it changes.

## Keep Document Semantics Model-Owned

Documentation prose, semantic content, structure, naming, priority, and
current-state narratives are AI-managed. Scripts, contracts, and tests must not
decide whether that content is correct through required or forbidden keywords,
exact sentences, text snapshots, heading or section layouts, line/page/word or
file counts, or status and priority assertions embedded in Markdown or Skill
text.

Machine checks may validate deterministic mechanics without becoming a second
semantic owner: parsability and front matter/schema, links and referenced asset
existence, generated-artifact integrity and provenance, explicitly executable
code examples, secrets and security boundaries, path safety, license identity,
and irreversible side-effect gates. Retire a check when it reads prose to infer
design intent, progress, priority, documentation quality, or current truth.
Do not add a test that merely asserts this Skill or Profile contains prescribed
wording; verify carrier identity and installed readback instead.

## Make Proportional Changes

- Edit the smallest set of sections that restores a clear owner and accurate
  current state. Do not reorganize the entire docs tree to fix one topic.
- Reuse the repository's current planning and history surfaces. Do not create a second ledger,
  coverage database, mandatory change packet, or fixed batch matrix. For durable
  multi-step work, use the existing OPL Flow, Beads, Linear, or repo-native
  owner surface.
- Let the model make semantic judgments from context. Use scripts only for the
  deterministic mechanics above when the check is genuinely repeated and
  error-prone; file presence and keyword counts do not prove documentation is
  correct.
- Match claim strength to evidence. Mark unknown, deferred, or externally
  unverified facts honestly.
- When documentation describes a retired module, command, workflow, or
  contract, first prove the successor and real caller cutover. Then retire the
  stale documentation with the old surface; do not add permanent aliases or
  compatibility prose without an active compatibility requirement.

## Work Across Repositories

Keep each repository's product and domain truth in that repository. OPL Flow
owns only this reusable governance method and any shared execution state; it
does not become the documentation content authority for consumer repositories.

For multiple repositories, worktrees, or concurrent owners, use
`$coordinate-concurrent-tasks`. Give every writable slice one owner and a
bounded write set, then integrate against fresh canonical truth. A document
cleanup task does not authorize changes to unrelated code, runtime state, or
external systems.

## Verify And Finish

Run the target repository's focused documentation, contract, link, build, or
test checks in proportion to the changed claims. Use fresh runtime, installed,
remote, or public readback when the documentation makes claims about those
surfaces.

Finish with:

- the semantic topics governed and their current owners;
- stale or duplicate surfaces removed or reduced;
- verification actually run;
- unresolved authority or evidence gaps.

Do not report documentation alignment as runtime, release, domain, or product
readiness unless those owner surfaces were independently verified.

# Trim Authoring-Session Leakage

Use `governance.md` and `prose.md`. The target is prose whose viewpoint is
the temporary authoring session rather than the repository, not private model
reasoning as a security classification.

## The Test

Ask whether a reader at the current revision, without the task transcript, PR
conversation, or uncommitted plan, can resolve every reference and verify every
claim. If not, preserve the factual clauses as current repository facts and
remove the disposable narration. Delete a passage outright only when it carries
no load-bearing proposition.

Typical candidates include:

- dead decision ordinals, audit codes, phase labels, or sections of uncommitted
  drafts;
- "this PR", stack-position, previous-commit, reviewer, or review-round
  narration in durable prose;
- repository-history storytelling such as "used to" or "this cut" where the
  current behavior or counterfactual regression guard is the useful fact;
- comments that argue with a reviewer, narrate obvious control flow, or walk
  through a test body;
- hedged deferrals without a durable issue or `TODO` owner.

Do not delete resolvable issue references, external standards, required
suppression reasons, measured bounds, runtime old/new object terminology,
present-tense counterfactual regression pins, or sanctioned history inside a
decision record or postmortem. Do not edit frozen history or recorded fixtures.

## Workflow

1. Confirm scope and read the owning code or document.
2. Search broadly for candidate language, then read dense prose without relying
   on keyword hits alone.
3. Enumerate propositions before editing so an obligation is not turned into an
   endorsement and a hypothetical is not promoted to shipped behavior.
4. Fix the owner first, regenerate projections, update paired languages when
   applicable, and behavior-test model- or user-visible strings.
5. Re-run the repository's documentation or behavior gates and
   `git diff --check`; report sanctioned keeps as well as removed leakage.

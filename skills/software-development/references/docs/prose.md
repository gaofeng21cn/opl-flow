# Apply The Prose Standard

Use `governance.md` for authority and current-state alignment. Confirm the requested
scope or use the exact current diff when that is the obvious scope. Review and
audit requests remain read-only; edit only when the user asked to write or fix.

Exclude vendored code, frozen history, generated projections, snapshots, and
recorded fixtures unless the task explicitly targets their owning source.

## Preserve Complete Propositions

Before editing a passage, identify every relevant actor and action, condition,
timing and ordering rule, `must`/`may`/`never` modality, negative guarantee and
exception, ownership transfer, side effect, failure mode, and consequence.
Remove repetition and decoration only when those facts survive more clearly.
Shorter text is not better when it weakens a contract.

Keep prose where code and structure cannot express a required fact:

- public API prose covers return distinctions, errors, side effects, ownership,
  timing, cancellation, durability, and limitations;
- internal comments cover non-local invariants, races, security boundaries,
  surprising failure behavior, and maintainer traps rather than control flow;
- tests explain only non-obvious fixture, entry-path, platform, or assertion
  rationale;
- READMEs and cookbooks state prerequisites, configuration, semantics, failures,
  real entry paths, verification, limitations, and extension points;
- prompts, diagnostics, and visible strings are behavior and need the owning
  behavioral validation when wording changes.

State current behavior from the repository's vantage. Move architecture,
extended rationale, history, and examples to their current owner and link it;
do not replace a necessary local contract with a link alone.

## Finish

Classify candidates as keep, add, trim, restore, restructure, or defer. Update
owner prose before generated artifacts, rerun the narrow relevant checks and
`git diff --check`, and report deliberate keeps as well as edits. Never invent
changes merely to reduce a word count.

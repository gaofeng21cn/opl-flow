# Setup And Update

Use this reference for `setup` and `update`.

These actions install, repair, and update capabilities only. They never run the
explicit `$opl-flow start` owner-API route or create its state.

## Inspect First

Read the configured carrier and Framework projection, then run the combined
workflow readback when an Instance is known:

```bash
opl packages status --package-id opl-flow --json
python3 scripts/opl_workflow.py status --instance <opl-instance>
```

Distinguish Flow package availability, experience-baseline degradation,
specialized capability absence, Profile state, Ledger state, and Fleet state.

## Setup

1. Install or repair Flow through the current Framework/package action.
2. Prepare the user Profile. Apply only a reviewed semantic-merge packet when
   existing content is not a known Flow-owned revision.
3. Repair the declared experience baseline from each component owner's source.
4. Resolve one private `opl-instance-<owner>` only when durable Ledger or Fleet
   state is requested. Confirm owner/name/private visibility before creating a
   remote repository.
5. Initialize Beads only when no Ledger exists. An existing Dolt-backed clone
   uses bootstrap/recovery, not a second `bd init`.
6. Configure Linear or Fleet only when requested by the selected deployment.

## Update

1. Update Flow with `opl packages update opl-flow --json`.
2. Let Framework perform source-aware legacy migration and baseline repair.
3. Update Beads, non-development OPL Skills, and Fleet components only through
   their owners when the requested environment uses them.
4. Pull Dolt before Ledger mutation; push only after a coherent mutation.
5. Restart or create a new Codex session only when executor discovery requires
   it, then verify the effective Skill IDs.

## OPL Skills

OPL Skills contains independently useful non-development workflows. Install
only explicit requested Skill IDs through its owner route; Flow setup does not
install it as a development pack.

## Mutation Boundaries

- Ask only for unavoidable OAuth/GitHub authorization or a materially ambiguous
  target.
- Never copy installed Skill or tool bytes between Fleet nodes.
- Never treat Instance `required: true` as a public Flow dependency.
- Do not create an all-in-one lifecycle owner beside Framework and the actual
  component owners.

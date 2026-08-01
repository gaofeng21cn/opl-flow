# Setup And Update

Use this reference for `setup` and `update`.

These actions install, repair, and update capabilities only. They must not
create a Ledger Dashboard, Bead, Linear project, or Automation. Formal Ledger
onboarding is a separate explicit `$opl-flow start` action.

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
3. Update Beads, OPL Skills, and Fleet components only through their owners.
4. Pull Dolt before Ledger mutation; push only after a coherent mutation.
5. Restart or create a new Codex session only when executor discovery requires
   it, then verify the effective Skill IDs.

## OPL Skills Presets

OPL Skills is an independent enhancement pack. Never install it with `-s '*'`.
Read `gaofeng21cn/opl-skills:contracts/skill-catalog.json`, resolve the requested
preset to explicit member IDs, and pass those IDs to the owner-supported
`npx skills add ... -s <ids> -y` route.

Use `development-complete` for the complete development enhancement set. It
contains architecture workflows, prototype/grilling/zoom-out helpers, and all
six book lenses. Catalog categories are browsing metadata, not mutually
exclusive installation profiles.

## Mutation Boundaries

- Ask only for unavoidable OAuth/GitHub authorization or a materially ambiguous
  target.
- Never copy installed Skill or tool bytes between Fleet nodes.
- Never treat Instance `required: true` as a public Flow dependency.
- Do not create an all-in-one lifecycle owner beside Framework and the actual
  component owners.

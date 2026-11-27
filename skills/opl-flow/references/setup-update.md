# Setup And Update

Use this reference for `setup` and `update`.

These actions install, repair, and update capabilities only. They never run the
explicit `$opl-flow start` owner-API route or create its state.

## Inspect First

Check the Framework API version and the two installed views. Run the workflow
readback when an Instance is configured.

```bash
opl --version --json
opl pack inspect opl-flow --json
codex plugin list --json
python3 scripts/opl_workflow.py status --instance <opl-instance>
```

On v2, `pack inspect` reports the Framework install. Codex can still report an
enabled native plugin from before the upgrade when Pack reports `PACK_NOT_FOUND`.
Fleet checks its capabilities against the installed Flow policy. Use the
Package install entry when registering Flow with Framework. On a v1 carrier,
read `opl packages status --package-id opl-flow --json` for its baseline projection.

## Setup

1. With Framework v2, install the selected Flow Package through the [Package lifecycle](package-lifecycle.md) procedure and confirm its installed identity.
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

1. Use `opl pack update opl-flow --source <source> --json` with the verified v2 Package source. Read back the installed version and the Codex carrier.
2. Review the baseline report and repair any missing capability through its owner.
3. Update Beads, non-development OPL Skills, and Fleet components only through
   their owners when the requested environment uses them.
4. Pull Dolt before Ledger mutation; push only after a coherent mutation.
5. Restart or create a new Codex session only when executor discovery requires
   it, then verify the effective Skill IDs.

## Dual-Host Profile Separation

- **Codex (`~/.codex/`)**: Uses `templates/AGENTS.md` (projected into `~/.codex/AGENTS.md`) and `templates/TASTE.md` (`~/.codex/TASTE.md`), handled via Framework `profile_surface` with semantic merge that preserves machine-local policies appended by the user.
- **AntiGravity (`~/.gemini/`)**: Uses `templates/antigravity/GEMINI.md` (`~/.gemini/GEMINI.md`) and `templates/antigravity/agy-fast-AGENTS.local.md`, handled via `opl_workflow.py antigravity` marker blocks (`OPL_FLOW_AGY_BASELINE`) and never shares or overwrites `~/.codex/AGENTS.md`.

## AntiGravity Baseline

When the user asks to inspect, establish, or repair their AntiGravity
(`~/.gemini/`) baseline, load `references/antigravity-baseline.md` and run
`python3 scripts/opl_workflow.py antigravity doctor --json`, preview with
`apply --dry-run --json`, and apply with `apply --json` (adding
`--install-plugins` or `--with-weekly-audit` only when requested). Existing user
rules outside managed markers are always backed up and preserved.

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

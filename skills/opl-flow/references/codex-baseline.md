# Codex Experience Baseline

Use this reference for `doctor` and `tune`.

## Authority

- Flow owns the recommended profile, model policy, and capability intent.
- Framework compiles Flow intent into generic installation, repair, status,
  and Full build-lock projections; carriers own physical mutation and fresh
  installed readback.
- App owns Auto resolution, UI, persistence, explicit user selection, and the
  fallback used when an installed Flow recommendation is unavailable.
- The user owns the effective `AGENTS.md` and any explicit override.

## Three Status Planes

Read and report these independently:

1. `package_operational`: installed physical surface, enabled exposure, and
   executor callability. Failure blocks Flow-specific actions only.
2. `experience_baseline`: the policy's default Skills and Tools. Missing or
   drifted items produce `degraded` plus an owner-supported repair route; Flow
   itself remains callable.
3. `specialized_capabilities`: optional enhancements such as
   `architect-and-simplify`. Absence is normal and has no repair requirement.

Do not infer any plane from another. A present Plugin does not prove companion
currentness; a missing companion does not prove the Plugin is unusable.

The baseline is grouped as:

| Bundle | Default behavior | Absence |
| --- | --- | --- |
| Internet research | Agent Reach Skill + CLI/doctor | degraded, owner repair offered |
| Office authoring | OfficeCLI Skill family + CLI | degraded, Framework repair offered |
| Document extraction | MinerU extractor Skill + CLI | degraded, Framework repair offered |
| Visual design | `ui-ux-pro-max` | degraded, Framework repair offered |

App first-run does not own this table. Read `system_initialize.recommended_skills`
from the installed Framework projection. When Flow is absent, that Flow-derived
list is absent rather than replaced by an App static catalog.

## Model Policy

Precedence:

```text
explicit user selection
> installed Flow recommendation
> fresh Codex model catalog/default
> App fallback when Flow is unavailable
```

Flow recommends `gpt-5.6-sol` and `max`. Do not overwrite a fixed user choice.
In Auto mode, prefer the live catalog/default according to the App contract.
The recommendation is policy, not proof that the model is currently available.

## Profile Safety

For `~/.codex/AGENTS.md`:

1. read and hash the current target;
2. back it up before mutation;
3. remove only known legacy marker blocks;
4. preserve distinct user preferences;
5. semantic-merge or produce a reviewable packet;
6. compare the target hash immediately before apply;
7. validate and atomically replace, or leave the original untouched.

Use:

```bash
python3 scripts/opl_workflow.py profile status
python3 scripts/opl_workflow.py profile prepare
python3 scripts/opl_workflow.py profile apply --packet <reviewed-packet>
```

`prepare` must not overwrite an unknown existing Profile.

## Capability Routing

The experience baseline is intentionally broad enough to establish the OPL App
usage floor: internet research, Office documents, document extraction, and UI
design support. It is not a claim that every task requires those tools.

Specialized development and architecture capabilities remain in OPL Skills.
When `architect-and-simplify` is discovered, use it for architecture mapping or
simplification. When absent, perform the same work model-natively and report
the capability as optional, not degraded.

For Full distribution, read the Framework-generated
`opl_flow_capability_build_lock.v1`. Do not derive Full payload selection from
an App source manifest; it provides resolution hints only after Flow has
selected a capability.

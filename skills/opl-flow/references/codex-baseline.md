# Codex Experience Baseline

Use this reference for `doctor` and `tune`.

## Local Workflow Before Distribution

For a request to optimize this machine and then synchronize the result into
Flow, start with the user's effective local instructions, Skills, configuration,
and actual execution. Validate that local result first; Flow then carries the
reusable deployment projection for other machines. A package recommendation
does not override local preferences or prove that local behavior improved.

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
3. `specialized_capabilities`: external optional capabilities. Absence is
   normal and has no repair requirement.

Do not infer any plane from another. A present Plugin does not prove companion
currentness; a missing companion does not prove the Plugin is unusable.

The baseline is grouped as:

| Bundle | Default behavior | Absence |
| --- | --- | --- |
| Internet research | Agent Reach Skill + CLI/doctor | degraded, owner repair offered |
| Office authoring | OfficeCLI Skill family + CLI | degraded, Framework repair offered |
| Document extraction | MinerU extractor Skill + CLI | degraded, Framework repair offered |

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

Flow recommends `gpt-6-astra` and `max`. Do not overwrite a fixed user choice.
In Auto mode, prefer the live catalog/default according to the App contract.
The recommendation is policy, not proof that the model is currently available.

### Model Upgrade Audit

When an upgrade includes workflow tuning, use the official documentation for
the exact requested model before changing prompts. Prefer the available
`openai-docs` Skill and its official search/fetch tools. Record the inspected
source and date; do not treat an older bundled guide or a model alias as fresh
guidance.

1. Inspect the effective model, reasoning effort, provider API route, catalog,
   global/project instruction chain, selected configuration overlays, and
   installed Skill sources. Inventory discovery metadata broadly, then read
   the instructions that can actually affect the requested workflow. Inspect
   configuration by field and report only credential presence/source.
2. Audit ambiguous approval language, stale Skill routes, conflicting tool
   mandates, repeated generic process, writing verbosity, delegation criteria,
   and excessive verification. Preserve domain and irreversible-action controls;
   do not rewrite third-party or bundled cache files as local source.
3. Apply the smallest local changes supported by the evidence. Preserve the
   user's language, preferences, fixed model/effort, and intentionally tiered
   automation or fallback choices. A flagship upgrade does not justify moving
   every workload to the flagship or increasing every reasoning budget.
4. Verify changed local files and run a fresh executor on a bounded real task.
   Check actual tool execution, output readback, unnecessary approval pauses,
   Skill routing, and proportional verification. Do not turn prose into
   keyword tests or claim behavioral quality from file equality alone. The
   AGENTS instruction chain is rebuilt for a new run; an existing task may
   retain its original instructions.
5. After local validation, synchronize only reusable behavior into Flow's
   Profile and relevant routed references. Keep personal endpoints, credentials,
   topology, session state, private rules, and workload overrides local. Use the
   existing Profile source/template equality check and validate package source.
   Report source synchronization, publication, installation, and fresh discovery
   separately, according to the user's requested endpoint.

For GPT-6 Astra, the official guide inspected on 2026-09-06 emphasizes continued
execution within existing authorization, explicit user/Skill precedence,
focused clarification, concise prose, intentional delegation, and verification
proportional to the change. Preserve an existing supported reasoning effort;
start `none`/`minimal` workloads at `low` when migration is requested. Tool use
requires Responses; custom `temperature`, `top_p`, and log probabilities are
unsupported. Async tools and mid-turn steering are harness capabilities: do not
invent local config switches or redesign the harness solely to mirror an API
feature list.

Sources:
- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/codex/guides/agents-md

Refresh the model guide during the next model upgrade rather than assuming this
dated summary establishes future compatibility.

## Profile Safety

For `~/.codex/AGENTS.md`:

1. read and hash the current target;
2. back it up before mutation;
3. remove only known legacy marker blocks;
4. preserve distinct user preferences;
5. semantic-merge or produce a reviewable packet;
6. compare the target hash immediately before apply;
7. validate and atomically replace, or leave the original untouched.

Framework owns these guarded Profile mutations:

```bash
opl packages install opl-flow --json
opl packages update opl-flow --json
opl packages repair --package-id opl-flow --json
opl packages status --package-id opl-flow --json
```

The carrier must not overwrite an unknown existing Profile.

## Capability Routing

The experience baseline is intentionally broad enough to establish the OPL App
usage floor: internet research, Office documents, and document extraction. It
is not a claim that every task requires those tools.

Development and architecture capabilities are bundled with OPL Flow. Use
`$software-development` mode `architecture` for mapping or simplification.

The external `stop-that-shit` Plugin is an explicit optional Guard for covered
Codex Hook events. Observe it separately from Flow's model-native Stop Ladder;
do not install or enable it by default, make Flow depend on it, or describe its
absence as degraded. When the user enables it, report Hook trust and coverage
as guard state rather than a security or general model-behavior guarantee.

For Full distribution, read the Framework-generated
`opl_flow_capability_build_lock.v1`. Do not derive Full payload selection from
an App source manifest; it provides resolution hints only after Flow has
selected a capability.

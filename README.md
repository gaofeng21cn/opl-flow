<p align="center">
  <img src="assets/branding/opl-flow-logo.png" alt="OPL Flow logo" width="128" />
</p>

<p align="center">
  <a href="./README.md"><strong>English</strong></a> | <a href="./README.zh-CN.md">中文</a>
</p>

<h1 align="center">OPL Flow</h1>

<p align="center"><strong>The Codex baseline and durable work-coordination layer</strong></p>

<p align="center">
  <img src="assets/branding/opl-flow-ai-fleet-v3.png" alt="OPL Ledger objectives connect through Flow and Fleet to independently managed execution nodes" width="100%" />
</p>

OPL Flow provides a concise user Profile, model recommendation, capability
policy, and reusable Skills for Codex. Optional Beads-backed Ledger and Fleet
capabilities preserve work ownership across tasks, repositories, and machines.

Flow is optional. Its absence does not block Codex, OPL Base, the App, another
Package, or domain work. A missing recommended capability degrades the
experience and offers repair while Flow remains usable.

## Choose A Workflow

| Need | Entry |
| --- | --- |
| Inspect, set up, tune, or update the Codex baseline | `$opl-flow` |
| Develop, review, improve architecture, govern docs, or deliver software | `$software-development` |
| Coordinate native Codex tasks, integrate work, recover, or migrate an owner | `$manage-codex-tasks` |
| Keep durable objectives and an optional Linear portal | `$opl-flow start` |
| Admit remote capacity and continue work across machines | `$opl-flow fleet` |

The Plugin exposes three router Skills. Each loads its focused references only
when needed; ordinary small changes remain model-native. Independent
non-development workflows live in
[OPL Skills](https://github.com/gaofeng21cn/opl-skills). Third-party capabilities
use their own installation and update channels.

## Get Started

Follow [new machine setup](docs/new-machine-codex-setup.md) to install through
the configured carrier and verify discovery in a new Codex task. Then use:

```text
Use $opl-flow setup to establish or repair my Codex baseline.
```

Setup deploys capabilities. Explicit `$opl-flow start` additionally creates or
reuses the Ledger Dashboard, Bead, Linear projection, and one hourly
`OPL Flow Supervisor`. Core usage needs neither Linear nor Fleet.

Flow's current model recommendation and capability selection are owned by
[workflow-policy.json](contracts/workflow-policy.json). Explicit user choices
win; App owns Auto resolution and compatible fallback from the live Codex
catalog. Flow does not inject a hidden prompt.

## Ownership

| Component | Responsibility |
| --- | --- |
| Codex | Reasoning, tools, execution, and native task coordination |
| OPL Flow | Profile and capability intent, workflow methods, Ledger adapter, Git lifecycle, and reusable Fleet engine |
| OPL Framework and native carrier | Package lifecycle, Profile materialization, capability projections, and installed readback |
| OPL Ledger / Beads | Durable objectives, dependencies, current execution owner, checkpoints, and remaining work |
| Linear | Optional complete human projection of the Ledger with narrowly scoped fields |
| GitHub and artifact owners | Canonical source and delivery evidence |
| OPL Fleet | Fresh node/workspace admission, capacity leases, and execution continuity |
| Private OPL Instance | Private Ledger, topology, policy, operations, and personal overlays |

Fleet workspace and owner-migration contracts are implemented in source.
A particular node, migration, or installed Package still requires its own fresh
readback. Broader Fleet capabilities remain explicitly identified as design
work in the [Fleet architecture](docs/opl-fleet-architecture.md).

Credentials, sessions, conversation contents, logs, caches, private paths, and
lease secrets are not public package content or node-to-node synchronization
payloads.

## Develop

```bash
scripts/verify.sh
scripts/verify.sh full
```

These checks validate source contracts; they do not install, publish, or certify
a user's machine. [The documentation index](docs/README.md) routes architecture,
installation, protocol, and maintainer guidance to their owning documents.

## License

[Apache-2.0](LICENSE). Adapted third-party methods and notices are recorded in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

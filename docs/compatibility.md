# OPL Flow Executor Compatibility

This document owns the supported executor boundary. Installation composition
belongs to [capability governance](capability-governance.md), and operator
steps belong to [machine setup](new-machine-codex-setup.md).

## Supported Route

The production route is Codex-first: Codex Plugin Manager is the native
Plugin/config/cache carrier and Codex CLI supplies execution. Framework owns
OPL Package installation and reconciliation across that carrier.

Flow's Package identity, Profile intent, public status, and public actions do
not embed Codex-private session fields. Neutral-contract tests establish that
boundary; they do not certify a second executor or carrier. No parallel Claude
or Hermes product is supported here. A future executor requires an explicit
product decision and a real adapter with its own readback.

## User And Product Boundaries

Flow is optional. Removing it must leave Base, App, ordinary Codex, other
Packages, and domain work usable. Flow does not inject hidden base prompts or
take authority over repository instructions and explicit user preferences.

Changing an executor must preserve the stable Package identity and user-owned
Profile, preferences, and tasks. A missing executor adapter is a route-specific
failure, not evidence that the Package or user data has disappeared.

Standard and Full consume the same Flow policy through Framework. Their
assembly and release qualification remain App-owned; this document does not
define a release matrix or claim current installation readiness.

## Evidence

`scripts/verify.sh` verifies repository contracts. Publication, carrier state,
new-session Skill discovery, execution callability, experience readiness, and
Full build qualification each require their owning readback. None can be
inferred from a successful source check or another layer's version.

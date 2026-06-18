---
name: risk-based-development-flow
description: "Use when Codex is planning, implementing, debugging, or verifying code changes and must choose verification effort, test-writing effort, TDD usage, or completion evidence by risk instead of ritual. Trigger for new features, bug fixes, refactors, runtime/currentness/readiness claims, release/CI work, test-suite bloat, flaky or slow tests, or when the user asks to balance speed and quality."
---

# Risk-Based Development Flow

## Core Rule

Optimize for the cheapest evidence that proves the user-facing claim.

TDD, unit tests, integration tests, end-to-end checks, live CLI readbacks, runtime receipts, logs, screenshots, schema validation, and manual inspection are evidence tools. Choose the smallest set that covers the actual risk. Do not turn testing into a ritual, and do not use green tests to claim behavior that only live/runtime evidence can prove.

Read `references/external-practices.md` when you need the external rationale behind this flow or need to explain it to the user.

## Risk Classes

Classify before implementing or verifying:

| Class | Examples | Default verification | TDD |
| --- | --- | --- | --- |
| L0 Read/Explain | read-only audit, explanation, state check | Fresh source/runtime evidence only | No |
| L1 Docs/Config/Metadata | prose docs, navigation, non-machine config notes | Formatting/link/schema check if relevant | No |
| L2 Small Code Change | local helper, small CLI option, behavior-preserving refactor | Focused existing tests or direct command | Usually no |
| L3 Behavior/Contract Change | CLI/API behavior, schema, machine contract, authority/permission boundary, data writes | Focused tests plus contract/readback evidence | Use when risk or regression value justifies |
| L4 Runtime/Release/Currentness | release, install, CI gate, runtime truth, latest/fresh/currentness/readiness, owner receipt | Live command, runtime artifact, read model, receipt, or end-to-end acceptance first | No as primary evidence |

If a project `AGENTS.md`, contract, or user instruction requires heavier verification, follow it. If that requirement conflicts with this flow, use the stronger project-specific rule but keep scope narrow.

## Verification Budgets

Choose one budget and keep it visible in planning and final evidence:

| Budget | Use when | Limits |
| --- | --- | --- |
| `none` | pure read/explain, no claim of change | no test or build run |
| `tiny` | docs/config/static change | no new tests; one focused check if useful |
| `focused` | ordinary local implementation | run affected command/tests; add at most a few high-value tests |
| `standard` | shared behavior, contracts, multi-file implementation | focused checks plus repo default minimal verification |
| `full` | release, broad refactor, CI/runtime authority, destructive or irreversible paths | full repo or project-prescribed gate plus live/readback evidence |

Do not escalate from `focused` to `standard` or `full` just because unrelated tests fail. Classify unrelated failures as residual risk unless they touch the same contract or write set.

## TDD Decision

Use TDD when at least one is true:

- The user explicitly asks for TDD or test-first.
- A bug has a stable, low-cost reproduction and a regression would be costly.
- The change defines a durable contract, schema, CLI/API behavior, permission boundary, or irreversible write path.
- The desired interface is unclear and a test-first API sketch will reduce design ambiguity.
- A project rule explicitly requires test-first for this surface.

Do not default to TDD for:

- read-only audits;
- docs-only changes;
- behavior-preserving split/rename/cleanup;
- one-off ops;
- runtime/currentness/readiness claims where live evidence is the proof;
- generated output that should be verified through its generator;
- areas where existing higher-level contract/readback evidence already covers the behavior.

When TDD is not selected, still verify. Use direct focused evidence instead of writing tests by habit.

## Test Portfolio Rules

Prefer a balanced portfolio:

- Many small deterministic tests for stable logic and contracts.
- Fewer integration tests for important seams.
- Very few end-to-end tests for critical workflows.
- Live/readback evidence for runtime, release, currentness, and owner-route claims.

Add or keep a test only if it answers: "Which specific regression does this catch?" If the answer is vague, do not add it.

Delete, merge, or avoid tests that:

- lock implementation details instead of observable behavior;
- assert Markdown prose, headings, or documentation wording;
- preserve old facades, aliases, or compatibility wrappers after the owner surface replaced them;
- mostly test mocks;
- are slow, flaky, environment-dependent, or hard to diagnose;
- duplicate coverage already provided by a stronger contract/readback surface.

## Debugging Rules

Always find the root cause before fixing. After root cause is known, choose regression evidence by risk:

- Stable and cheap bug reproduction: add a failing regression test, then fix.
- Flaky, external, timing, environment, or runtime issue: use a minimal reproduction script, diagnostic command, log/readback, or live runtime proof.
- Multi-component failure: instrument the component boundary that distinguishes where the defect lives; remove or contain temporary instrumentation after use.

Do not turn an unrelated red test suite into the task. Fix unrelated failures only when they share the same root cause, same contract, or same write set.

## Completion Evidence

Before saying done, fixed, passed, ready, fresh, latest, current, or release-ready:

1. Restate the exact claim.
2. Choose the evidence type that can actually prove it.
3. Run fresh verification within the chosen budget.
4. Read the output and classify gaps.
5. Report the evidence and residual risk.

Tests passing prove tests passed. They do not prove runtime readiness, release readiness, currentness, production behavior, or owner acceptance unless the project explicitly defines that test as the owner evidence.

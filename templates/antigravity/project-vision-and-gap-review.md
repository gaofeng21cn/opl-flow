---
name: project-vision-and-gap-review
description: >-
  Use when asked to distill a project's design philosophy, define its ideal state in
  one sentence, assess completeness, capability gaps, performance, or over-engineering,
  and propose a prioritized convergence roadmap.
---

# Project Design Philosophy, Ideal State & Gap Review

Keep this evaluation **strictly read-only** until the user approves concrete implementation work. Anchor every judgment in live code and contracts rather than README/whitepaper claims.

## Steps

1. **One-batch architecture snapshot**:
   - Run a single `batch_search` probing entrypoints, `contracts/` / manifests, core runtime modules, test suites, and key `docs/`.
   - Use `quick_outline` + parallel ranged `read_file` (<=200 lines) on critical files; delegate broad multi-repo surveys to read-only `research` subagents with concise structured outputs.
   - Truth precedence: **`contracts/` + live code + tests** > prose `docs/` or whitepapers.

2. **One-Sentence North Star & Ideal Architecture**:
   - State the project's **core job-to-be-done** in one sharp sentence.
   - Define the **ideal minimal form** and explicit **non-goals / ownership boundaries** (what must NOT live in this repository).

3. **Evidence-Backed Gap, Performance & Over-Engineering Audit**:
   - Separate findings into three distinct buckets with exact `file:line` or runtime metrics:
     - **Genuine capability gaps**: missing end-to-end loops, broken contracts, reliability flaws.
     - **Performance / latency bottlenecks**: hot-path I/O, redundant spawns, unbatched calls, memory/token bloat.
     - **Over-engineering / reinvented wheels**: dead abstractions, parallel truths, custom code replaceable by stdlib or platform primitives.

4. **Prioritized Convergence Roadmap**:
   - Present a crisp table ranked by **Net Value vs Implementation Risk** (`P0 / P1 / P2`), explicitly highlighting **delete / merge / simplify** candidates first.
   - Stop at the recommendation table and wait for user confirmation before mutating any files.

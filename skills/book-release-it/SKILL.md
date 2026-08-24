---
name: book-release-it
description: "Use when production failure semantics matter in services, APIs, jobs, queues, or integrations: explicit timeouts, bounded retries, backpressure, bulkheads, circuit breaking, health/readiness, overload, recovery, and operational observability. Do not trigger for ordinary CI edits or generic release documentation."
---

# Apply The Release It Lens

Design the failure path as deliberately as the happy path:

- Put finite timeouts on outbound calls and waits.
- Retry only safe operations; bound count and total time, back off or jitter, and distinguish permanent failures.
- Isolate dependency and workload failure with bulkheads, breakers, separate pools, or fast failure.
- Bound queues, buffers, pools, caches, payloads, and background work; define full behavior and backpressure.
- Preserve core service under overload through demand limits, prioritization, degradation, or load shedding.
- Validate external input and dependency responses before they affect durable state or downstream systems.
- Make startup, health/readiness, migrations, jobs, and administrative controls observable, restartable, authorized, and recoverable.
- Expose latency, saturation, queue age, retries, dependency state, version, configuration, and correlation context without leaking secrets.
- Keep rollback or roll-forward paths for partial operational changes.

Use chaos, capacity, or failure injection only with bounded blast radius, observability, stop conditions, and a concrete learning goal.

# Apply The DDIA Lens

Make the data contract explicit before changing the system:

- Identify the source of truth and label every cache, index, projection, search copy, read model, or materialized view as derived state.
- Distinguish accepted, persisted, visible, applied, and durable success.
- Define behavior for timeout, unknown success, duplicate delivery, replay, reordering, crash, partial write, and stale read.
- Scope ordering and consistency to the smallest key, partition, aggregate, or invariant that requires them.
- Make retryable work idempotent or give it an explicit deduplication and recovery contract.
- Evolve schemas, APIs, messages, and events across old readers, old writers, stored data, and in-flight work.
- Match transaction isolation and coordination to named invariants; do not assume exactly-once delivery.
- Give derived data observable lag, repair, and deterministic rebuild paths.
- Choose replication and partitioning from actual access patterns, failure tolerance, locality, hot keys, and rebalancing cost.

Verification must cover the named failure semantics, not only the happy path.

# Apply The Clean Architecture Lens

Use the lightest boundary that protects real business policy. Do not manufacture ports, adapters, or layers without a volatile dependency or independent policy to protect.

- Source dependencies point toward stable policy; frameworks, databases, UI, queues, vendors, and deployment details stay outside.
- Inner policy owns the interfaces it needs; outer details implement them.
- Pass plain request/response models across policy boundaries, not framework requests, ORM rows, SDK types, or transport objects.
- Keep controllers, handlers, presenters, and adapters focused on translation and wiring.
- Put construction and concrete binding in an outer composition root.
- Test policy without real infrastructure; test adapters at their actual seams.
- Enforce an important boundary in code, package visibility, dependency rules, or tests rather than diagrams alone.

Prefer incremental extraction around a demonstrated change pressure. Preserve existing behavior and repository conventions unless the user explicitly authorizes a wider redesign.

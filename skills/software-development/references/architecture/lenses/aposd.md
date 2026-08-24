# Apply The APoSD Lens

Treat repository facts, user goals, and local contracts as authority. Use this lens to compare designs, not to force abstractions.

- Prefer deep modules: a small semantic interface that hides meaningful complexity.
- Reject pass-through wrappers, exposed sequencing, representation leaks, and configuration that moves internal choices to callers.
- Pull complexity downward when the lower module owns the knowledge.
- Keep related state, invariants, and behavior together unless a new boundary reduces total cognitive load.
- Define errors and invalid states away when a stronger interface or invariant can remove caller ceremony.
- Name the abstraction by domain purpose, not mechanism.
- Add a module, helper, facade, option, or seam only when it hides more complexity than it introduces.
- For a non-trivial interface, compare at least two plausible shapes before choosing.

Stop when further restructuring no longer reduces caller knowledge, change amplification, or hidden dependencies.

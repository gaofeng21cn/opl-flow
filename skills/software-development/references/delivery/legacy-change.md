# Apply The Legacy Code Lens

Gain control before redesigning:

1. State the requested behavior change and behavior that must remain.
2. Identify the change point and the nearest observable effect.
3. Characterize uncertain behavior with the smallest reliable test or observation path.
4. Create the smallest seam needed for sensing or substitution.
5. Break only the dependency that blocks feedback: construction, global state, time, environment, framework object, I/O, or hard collaborator.
6. Make the behavior change, verify it, then refactor locally.

Keep behavior changes separate from broad cleanup. Use sprout/wrap or extraction techniques only as temporary change-enabling moves, and remove test-only or subclass tricks when safer structure exists.

Do not launch a rewrite merely because the current design is unpleasant.

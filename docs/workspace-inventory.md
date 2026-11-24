# Read-only workspace inventory

`scripts/fleet/workspace_inventory.py` discovers normal Git checkouts
and linked worktrees beneath caller-selected local roots. It groups independent
clones by normalized remote identity and distinguishes them from worktrees that
share the same Git common directory. Remote credentials are never returned.

The caller supplies its existing maintenance profile and optional custody
receipts. Discovery does not add repositories to that profile, fetch, update,
remove, or claim ownership of any checkout. A custody receipt identifies its
recorded owner; it does not establish that a chat is currently executing.

The scan stops at checkout roots and skips dependency, build and model trees,
symlinks and cross-filesystem children. Overlapping scan roots are deduplicated.
Unreadable or invalid Git checkouts remain explicit failures. Missing declared
paths and unregistered checkouts remain separate findings.

Size measurement is opt-in because dependency trees can be expensive to walk.
It uses allocated directory blocks and does not estimate reclaimable space;
hard links and APFS clones can overlap. Bind any later cleanup to a fresh,
reviewed exact set with current source, caller, custody and recovery evidence.

Keep one stable primary checkout per maintained repository. Use the native
Codex worktree/Handoff path or Git worktree lifecycle for parallel development.
On task completion, retain useful results and necessary evidence, verify
canonical absorption or explicit retirement, then close the owned worktree.
Build output and evidence belong to their owning project, outside worktree
pools. Third-party patch checkouts remain temporary task inputs.

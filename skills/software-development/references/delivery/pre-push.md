# Select Pre-Push Evidence

Use the delivery guide as the owner. This reference selects evidence for an
outgoing change; it does not grant push, force-push, PR, merge, release, or
deployment authority.

## Inspect The Outgoing Scope

Confirm the repository, branch or detached state, dirty paths, and live remote
base or stack parent. Fetch the verified base and inspect the complete committed
and dirty task-owned change against its merge base. Rerun scope selection after
a base merge, retarget, rebase, or generated-output change.

## Choose The Narrowest Sufficient Checks

Every behavior change needs the narrowest available check that would fail for
its regression. Expand only when the changed contract or blast radius requires
it.

- Run the owning focused test for package, module, or script behavior; add
  adjacent consumers when a shared contract changes.
- Run documentation, generator, link, language-pair, lint, and formatting gates
  for their affected sources.
- Run snapshots or real scenarios for model-, CLI-, terminal-, or UI-visible
  output.
- Run build and real-entry smoke checks for manifests, exports, loaders, bins,
  workers, subprocesses, generated artifacts, and packaged paths.
- Run real-provider or end-to-end checks only when credentials and authority are
  available; never expose secrets or call an unavailable check passed.

Do not repeat a passing check only because commit or push follows. Run a full
local rehearsal only when the user requests it, a CI failure requires it, or no
narrower set credibly covers a genuinely cross-cutting diff.

## Protect Rewritten History

Before an authorized standalone history rewrite, fetch the remote branch and
record its exact OID. Publish only with `--force-with-lease=<branch>:<oid>` or a
platform-native stack command that supplies equivalent lease protection. Never
use raw `--force`. After rewriting, re-fetch heads and re-evaluate review
threads, approvals, mergeability, checks, and changed scope.

## Finish

Stop on a relevant failure unless the user explicitly authorizes a documented
hook bypass. After an authorized push, fetch and verify the remote ref equals
local `HEAD`; inspect remote CI when a PR exists and report pending checks as
pending. A successful push does not prove canonical merge or release.

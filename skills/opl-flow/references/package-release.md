# Package Release

Use the bundled `scripts/package_release.py` instead of manually rebuilding
cross-repository inputs and readbacks. It has no persistent state and performs
no Git commit, tag, or Profile write.

## Authorities

- Owner canonical `main` and annotated `v<version>` select the source bytes.
- Framework canonical `main` selects the generated Package projection.
- The protected `publish-package.yml` workflow owns immutable OCI publication
  and `latest-stable` advancement.
- Codex Plugin Manager owns installed carrier bytes. The user's
  `~/.codex/AGENTS.md` remains user-owned.

Keep single-writer, immutable-version, predecessor/CAS, receipt, attestation,
and public readback gates. These protect a public mutation; do not expand them
into a database, lock service, rollback system, or second receipt.

## Three Actions

Resolve `<opl-flow-skill>` to the loaded Skill directory, then run from the
Package owner repository with absolute roots:

```bash
python3 <opl-flow-skill>/scripts/package_release.py prepare \
  --package-id <id> --owner-root <owner> --framework-root <framework>
```

`prepare` requires a clean owner checkout at fresh `origin/main` and an
annotated release tag selecting `HEAD`. Review and absorb its three generated
Framework files before publication.

```bash
python3 <opl-flow-skill>/scripts/package_release.py publish \
  --package-id <id> --framework-root <framework>
```

`publish` requires clean Framework `HEAD == origin/main`. It reads the current
predecessor, dispatches one protected workflow, reconciles an unknown dispatch
by request id, formally approves the one exact pending `release-stable`
deployment through the authenticated GitHub reviewer, verifies the receipt,
immutable and `latest-stable` digests, and both attestations, then reports
queue, job, and total seconds. Fail immediately on another pending environment,
multiple pending deployments, or missing reviewer authority.

```bash
python3 <opl-flow-skill>/scripts/package_release.py activate \
  --package-id <id> --framework-root <framework> \
  --opl-bin <canonical-framework>/bin/opl
```

`activate` delegates marketplace refresh and carrier update to Framework once,
then reads back the enabled Plugin version, required Skills, single-Package
status, and default Profile delta as a compact summary. It reports
`profile_merge_required` and a diff when the default changed; merge user Profile
content semantically outside the script. Start a fresh Codex executor when
discovery is required.

## Terminal Readback

Do not call a release complete before the same owner and Framework commits bind
the public immutable digest, `latest-stable`, attestation subject, installed
Plugin version, required Skills, and Profile delta. Close owned worktrees only
after canonical remote parity and installed/public readback.

# Package Release

Use the bundled `scripts/package_release.py` instead of manually rebuilding
cross-repository inputs and readbacks. It has no persistent state and performs
no Git commit, tag, or Profile write.

## Authorities

- Owner canonical `main` selects source bytes; a published release additionally
  requires an annotated `v<version>` tag.
- Framework canonical `main` selects the release Package projection; an explicit
  external projection selects a local source installation.
- The protected `publish-package.yml` workflow owns immutable OCI publication
  and `latest-stable` advancement.
- Codex Plugin Manager owns installed carrier bytes. The user's
  `~/.codex/AGENTS.md` remains user-owned.

Keep single-writer, immutable-version, predecessor/CAS, receipt, attestation,
and public readback gates. These protect a public mutation; do not expand them
into a database, lock service, rollback system, or second receipt.

## Standard Agent Distribution

MAS, MAG, RCA, OMA, OPL Book Forge, and Med Auto Cast use OCI as their sole
Package publication channel. Do not create or retain separate GitHub Release
pages or assets for these six Agents. Keep annotated source tags for immutable
source binding, and publish through the shared Package workflow. Do not create
a parallel ZIP or wheel publisher in an Agent repository.

READMEs provide the standard `opl packages install <package-id> --json` entry
and the OCI repository. Changes remain in repository documentation and Git
history. Domain qualification is separate from Package publication. This rule
does not apply to App products with independently distributed installers.

## Local Source Preparation

Use `prepare-source` to prepare a local source installation before publication.
Both the owner and Framework checkouts must be clean, with each `HEAD` equal to
its fresh `origin/main`. The command rechecks their cleanliness and exact commits
after generation. It keeps the owner's Package and Plugin identities and binds
the exact source commit and content locks through the existing projection and
payload generators. It does not require or create a tag, publish an OCI artifact,
or advance `latest-stable`.

Resolve `<opl-flow-skill>` to the loaded Skill directory and supply absolute
roots:

```bash
python3 <opl-flow-skill>/scripts/package_release.py prepare-source \
  --package-id <id> --owner-root <owner> --framework-root <framework> \
  --output-root <new-external-output-root>
```

The output root must not exist and must be outside both source trees. The command
exports the committed Framework projection baseline for dependency resolution,
updates only the selected Package, and atomically creates `packages/` and `allowlists/` below
that root. Each invocation produces a complete independent set. For several
Packages, choose a separate new root for each, such as `<output-parent>/<id>`;
do not accumulate preparations in one output directory.

The result reports `package_projection_dir`, `payload_sha256`,
`owner_source_commit`, `framework_source_commit`, and the native selector, with
publication and native mutation both false. Preparation alone does not install the Package. Preserve
this output for the intended installation and its readback; the Framework
release projection remains unchanged.

For an authorized native installation, set `OPL_PACKAGE_PROJECTION_DIR` to the
returned `package_projection_dir` (`<output-root>/packages`), select
`OPL_MODULE_SOURCE_MODE=git_checkout`, and provide the exact owner checkout using
`OPL_MODULE_PATH_<PACKAGE_ID>` with punctuation removed and letters uppercase.
For example, update an installed OPL Book Forge carrier with:

```bash
OPL_PACKAGE_PROJECTION_DIR=<output-root>/packages \
OPL_MODULE_SOURCE_MODE=git_checkout \
OPL_MODULE_PATH_OBF=<owner> \
<framework>/bin/opl packages update obf --json
```

Use `packages install obf` if the Package is absent. The native lifecycle keeps
the declared Package/Plugin identity and verifies the selected source bytes
against the prepared payload; it owns carrier writes and fresh installed
readback. Local activation is evidence of that source installation, not a
published release. Keep the same projection and source selection for subsequent
readback of this installation.

## Three Release Actions

Resolve `<opl-flow-skill>` to the loaded Skill directory, then run from the
Package owner repository with absolute roots:

```bash
python3 <opl-flow-skill>/scripts/package_release.py prepare \
  --package-id <id> --owner-root <owner> --framework-root <framework>
```

`prepare` requires a clean owner checkout at fresh `origin/main` and an
annotated release tag selecting `HEAD`. It resolves the canonical owner manifest
and carrier descriptor through Framework publication refs and the payload
allowlist, verifies their committed identities, and refreshes owner capability,
dependency and content-lock fields. Presentation inherits missing fields from
the central projection; each explicitly declared owner field replaces its
central value, including empty values, without merging nested values.
A missing owner `source_repo` does not waive
the binding between origin, Framework projection and payload allowlist. Existing
same-version payload bytes remain immutable. Review and absorb the generated
Package and payload files, plus the allowlist when content-lock paths changed,
before publication.

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
multiple pending deployments, or missing reviewer authority. When the local
registry read is denied, the same protected workflow resolves the predecessor
with its authenticated Package credential before any publication. Denial is
never absence; unresolved authenticated reads stop publication.

A pending environment without required reviewers continues through the same run
watch. If an approval write has an unknown outcome, Flow only reads that run back;
it never repeats the approval POST or dispatches another run during reconciliation.

For an `authorized_only` Package, `publish` reads the private owner's publisher
wrapper at its fresh `main` commit and dispatches that repository with the
wrapper's four declared inputs. Both fixed Framework pins must agree, select a
known ancestor of canonical Framework `main`, and contain the same selected
Package release identity, access policy, and payload bytes. Presentation changes
and unrelated Framework updates do not require
repinning the wrapper. The owner caller commit, Package source commit, and pinned
Framework commit remain separate; workflow and receipt readbacks bind each to the
requested publication. The wrapper uses the registered mapping/scalar YAML form;
duplicate keys, aliases, or other unsupported YAML forms fail before dispatch.

Private publication uses the configured software source's credential handle.
Disabled sources and missing credentials stop before dispatch. The private owner
publisher resolves the predecessor with its authenticated identity, so a private
registry's masked 404 cannot become an absence assertion. Flow reads the private
OCI receipt through Framework's shared verifier and trusted signing key, with
credentials confined to a short-lived process and temporary registry config.
The trusted key is `contracts/opl-framework/keys/private-packages/<package_id>.pub`
when present; only Packages without that file use the legacy
`contracts/opl-framework/keys/private-package-signing.pub`. An invalid Package
identity stops before credential access. Verification with a Package key never
retries with the legacy key after failure.
The verified receipt must match the request, predecessor, pinned Framework
commit, owner repository, and workflow run. Private receipts are not downloaded
from Actions, and public keyless verification is not used for private Packages.

```bash
python3 <opl-flow-skill>/scripts/package_release.py activate \
  --package-id <id> --framework-root <framework> \
  --opl-bin <canonical-framework>/bin/opl
```

`activate` reads Framework Package status and calls its official install or
update entrypoint. It requires a real installed carrier descriptor, the expected
version, available source files and callability; a source-checkout projection
cannot substitute for installation. Required providers absent from the native
carrier are installed explicitly, then checked against the fresh consumer
dependency binding and their installed content locks.

Interactive Plugins remain enabled. Headless capabilities remain disabled in
Codex's conversational surface and must expose Framework projection callability;
their exported core Skills and content bytes are checked without enabling them.
An installed carrier with unresolved overall readiness is reported as
`installed_with_readiness_debt`. This does not establish overall or domain
readiness. For a Package with a Profile, report `profile_merge_required` and a
diff when the default changed; merge user Profile content semantically outside
the script. Start a fresh Codex executor when discovery is required.

## Terminal Readback

Do not call a release complete before the same owner and Framework commits bind
the public immutable digest, `latest-stable`, attestation subject, installed
Plugin version, required Skills, and Profile delta. Close owned worktrees only
after canonical remote parity and installed/public readback.

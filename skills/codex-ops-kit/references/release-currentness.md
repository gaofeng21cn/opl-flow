# GitHub Release Evidence

Use this playbook only for public GitHub release URLs, release assets, and exact install commands.

Derive the canonical repository from `git remote get-url origin` and check every scanned release tag and asset with live `gh release view` readback:

```bash
python3 scripts/release_url_audit.py --repo .
```

Limit scanning when the published surface is elsewhere:

```bash
python3 scripts/release_url_audit.py --repo . --paths README.md docs/install.md --tag <tag>
```

To claim an exact public install command works, execute that command in an isolated temporary home:

```bash
python3 scripts/release_url_audit.py --repo . \
  --command '<published command>' --run-command
```

Treat missing `gh`, failed remote readback, non-GitHub origin, repo/tag/asset mismatch, or command failure as blocked. Report the checked tag, assets, command status, and remaining gaps.

Do not use this audit to infer runtime readiness, deployment state, credential freshness, cache freshness, realtime sync, or owner acceptance; use the owning runtime or release authority for those claims.

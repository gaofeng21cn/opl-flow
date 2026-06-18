# Release And Currentness

Use this playbook before changing release notes, installer scripts, README install commands, public install instructions, realtime/synced/latest/fresh claims, or cache-backed status claims.

## Release And Install Claims

Audit the canonical GitHub slug from `git remote get-url origin`, not stale docs or chat text:

```bash
python3 scripts/release_url_audit.py --repo .
```

When claiming a one-command install works, run the exact command in a temporary home:

```bash
python3 scripts/release_url_audit.py --repo . --command '<published command>' --run-command
```

## Secret And Cache Freshness

For tools relying on credentials, remote sync, or local caches, run a secret-safe preflight before claiming currentness:

```bash
python3 scripts/secret_freshness_preflight.py --env TOKEN_NAME --cache /path/to/cache --max-age-seconds 3600 --realtime-probe '<safe command>'
```

Allowed result classes are `realtime`, `cache`, and `blocked`.

Report `latest`, `synced`, `fresh`, or `current` only when fresh evidence supports that exact class. If a realtime probe fails, state the cache boundary or blocker explicitly.

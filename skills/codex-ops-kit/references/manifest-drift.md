# Manifest And Drift

Use this playbook for broad edits, cross-repo changes, generated files, installed config, runtime projections, and surfaces where source of truth can drift.

## Transaction Manifest

Use a manifest before broad multi-file, cross-repo, or config edits where a partial patch would be hard to reason about:

```bash
python3 scripts/change_manifest.py template > /tmp/change-manifest.json
python3 scripts/change_manifest.py preflight --repo . --manifest /tmp/change-manifest.json
python3 scripts/change_manifest.py status --repo . --manifest /tmp/change-manifest.json
```

If preflight disagrees with current files, update the plan or manifest before widening the patch.

## Source-Truth Drift

Before editing a failing file, classify it as one of:

- source of truth,
- generated artifact,
- installed config,
- runtime projection,
- one-time migration target.

For generated, installed, reconciled, or runtime-projected files:

1. Locate the generator, installer, reconcile command, doctor, or runtime owner.
2. Fix the owner surface.
3. Verify through the owner command or runtime output.
4. Treat emitted files as verification output or explicit migration artifacts.

Do not claim a persistent fix after hand-editing only generated config.

# OPL Flow Brand Assets

`opl-flow-logo.png` is the product mark. `opl-flow-coordination.png` is the
master public coordination diagram used by both repository READMEs.

The [Flow whitepaper](../../docs/whitepapers/opl-flow-whitepaper.md) owns the
product model; [workflow architecture](../../docs/reusable-workflow-architecture.md)
and [Fleet architecture](../../docs/opl-fleet-architecture.md) own technical
boundaries. The diagram presents Router, Worker, Ledger, and Fleet as four
responsibilities. Local execution is the primary path, Ledger preserves ongoing
work, and Fleet provides execution support when needed. Human views connect to
Ledger; artifacts and evidence remain with their respective owners.

Maintain the PNG here and export the profile repository's WebP from that same
image. For sibling checkouts:

```bash
cwebp -q 90 -m 6 assets/branding/opl-flow-coordination.png \
  -o ../gaofeng21cn/assets/branding/opl-flow-coordination.webp
```

Keep the hand-drawn black ink, teal and blue palette, legible English labels,
and clear separation of the work loop from optional execution support.

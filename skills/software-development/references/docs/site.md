# Synchronize A Documentation Site

Use `governance.md` for document ownership and meaning. Discover the target
repository's actual site generator, manifest, navigation, locale, and build
contracts; do not assume VitePress, a fixed `docs.ts`, or DeepSeek Harness
paths.

## Keep One Editable Source

- Edit canonical repository Markdown or the owning content source.
- Treat generated site trees, caches, and distributions as disposable output.
- For a new page, add its owning source and one explicit manifest/navigation
  entry when the site requires one.
- For a rename, move or removal, update source, manifest, aliases or redirects,
  and every inbound repository link atomically.
- Preserve the repository's bilingual pairing and locale rules; do not invent
  locale directories or duplicate routes.
- Change generators or source metadata instead of hand-editing generated
  catalogs.

Before editing a manifest, read its current schema and the site's navigation
configuration. Keep canonical Markdown links repository-relative; let the
projector translate them. Do not add deployment, hosting, permissions, or
public publication merely because a site projection changed.

## Verify The Projection

Run the repository's focused docs check, link and fragment checks, generator or
site build, language-pair check, lint, and `git diff --check` as applicable.
Verify the generated route, source mapping, inbound links, and representative
rendered page from the same source revision. Report source, projection, and
public deployment as separate states.

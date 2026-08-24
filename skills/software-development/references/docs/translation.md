# Translate A Documentation Pair

Run this extended workflow only when the user explicitly requests a bilingual
documentation pair. Routine small translations follow the target repository's
ordinary documentation rules. Use `governance.md` for authority and current-state
claims, and the target repository's own pairing and terminology contract for
the actual language decision.

## Classify The Change

- Existing pair with one side changed: generate or inspect the repository's
  narrow diff briefing and update only the affected counterpart units.
- New pair: read the pairing, terminology, style, and source-of-truth rules and
  translate the whole document while preserving structure.
- Renamed or deleted document: rename or delete its counterpart and consistency
  record atomically.

Never retranslate unchanged prose for a narrow update. Preserve code spans,
links, headings, list and table structure, modality, warnings, and every source
proposition. Both languages carry the document's meaning; wording must be
native, not word-for-word.

## Verify

Run the target repository's pairing record/update command, scoped pairing check,
docs/link/build checks, and `git diff --check`. Read each completed counterpart
alone and compare changed clauses against the source. Report pending terminology
or an unavailable pairing owner instead of inventing a second translation
memory.

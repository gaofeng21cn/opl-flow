# Local Skill Frontmatter Trigger Audit

Owner: `gaofeng`
Purpose: `local_skill_trigger_audit_provenance`
State: `historical_provenance`
Machine boundary: Frozen human-readable audit and implementation provenance. The
counts and local discovery observations below are not current inventory or
readiness truth; use canonical Skill sources, plugin/package policy, and fresh
Codex discovery for current state.
Date: 2026-07-12

## Scope And Counting

Scanned roots:

- `~/.codex/skills`
- `~/.agents/skills`
- `~/.skills-manager/skills`
- `~/.codex/plugins/cache`

The scan found 164 physical `SKILL.md` frontmatters representing 154 unique names. Ten names have two physical copies. A cache file is not automatically runtime-active: disabled plugin caches are listed separately from currently discoverable skills.

Risk means likely interference with model-native reasoning, not whether the skill itself is useful:

- `high`: broad automatic wording or multiple active skills can match the same ordinary request.
- `medium`: useful narrow procedure, but the trigger still contains an automatic gate or overlaps one neighbor.
- `low`: explicit request, selected template, or genuinely narrow domain trigger.
- `cache-only`: physically present but its owning plugin is currently disabled; no immediate trigger risk.

## Priority Findings

| Skill or cluster | Current trigger issue | Risk | Recommended action for a later change |
| --- | --- | --- | --- |
| `agent-reach` | Says `MUST USE` for any internet lookup, any named platform, and even any shared URL. | high | Trigger only on explicit multi-source/platform research or when its specialist backend is needed. A URL alone should not activate it. |
| `agent-browser` | Covers all web interaction, scraping, QA, bug hunts, Electron apps, Slack, cloud browsers, and says to prefer it over built-ins. | high | Limit to explicit terminal browser automation, Electron automation, or a named `agent-browser` request. Remove the blanket preference. |
| Browser cluster | `agent-browser`, `playwright`, `control-in-app-browser`, `agent-reach`, and `defuddle` overlap. | high | Give each one exclusive intent: signed-in visible UI, local browser testing, terminal/Electron automation, multi-source research, or clean article extraction. |
| Office/PDF cluster | Official `documents`/`Presentations`/`Spreadsheets`, the OfficeCLI family, MinerU, and PDF skills all match common document requests. | high | Pick one default file-editing family. Make OfficeCLI explicit/high-fidelity only; MinerU OCR/extraction only; PDF layout/render only. |
| `officecli-docx`, `officecli-pptx`, `officecli-xlsx` | Each says “any time” its file type or broad words such as report, deck, spreadsheet, dashboard, or tracker appear. | high | Require an actual file type/path or explicit OfficeCLI request; generic content words must not trigger. |
| `sites-building` / `sites-hosting` | Broad website categories, with “Always use” for Sites-owned projects and automatic chaining into hosting. | high | Keep the `.openai/hosting.json` owner rule, but otherwise require an explicit Sites build/publish intent. |
| OPL domain duplicate entries | MAG, BookForge, and RCA each have package/runtime projection copies. MAG copies already disagree about whether `mag` or `med-autogrant` is canonical. | high | Fix plugin generation/install ownership and expose one canonical public entry. Do not patch generated caches independently. |
| MAS ScholarSkills pack | Intended policy is workspace/quest-only (`codexDefaultExposure: false`), but the local plugin is globally enabled and all subskills are visible from the `opl-flow` cwd. | high installation drift | Keep the skill content and workspace/quest sync design. Remove the global plugin exposure so runtime matches the existing policy; no router-first rewrite is needed. |
| `codex-ops-kit` | Contains useful deterministic Git/GitHub scripts, but remains in `GUARDRAIL_SKILLS`, plugin required files, and strict blocking readiness despite being described as optional. | high core coupling | Remove it from OPL Flow core/readiness. Keep the scripts as a separate explicit tool or optional skill for a requested lane/public-release audit. |
| `zoom-out` | Short perspective prompt with `disable-model-invocation: true`. | low | Retain unchanged; it is already explicit and cannot auto-trigger. |
| `prototype` | Contains useful logic/UI prototype branches and is triggered by explicit prototype/playable-design intent. | low | Retain; ordinary design uncertainty should continue model-native. |
| `external-learning-landing` | Can upgrade learning from a repo/paper/workflow into a local governance landing. | medium | Current “local adoption intent” exclusion is good; strengthen to explicit adoption/mapping request. |
| `evidence-bound-closeout` | Automatically activates before certain artifact completion claims. | medium | Keep only for exact-byte generated deliverables where identity binding matters; do not apply to ordinary code completion. |
| `book-legacy-code` | Risky work in unclear/weakly tested code can be interpreted broadly. | medium | Require an actual construction/testing obstacle or explicit legacy-code request. |
| `systematic-debugging` | Automatic after repeated/flaky/cross-component failure or a failed fix; body is generic debugging reasoning with no unique tool. | medium | Remove from automatic discovery; retain only as an explicit method. |
| `test-driven-development` | Automatically includes durable contracts, permission boundaries, and irreversible writes; body is generic red-green-refactor guidance. | medium | Explicit TDD/test-first only. |
| `verification-before-completion` | Automatic for high-risk runtime/release/authority claims; body is a generic evidence checklist. | medium | Explicit independent audit only. |
| `ui-ux-pro-max` | Previously broad, now explicit or limited to system-level visual/UX work. | low | Retain current narrowed frontmatter. |
| `superpowers-lite` | Explicit-only umbrella. | low | Retain. Superpowers is not packaged by OPL App and has no automatic plugin bootstrap. |

## Private Design And Development Skill Body Review

This section reflects full-body review, not frontmatter-only classification.

| Skill | What the body actually adds | Necessity verdict |
| --- | --- | --- |
| `codex-ops-kit` | Three deterministic scripts: Git/worktree state, patch absorption classification, and live GitHub release/install audit; 536 lines total plus two short references. OPL Flow still treats absence as strict failure. | Keep capability outside OPL Flow core; remove automatic workflow/readiness role. Explicit audit only. |
| `evidence-bound-closeout` | Exact-file fingerprint plus post-fingerprint QA script. | Keep as explicit exact-byte artifact utility. Not an ordinary completion phase. |
| `agent-browser` | Version-matched CLI skill loading, accessibility-tree refs, Electron/Slack/cloud-browser backends. | Keep tool; narrow frontmatter to named CLI/Electron/backend need. |
| `playwright` | Concrete wrapper, snapshot/ref workflow, trace and multi-tab commands. | Keep tool; use for reproducible terminal browser/UI-flow testing. |
| `agent-reach` | Multi-platform backend router, health checks, retry references, update checks, and platform commands. | Keep tool but make explicit multi-platform/platform-backend research only. Remove URL-alone and routine web-search triggers. |
| `defuddle` | One focused clean-page extraction command. | Keep; supplied article/docs URL extraction only. |
| `OfficeCLI` base and file skills | Extensive DOM/CLI manuals, renderer caveats, formula/layout rules, and artifact QA. | Keep capability. Narrow generic words; decide one default Office family. |
| OfficeCLI scene skills | Academic paper, dashboard, financial model, and pitch-deck domain recipes with real deliverable checks. | Keep; their named scenarios are sufficiently specific. |
| `mineru-document-extractor` | Actual OCR/table/formula/batch CLI, token modes, limits, and privacy metadata. | Keep; OCR/complex extraction only, not ordinary Office editing or simple web reading. |
| `pdf` | Poppler render plus PDF generation/extraction workflow. | Keep; layout-sensitive PDF work only. |
| `ui-ux-pro-max` | Searchable design database and scripts. The body is broad and prescriptive, but frontmatter now excludes routine UI work. | Keep current explicit/broad-design trigger. Do not load for normal component implementation. |
| `cli-creator` | Durable CLI contract, auth/config, JSON, install and smoke-test patterns. | Keep for explicit durable CLI creation; not for ordinary repo scripts. |
| `academic-defense-prep`, `hatch-pet` | Specialized deliverable schemas, assets, scripts, and QA. | Keep; genuine domain capabilities. |
| `prototype` | Two concrete branches with referenced runnable logic/UI templates. | Keep explicit; it provides artifact patterns beyond generic reasoning. |
| `grill-with-docs` | One-question-at-a-time design interview plus CONTEXT/ADR formats. | Keep explicit-user-only. It intentionally changes interaction style. |
| `improve-codebase-architecture` | Ranked architecture-candidate method plus vocabulary/reference material. | Keep for explicit architecture-audit requests; no automatic use. |
| `zoom-out` | Seven-line user-invoked perspective prompt; auto invocation disabled. | Keep unchanged. |
| APoSD/Clean Architecture/DDD lenses | Compact book-derived comparison criteria; all explicitly triggered. | Keep unchanged as optional named lenses. |
| `book-ddia`, `book-release-it` | Compact failure/data-semantics checklists with useful narrow exclusions. | Keep current narrow automatic domain triggers or make explicit if zero methodology routing is desired. |
| `book-legacy-code` | Generic six-step characterize/seam/change method, no unique tool. | Make explicit-only or retire from default discovery; GPT-5.6 can reason this natively. |
| `external-learning-landing` | Governance classification and owner-surface landing procedure, no unique tool. | Make explicit adoption-governance only; do not trigger on ordinary external learning. |
| `systematic-debugging` | Generic reproduce/hypothesis/root-cause workflow, no unique tool. | Remove from automatic discovery; retain only through explicit Superpowers/debug-method request. |
| `test-driven-development` | Generic red-green-refactor selection gate, no unique tool. | Explicit TDD/test-first only. Do not auto-trigger from contract/API/permission keywords. |
| `verification-before-completion` | Generic five-step evidence gate, no unique tool. | Explicit independent audit only; ordinary completion remains model-native. |
| `superpowers-lite` | Explicit router to the three generic method skills. | Keep explicit umbrella; no automatic bootstrap. |

## Overlap Matrix

### Browser And Web

| Entry | Intended owner after cleanup | Assessment |
| --- | --- | --- |
| `control-in-app-browser` | Existing signed-in in-app browser state and visible UI operations | keep |
| `playwright` | Explicit terminal-driven local web testing and reproducible browser flows | keep, narrow overlap |
| `agent-browser` | Explicit terminal/Electron/cloud-browser automation | narrow frontmatter |
| `agent-reach` | Explicit multi-platform internet research and specialist platform fetch | narrow frontmatter |
| `defuddle` | Clean readable extraction from a supplied article/docs URL | keep |
| `sites-building` | Sites-owned project implementation | narrow non-Sites trigger |
| `sites-hosting` | Explicit Sites publish/hosting operation | narrow chaining trigger |

`control-chrome` and `computer-use` are physically cached but currently disabled. They are not an immediate runtime trigger risk.

### UI And Product Design

| Entry | Status | Assessment |
| --- | --- | --- |
| `ui-ux-pro-max` | current local skill | low risk; explicit/system-level only |
| `prototype` | current local skill | low; explicit prototype intent and useful artifact branches |
| `frontend-skill` | disabled `build-web-apps` cache | cache-only; broad if enabled later |
| `web-design-guidelines` | disabled `build-web-apps` cache | cache-only; user-requested audit trigger is reasonable |
| `react-best-practices` | disabled `build-web-apps` cache | cache-only; broad for any React edit if enabled |
| `shadcn` | disabled `build-web-apps` cache | cache-only; project marker gives a useful narrow boundary |

### Office, PDF, And Extraction

| Entry | Intended owner after cleanup | Assessment |
| --- | --- | --- |
| `documents`, `Presentations`, `Spreadsheets` | default creation/editing for their native artifact type | choose as one default family |
| `officecli` | explicit OfficeCLI umbrella | make explicit-only or remove umbrella |
| `officecli-docx`, `officecli-pptx`, `officecli-xlsx` | explicit high-fidelity OfficeCLI operations | narrow “any time” wording |
| `officecli-academic-paper`, `officecli-data-dashboard`, `officecli-financial-model`, `officecli-pitch-deck` | exact named scenario | retain; already specialized |
| `mineru-document-extractor` | OCR, formulas, tables, scans, batch extraction | retain but do not trigger for ordinary Office editing |
| `pdf` | PDF rendering/layout inspection and generation | retain one discovered copy |
| `academic-defense-prep` | defense storyline/scripts/notes | retain; route file manipulation to one owner only |

### Development Methods

| Group | Skills | Assessment |
| --- | --- | --- |
| Explicit architecture lenses | `book-aposd`, `book-clean-architecture`, `book-domain-driven-design` | low; explicit-only |
| Narrow systems lenses | `book-ddia`, `book-release-it` | low; exclusions are clear |
| Legacy/risk methods | `book-legacy-code`, `systematic-debugging`, `test-driven-development`, `verification-before-completion` | medium to medium-low; already substantially narrowed |
| Explicit collaboration methods | `grill-with-docs`, `improve-codebase-architecture`, `superpowers-lite`, `ui-ux-pro-max` | low |
| Potentially broad helpers | `external-learning-landing`, `evidence-bound-closeout` | medium; make explicit as above |
| Explicit artifact/perspective helpers | `zoom-out`, `prototype` | low; retain |

## Duplicate Physical Names

These ten names each have two physical copies:

| Name | Duplication source | Recommendation |
| --- | --- | --- |
| `gh-address-comments` | local curated cache and remote GitHub plugin cache | do not edit caches; keep only the enabled/connected provider |
| `gh-fix-ci` | local curated cache and remote GitHub plugin cache | same |
| `github` | local curated cache and remote GitHub plugin cache | same |
| `yeet` | local curated cache and remote GitHub plugin cache | same |
| `gmail` | local curated cache and remote Gmail plugin cache | same |
| `gmail-inbox-triage` | local curated cache and remote Gmail plugin cache | same |
| `med-autogrant` | `mag-local` alias and `med-autogrant-local` public package | consolidate public entry |
| `opl-bookforge` | `obf-local` alias and `opl-bookforge-local` public package | consolidate public entry |
| `redcube-ai` | `rca-local` alias and `redcube-ai-local` public package | consolidate public entry |
| `pdf` | official Primary Runtime and Skills Manager copy | retain one enabled owner |

The GitHub/Gmail duplicates are provider/cache duplication, not necessarily two active unnamespaced triggers. Manual edits inside plugin cache would be overwritten by refresh and are not recommended.

## Low-Risk Domain Inventory

The following are narrow enough that frontmatter cleanup is not currently justified:

- System/local utilities: `imagegen`, `openai-docs`, `plugin-creator`, `skill-creator`, `skill-installer`, `skill-upgrader`, `screenshot`, `template-creator`, `texlive-runtime-installer`, `visualize`.
- Mail/personal workflows: `apple-apps`, `codex-mail-workbench`, `mail-triage`, `obsidian-tech-memo`, `travel-card-benefit-planner`, `xiaohongshu-repo-scout`.
- Specialized builders: `cli-creator`, `hatch-pet`, `opl-flow`, `opl-meta-agent`, `mas`, `med-autoscience`, `scientific-compute-runner`.
- Infrastructure/vendor: `stripe-best-practices`, `supabase-postgres-best-practices`, `temporal-developer`, `excel-live-control`.
- Security phase skills: `attack-path-analysis`, `deep-security-scan`, `finding-discovery`, `fix-finding`, `security-diff-scan`, `security-scan`, `threat-model`, `track-findings`, `triage-finding`, `validation`. Their phase or explicit-request boundaries are clear; the owning plugin is currently disabled.
- Selected artifact templates: all `artifact-template-*` entries trigger only when the user selects or names that template; their plugin cache is not currently active.

## MAS ScholarSkills Inventory

These are narrow and medically specific. The intended design materializes them into MAS work directories for project-scoped discovery. Current local runtime does not match that design: `mas-scholar-skills@mas-scholar-skills-local` is globally enabled, so this audit session in `opl-flow` received all plugin subskill frontmatters.

- Routers and planning: `mas-scholar-skills`, `medical-advanced-biomed-router`, `medical-methodology-planner`, `medical-protocol-and-sap-planner`, `medical-causal-inference-plan`, `medical-cohort-phenotyping`, `medical-survival-analysis-plan`.
- Data and readiness: `medical-data-governance`, `medical-data-freeze-and-analysis-readiness-reviewer`, `medical-risk-model-transportability-reviewer`, `medical-registry-atlas-story-architect`.
- Evidence and literature: `medical-research-lit`, `medical-evidence-synthesis-and-claim-map`, `medical-evidence-integrity-reviewer`, `medical-reference-integrity-auditor`, `research-pdf-evidence-explorer`, `medical-research-portfolio-memory-curator`.
- Writing and publication: `medical-manuscript-writing`, `medical-manuscript-review`, `medical-statistical-review`, `medical-submission-prep`, `medical-rebuttal-strategy`, `medical-publication-routeback-reviewer`, `medical-indication-dossier`.
- Figures and tables: `medical-display-qc`, `medical-display-regression-debugger`, `medical-figure-composer`, `medical-figure-design`, `medical-figure-style`, `medical-table-design`.
- Biomedical specialists: `medical-genomics-foundation-models`, `medical-protein-design`, `medical-single-cell-modeling`, `medical-structural-biology`.

Recommendation: retain the specialist content and existing workspace/quest sync policy. Remove or disable the global plugin installation, then verify from a fresh non-MAS Codex session that these subskills are absent. Revisit skill routing only if MAS workspace evidence shows ambiguity inside that domain.

## Implementation Result

Applied on 2026-07-12:

1. Narrowed `agent-reach`, `agent-browser`, and `defuddle` to explicit tool or unique-backend use; a URL or generic web task no longer triggers them.
2. Narrowed OfficeCLI base, DOCX, PPTX, and XLSX skills to explicit OfficeCLI or scene-skill routing. Kept the academic-paper, dashboard, financial-model, and pitch-deck scene triggers.
3. Narrowed MinerU to explicit use or OCR, scans, complex tables/formulas, and batch conversion.
4. Made `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `book-legacy-code`, `external-learning-landing`, `evidence-bound-closeout`, and `codex-ops-kit` explicit-only.
5. Removed the global `mas-scholar-skills@mas-scholar-skills-local` plugin and its stale cache. Workspace/quest sync remains the intended discovery route.
6. Removed global `mag@mag-local`, `mas@mas-local`, `rca@rca-local`, and `obf@obf-local` aliases and their stale caches. Retained the public `med-autogrant`, `med-autoscience`, `redcube-ai`, and `opl-bookforge` package plugins.
7. Deleted OPL Flow's companion checker and removed `codex-ops-kit` from profile/install readiness coupling while preserving its scripts as an explicit optional utility.
8. Deleted OPL Flow's independent CodexCont install/config/service lifecycle. Normal OPL Flow install/update now routes to OPL Framework package lifecycle; the repo-local installer is developer-only.

## Applied Change Order

The approved order was:

1. Narrow `agent-reach` and `agent-browser` frontmatter.
2. Establish one Browser/Web ownership matrix and one Office/PDF ownership matrix.
3. Fix OPL package/runtime duplicate generation at the owning source, starting with the contradictory MAG canonical-id copies.
4. Correct MAS ScholarSkills installation drift: preserve workspace/quest sync and remove global plugin exposure.
5. Make `codex-ops-kit`, `book-legacy-code`, `external-learning-landing`, `systematic-debugging`, TDD, and verification explicit-only.
6. Leave MAS specialist content, `zoom-out`, `prototype`, explicit book lenses, and narrow domain skills unchanged.

Canonical skill sources were edited first. Stale cache trees for removed plugins were deleted only after their plugin and marketplace registrations were removed.

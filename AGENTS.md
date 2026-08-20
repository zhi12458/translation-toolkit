# MPI Project Conventions

## Agent Instructions

You are working on the Mindful Peace International Chinese-English Buddhist/Dharma translation project.
- Before translating, load the `mpi-translation` and `mpi-terms-search` skills.
- Before reviewing, load `mpi-translation-review` (self mode for your own translations, other mode for peer review).
- The agent IS the translator: do not call external APIs to generate final
  English. Approved external models may analyze Chinese meaning or review an
  existing bilingual draft when `external_semantic_review: allow`; they never
  decide the final English wording.
- The workflow is not as rigid as the state machine below. The user may ask you to deviate from it. Be flexible when asked.

## Skills

Skills in `toolkit/skills/`.

Available: `mpi-translation`, `mpi-terms-search`, `mpi-translation-review`, `mpi-chinese-text-normalize`, `mpi-pptx-translate`, `mpi-pdf-to-docx-conversion`.

## Terms Database

See `mpi-terms-search` skill. Quick reference:
- CLI: `toolkit/terms-database/search.py <query> [limit]`
- Module: `from search import search; search("空性", limit=5, src="DoT定稿")`
- Priority: DoT定稿 > 内部特色词 > 佛教术语 > 经论名
- Default ordering is deterministic: exact Chinese match, longer/more-specific
  Chinese entry, source priority above, then SQLite rowid.

## Directory Structure

```
translate-files/<topic>/<article>/
  translation-project.yaml — source origin, delivery format, register, policy,
                             versions, release level
  term-map.yaml   — sense-specific term decisions and review state
  term-map.md     — legacy mechanical-gate format; new projects use YAML only
  source.dj      — Chinese original
  source-analysis.json — frozen blind Chinese source-meaning analysis; never
                         generated from or sent together with target.dj
  target.dj      — English translation (line count matches source)
  bilingual.dj   — canonical interleave (source line, target line, blank)
                   Generated with `gen-bilingual.py source.dj target.dj --output bilingual.dj`;
                   do not edit or commit.
  review-findings.jsonl — independent-review findings and resolution state
  semantic-review.json — final accuracy-review certificate bound to source and
                         target SHA-256 hashes
  qa-report.json  — generated PASS/WARN/SKIP/FAIL gate report; do not commit
```

Put `.docx` output in `/tmp/`. Don't commit binaries.
Generated files (`bilingual.dj`) are not committed either.

---

## Translation State Machine

Non-deterministic LLM work happens at the states; transitions are fixed.

| Current state | Event / condition | Next state | Notes |
|---|---|---|---|
| `*start*` | source loaded | `idle` | Begin from a new source. |
| `*start*` | bilingual loaded | `idle` | Begin from an existing review file. |
| `idle` | `SOURCE_LOADED` and blind analysis enabled | `source_analyzing` | K3 or an independent internal source-only role. |
| `idle` | `SOURCE_LOADED` and blind analysis skipped | `translating` | Record the policy reason. |
| `source_analyzing` | `SOURCE_ANALYSIS_FROZEN` | `translating` | Source hash and paragraph coverage verified. |
| `idle` | `BILINGUAL_LOADED` | `other_reviewing` | |
| `translating` | `TRANSLATION_DRAFTED` | `bilingual_ready` | |
| `bilingual_ready` | `BILINGUAL_GENERATED` | `self_reviewing` | |
| `self_reviewing` | `SELF_REJECTED` | `translating` | |
| `self_reviewing` | `SELF_APPROVED` and semantic review enabled | `semantic_reviewing` | V4 Pro or independent internal bilingual reviewer; blind to source analysis. |
| `semantic_reviewing` | `SEMANTIC_REJECTED` and repair cycles < 2 | `translating` | Apply confirmed meaning constraints, polish, then rerun. |
| `semantic_reviewing` | `SEMANTIC_REJECTED` after 2 cycles | `other_reviewing` | Blocking issues require human adjudication. |
| `semantic_reviewing` | `SEMANTIC_APPROVED` and peer review required | `other_reviewing` | Final certificate hashes match current files. |
| `self_reviewing` | `SELF_APPROVED` and only peer review required | `other_reviewing` | `release.independent_review_required` decides the branch. |
| `self_reviewing` | `SELF_APPROVED` and no peer review | `approved` | |
| `other_reviewing` | `PEER_REJECTED` | `translating` | |
| `other_reviewing` | `PEER_APPROVED` | `approved` | |
| `approved` | `TYPESET_REQUESTED` | `typesetting` | Optional. |
| `approved` | `COMPLETE` | `done` | |
| `typesetting` | `TYPESET_COMPLETE` | `done` | |

States:

: `idle` — Waiting for source or an existing bilingual file.
: `source_analyzing` — Reconstructing Chinese predicates, roles, relations, and
  scope without access to an English draft.
: `translating` — Draft `target.dj`.
: `bilingual_ready` — `bilingual.dj` generated from `source.dj` + `target.dj`.
: `self_reviewing` — Self-review with `mpi-translation-review` (self mode); edit `target.dj`.
: `semantic_reviewing` — Independent bilingual accuracy review, blind to the
  source-analysis artifact; merge findings and bind the review to file hashes.
: `other_reviewing` — Peer review with `mpi-translation-review` (other mode); write `review-findings.jsonl`.
: `approved` — Translation accepted; may typeset or finish.
: `typesetting` — Produce PDF/DOCX.
: `done` — Complete.

Peer review is not an informal model choice. Set
`release.independent_review_required: true` in `translation-project.yaml` for
public, scripture-dense, or doctrinally sensitive work. Those releases also
require `release.named_approver_required: true` and named human approval.

## Workflow A: Translation（翻译）

Translate Chinese source into English. The agent IS the model — no external APIs. This workflow covers the state machine path `idle` → `translating` → `bilingual_ready` → `self_reviewing`.

### Audited Codex strategy C

The distributable Codex strategy-C workflow is a strict specialization of
Workflow A. At the start of every run, read the parent `mpi-translations/AGENTS.md`,
this file, and the three MPI translation skills. Refuse to translate unless the
locked repository origins, Git SHAs, clean-worktree checks, and
`scripts/doctor.py --strategy-c` receipt all match the installation `READY.json`.

Use only this locked toolkit for source conversion, terminology search and
`term-map.yaml`, canonical source/target/bilingual management, DOCX rendering,
subtitle generation, and deterministic QA. The external orchestrator may
schedule Flash, Sol, and Pro and may record audit receipts, but it must not
contain fallback implementations of those toolkit responsibilities.

The enforced order is:

1. Run `docx2dj.py` or `source2dj.py` and freeze the resulting `source.dj` hash.
2. Run `terms-database/search.py` through `build-term-map.py`; stop for every
   `needs_human` term before English drafting.
3. Let DeepSeek V4 Flash `high` analyze only the frozen Chinese, project
   metadata, and term map through `deepseek-source-analysis.py`. It must not
   see or create `target.dj`.
4. Let the active GPT-5.6-Sol `medium` Codex agent write the English. It is the
   provisional default and the only English wording authority. Freeze its draft
   as canonical `target.dj` with `freeze-target.py`; do not let the orchestrator
   replace that validator.
5. Generate `bilingual.dj` with `gen-bilingual.py`, then let DeepSeek V4 Pro
   `max` review Chinese and English without seeing the Flash analysis.
6. Apply valid findings with Sol medium, regenerate `bilingual.dj`, and run Pro
   once more. If the second review still has title or critical/major blockers,
   Sol high may adjudicate only those findings. Stop for a human if any remain;
   never use high for an unrequested whole-text retranslation.
7. Run `check-translation.py --strict`; generate DOCX with `dj2docx.py` and
   verify both English and bilingual DOCX with `check-docx.py`; for media,
   generate and check subtitles with `gen-subtitles.py` and
   `check-subtitles.py`. For non-media, write a real `not_applicable` subtitle
   report with `check-subtitles.py --not-applicable`.

Every call above must pass through the strategy-C audit runner and appear in
the project `MANIFEST.json`. Missing or stale receipts are release failures.

### Source context

Before translating, distinguish `source_origin` from `delivery_format`. A talk
compiled into an article or book is publication prose even though its source is
oral: polished, written, warm, and restrained, without chatty contractions,
slang, or casual fragments outside quotations. Preserve first person,
rhetorical questions, reasoning sequence, simple analogies, and gentle voice.
Only transcript, subtitle, Q&A-dialogue, audio-script, and similar deliverables
should retain conspicuously spoken surface features. If either field is unclear,
ask the user before proceeding.

### Input

Source text in `.dj` or `.docx` (Chinese only).

### Deliverables

- `source.dj` — extracted/cleaned Chinese
- `source-analysis.json` — blind, hash-bound source-meaning analysis when the
  semantic-analysis stage is enabled
- `target.dj` — English translation, line count matches source
- `bilingual.dj` — interleaved (source line, target line adjacent, blank between pairs).
  Generated by `../../toolkit/scripts/gen-bilingual.py source.dj target.dj --output bilingual.dj`.
  Do not create or edit by hand; do not commit.
- `edit-suggestions.dj` — terminology/consistency issues flagged for review
- `translation-project.yaml` and a frozen `term-map.yaml`. The mechanical gate
  reads its JSON-compatible YAML 1.2 representation directly.
- `review-findings.jsonl` merged without deleting earlier review history, and a
  fresh `semantic-review.json` after the final accuracy review.
- `qa-report.json` from `check-translation.py . --strict --json --output qa-report.json` before release.

### Rules

1. Load `mpi-translation` and `mpi-terms-search` skills before starting.
2. Search terms DB for key Buddhist terms.
3. Titles and headings: translate the semantic head, modifiers, logical
   relation, and distinctions in a parallel series accurately. Prefer concise,
   immediately understandable English; publication formality must not add
   abstract scaffolding. Verify main title, TOC, and repeated body headings as
   a separate pass, with identical repeated renderings.
4. TOC: plain bullet lists, no link targets, no page numbers.
5. Djot formatting:
   - Emphasis: `*text*` (single asterisks). Never `**` (Markdown bold).
   - Comments: `{% ... %}`
6. Preserve source formatting — don't add/remove emphasis.
7. Translate in-response — never call external APIs to draft or polish the
   final English. External semantic-analysis/review calls follow the separate
   policy below.

### Four-stage semantic workflow

For projects that allow external semantic review, use this sequence. For
`release.level: sensitive` or `external_semantic_review: deny`, replace K3 and
V4 Pro with independent internal roles while preserving the same blind
separation and artifacts.

1. **Kimi K3 blind source analysis.** Run
   `scripts/kimi-source-analysis.py <project-dir>`. It may read only the full
   Chinese source, project metadata, and term map; it must never read or send
   `target.dj`. The validated, atomically written `source-analysis.json`
   records predicates, semantic roles and evidence status, clause relations,
   scope, reference/ellipsis, competing interpretations, and
   `must_preserve`/`must_not_invent`. A nullable or ambiguous role must not be
   filled simply to satisfy the schema. Production calls are serial with
   `reasoning_effort: high`, one paragraph per recoverable batch, and an
   effective concurrency of one. The client enforces the documented China
   Tier 1 budget (200 RPM, 2,000,000 TPM) locally and uses bounded backoff for
   HTTP 429; reserve `max` for a hard passage or an explicit performance test.
   If K3 exhausts its retry or elapsed-time budget, Qwen3.8-Max may be evaluated
   with `scripts/qwen-source-analysis.py <project-dir>` as a whole-document
   blind candidate, but it is not an automatic fallback until that exact
   account-visible model ID and endpoint pass the same gold set. It writes
   `source-analysis-qwen.json`; never mix Kimi and Qwen paragraph batches, and
   promote only one fully locally validated artifact.
2. **English drafting.** The translating agent reads Chinese, the frozen term
   map, and the hash-matching source analysis, then writes publication-quality
   English for publication deliverables. The analysis constrains meaning; it
   is not an English draft.
3. **DeepSeek V4 Pro independent accuracy review.** Run
   `scripts/deepseek-review.py <project-dir>`. It reads Chinese, English, term
   map, and project metadata, but never K3 output. It emits Chinese findings and
   meaning constraints, not final English wording. Long work is split into
   focused paragraph batches with adjacent read-only context; all batches must
   validate before new findings are merged atomically into
   `review-findings.jsonl`. Existing history is never replaced.
4. **English repair and written polish.** The translating agent applies only
   confirmed accuracy findings, then polishes the English for the declared
   delivery format. Run V4 Pro again after polishing. The final
   `semantic-review.json` source and target hashes must match the current files.
   After two automated repair cycles, any blocking finding goes to a human;
   do not continue a model rewrite loop.

K3 and V4 Pro are independent evidence sources, not voters. If they conflict,
retain both records and have a human adjudicate from the full context.

### External semantic-review policy and credentials

`translation-project.yaml` records `external_semantic_review: allow | deny`.
The default policy is allow, but sensitive projects always behave as deny. Do
not send a non-public manuscript through an exposed or unrotated credential.

- Kimi China: `https://api.moonshot.cn/v1`, model `kimi-k3`; read
  `KIMI_API_KEY`, then macOS Keychain service `mpi-kimi-review`.
- DeepSeek: `https://api.deepseek.com`, model `deepseek-v4-pro`; read
  `DEEPSEEK_API_KEY`, then macOS Keychain service `mpi-deepseek-review`.

The scripts do not accept keys on the command line, print credentials, store
them in project files, or echo provider response bodies in error messages.
Kimi uses strict JSON Schema subject to the provider's MFJS subset. DeepSeek's
standard JSON mode guarantees JSON syntax only, so its output is always
validated locally before any file is changed.

### Review

After translating, load `mpi-translation-review` (self mode) to check:
- Full detection rules (three passes + R1–R14 editorial polish)
- Terminology consistency against terms DB
- Grammar, fluency, calques
- Missing content (mid-paragraph truncation)
- Inconsistency (same term translated differently)

For M Strategy runs, Flash source analysis must also enumerate
`cultural_allusions` for every nonblank source line. This includes idioms,
proverbs, classical quotations, canonical or historical allusions, scriptural
quotations, and fixed classical expressions. Every declared item requires an
audited external-research decision before Sol translation. The independent Pro
review must check the contextual sense again without reading Flash analysis.
The regression phrase `独善其身` must be treated as a Mencian expression whose
classical self-cultivation/integrity sense is distinct from its later
self-interested pejorative sense.

### Strategy M semantic gates

For audited Strategy M runs, the locked source-analysis and bilingual-review
interfaces are mandatory in addition to ordinary translation QA:

- Flash must record high-risk time and aspect relations separately in
  `temporal_relations`. Source markers such as `时`, `后`, `才`, `已`, `仍`,
  and `再` must also appear verbatim in `must_preserve`; local validation
  rejects missing coverage.
- For Buddhist aphorisms, compact classical clauses, parallel formulas, and
  ellipsis, Flash must populate `elliptical_subject` and keep agent, cause,
  instrument, and state-holder roles distinct. An explicit cause must not be
  promoted to the acting or state-bearing subject.
- Each independent Pro review must return one `paragraph_audits` record per
  nonblank source paragraph, separately checking temporal/aspect, condition,
  negation, degree, elliptical subject, and semantic roles. A certificate with
  missing paragraph coverage cannot pass strict QA.
- Main title and every heading for semantic accuracy, plainness, concision,
  parallel structure, and exact TOC/body consistency

---

## Workflow B: Proofread / Review（校对/审阅）

Both self-mode and other-mode review use the unified `mpi-translation-review` skill.
The **same detection rules** apply to both. The only difference: self mode edits
`target.dj` directly; other mode records structured findings without editing it.

A third mode — **Direct Edit Review** — applies when the user explicitly says to
edit the `.dj` files directly and skip any comments file.

### B1: Self-Review（自审）

You translated it. You own the English. Load `mpi-translation-review` skill (self mode).

1. Read `source.dj` + `target.dj` fully.
2. Apply all detection rules (three passes + R1–R14 editorial polish).
3. Edit `target.dj` directly with `patch` (mode='replace').
4. Record non-obvious choices in `translation-findings.dj` if needed.
5. Regenerate `bilingual.dj` with `../../toolkit/scripts/gen-bilingual.py source.dj target.dj --output bilingual.dj`.
6. Verify both line counts and blank-line positions match.

### B2: Other-Review（审他稿）

Someone else translated it (volunteer, etc.). Load `mpi-translation-review` skill (other mode).

1. Read `source.dj` + `target.dj` fully.
2. Apply all detection rules (three passes + R1–R14 editorial polish).
3. Do NOT edit `target.dj` — write one structured record per issue to
   `review-findings.jsonl`. A human-readable `review-comments.dj` may be added,
   but it is not the canonical status record.
   Automated accuracy reviewers add `stage`, `provider`, `model`,
   `source_sha256`, and `target_sha256`, and merge by stable finding ID without
   overwriting older records.
4. Follow deliberation protocol: 随喜 first, questions not commands.
5. Address translator by name.
6. Ask the user whether to apply the findings. If yes, switch to Direct Edit Mode.

### B3: Direct Edit Review（直接修改稿）

The user wants fixes applied directly, no separate comments file. This can follow
a translation-review pass, or be a standalone polish pass.

1. Read full `target.dj` + `source.dj` in one pass.
2. Collect every issue using the full detection rules.
3. Batch all fixes into one set of exact-string replacements. Apply with `patch`.
4. Regenerate `bilingual.dj` with `../../toolkit/scripts/gen-bilingual.py source.dj target.dj --output bilingual.dj`.
5. Verify both line counts and blank-line positions match.
6. After written polish, rerun the independent accuracy reviewer and verify the
   resulting `semantic-review.json` hashes match the current source and target.

Avoid iterative "find a few more, edit again" loops. If the user asks "anything
else?" after a direct-edit pass, do one more full systematic read and batch again.

---

## Workflow C: Batch Translate / Review with Herdr（批量翻译/审阅）

Run one book/article per omp session in its own herdr pane. A historical
9-book batch (2026-08-07) used 9 review panes and one apply pass per pane.
Its legacy mechanical checks were green; that result is not evidence of
semantic quality and predates the current strict release records.

The four-stage semantic workflow still applies independently inside each book
directory. Do not use parallel panes to bypass K3's production rule of serial
`high` requests for one manuscript, and never give a V4 reviewer another
model's source analysis. For sensitive/deny batches, use distinct internal
source-only and bilingual roles instead of the provider scripts.

### Setup

1. One herdr workspace; the main omp session in the root pane orchestrates.
2. Rename each book dir with a shared batch prefix so they sort and zip
   together: `batch0-21【《心经》的人生智慧】`, `batch0-55【…】`, …
3. Split one pane per book with an absolute `--cwd`, then also pass the same
   absolute directory to omp's own `--cwd` at launch. Verify the resulting pane
   before sending work; this remains safe across Herdr versions with different
   cwd behavior.

```fish
# 5 right of the main pane, then 4 below it
set book_dir /absolute/path/to/book-dir
set r (herdr pane split --current --direction right --cwd "$book_dir" --no-focus)
set p (printf '%s\n' "$r" | jq -r '.result.pane.pane_id')
# repeat with each book's absolute cwd:
# herdr pane split --pane $p --direction down --cwd /abs/book --no-focus
herdr pane rename <pane> review-<book>   # label each pane
```

4. Launch an independent reviewer in every pane; use Herdr's agent lifecycle
   rather than a hand-written poll. The example uses OMP's configured default
   model; add `--model '<configured model or role>'` only after verifying it on
   the current machine:

```sh
herdr agent start review-book --kind omp --pane "$PANE_ID" -- \
  --cwd /abs/path/to/book-dir
herdr agent wait review-book --timeout 3600000
```

Verify each pane landed in its book dir:
`herdr pane read <pane> --source recent-unwrapped --lines 8` — the TUI title
shows the dir.

5. Submit the review prompt (B below) to all panes at once. Treat
   `idle`/`done` as completed and `blocked` as requiring attention; allow about
   one hour for long books.
6. Move each pane to its own tab so the batch is watchable while it runs:
   `herdr pane move <pane> --new-tab --label <name> --no-focus`.
7. After all reviews finish, submit the apply prompt (C below) to every pane,
   wait to completion, rerun the blind bilingual accuracy reviewer after the
   written polish, and run the draft gate. A named human then approves the
   resolved manuscript and updates `translation-project.yaml`; only after that
   run `check-translation.py --strict` and spot-check the landed fixes.
8. Package: `zip -r <batch>-reviewed.zip batch0-*/`, list the archive, and
   verify every expected project record and deliverable is present.

### The three prompts

**A — Translate a book** (one session per book, Workflow A):

> Translate the book <NAME> (file: <NAME>.docx) from Chinese to English for the MPI translation project. Follow Workflow A and its four-stage semantic workflow in ../../toolkit/AGENTS.md: (1) load the mpi-translation and mpi-terms-search skills; (2) extract source.dj atomically and freeze translation-project.yaml plus term-map.yaml; (3) when policy allows, run ../../toolkit/scripts/kimi-source-analysis.py . before target.dj exists; for sensitive/deny use an independent internal source-only role; (4) translate the ENTIRE book yourself using Chinese, frozen terms, and the hash-matching source analysis—external APIs must not generate final English; line count and blank positions match source; (5) generate bilingual.dj, self-review with mpi-translation-review, and edit target.dj; (6) run ../../toolkit/scripts/deepseek-review.py . without giving it source-analysis.json, or the independent internal bilingual equivalent; (7) apply confirmed accuracy constraints, complete publication-register polish, and rerun the independent accuracy review; after two blocking rounds stop for a human; (8) regenerate bilingual.dj and run draft QA. Strict QA waits for fresh semantic-review hashes, independent review, and named human approval. Preserve review history; do not commit generated bilingual/QA files. Report when done.

**B — Review a book** (Herdr pane, slow role; writes `review-findings.jsonl` only):

> Review the translation in this directory (your cwd is the book dir). Read translation-project.yaml first: judge register by delivery_format, not source_origin alone; compiled articles/books use polished written English even when sourced from talks. Independently reconstruct the Chinese predicates, semantic roles, clause relations, scope, time/modality, and reference chains before comparing target.dj. Review accuracy, Buddhist terms, completeness, fluency, and declared register. Do not read source-analysis.json. Safely merge one schema-valid JSON object per issue into review-findings.jsonl; preserve all existing records and fail on a conflicting finding_id. Do NOT modify source.dj, target.dj, or bilingual.dj. End with a one-paragraph summary.

**C — Apply findings** (same pane, direct-edit mode):

> Apply your review findings now. This is direct-edit mode per project convention. 1) Read review-findings.jsonl and target.dj fully. 2) Apply EVERY accepted accuracy finding first, then do one publication-register polish when delivery_format is publication_article/publication_book. Update finding status and resolution_note; never delete history. 3) Do not add/remove lines: source/target counts and blank positions stay identical. 4) Regenerate bilingual.dj. 5) Rerun the independent bilingual accuracy review after polish; it must remain blind to source-analysis.json. If the second automated round still blocks, stop for human adjudication. 6) Run the draft gate. Strict release requires current source/target/findings hashes in a clear semantic-review.json plus named human approval; never fabricate either. Report changes and checks.

### Gotchas（踩过的坑）

- Pass an absolute cwd to both pane creation and omp launch, then verify the
  pane before sending work; do not assume cwd behavior across Herdr versions.
- Prefer `herdr agent wait` with a deadline; surface `blocked` instead of
  treating it as success.
- Line-count and blank-line-position parity are load-bearing:
  `gen-bilingual.py` fails before output on drift. Apply fixes with exact-string
  replacements; never insert or delete lines casually.
- `check-translation.py` calibration facts (all learned on the 9-book run):
  - CJK leakage ignores actual Djot anchors/link destinations; ordinary
    parenthetical prose is still checked.
  - Only strictly-Chinese punctuation flags (`，。、；：？！《》【】（）`); `—` `“”` `’` `·` are legitimate English.
  - Source emphasis multiplicity on each line must survive; targets may
    legitimately add italics for titles/Sanskrit.
  - Digit fidelity understands 万/亿 scaling, 多, word and comma forms (180亿 → "18 billion", 1300多万 → "13+ million"), and excludes TOC page numbers (`[N](#...)`), which the convention drops.
  - Use `--allow-cjk 人` for intentional Chinese and `--term-map term-map.yaml`
    to check terminology fidelity. Draft mode reports a missing map as SKIP;
    strict mode fails on every SKIP.
- If a dedicated reviewer model or role is configured, confirm its exact name
  locally before passing `--model`; the public workflow must not assume a
  machine-specific alias.
- Reviews are the quality gate: the apply pass is what lands accepted findings
  in `target.dj`. The mechanical gate proves structure, not semantic quality.

---

## Djot

- Comments: `{% ... %}`
- Emphasis: `*text*` (single asterisks)
- Dashes in English: `---` em, `--` en. Pandoc converts in docx output.
- Preserve source formatting — don't add/remove emphasis

When editing `.dj` files, use `patch` (mode='replace') — not regex-based
string replacement in `execute_code`. `patch` is safer, surfaces conflicts,
and produces a diff you can review.

## Typst Bilingual Template

For producing PDFs from bilingual Chinese-English articles:

- Template: `translate-files/lib/mpi-bilingual-template.typ`
- Example host: `translate-files/从物品整理到心灵整理/mindful-organizing.typ`
- Design notes: `references/typst-template-design.md`
- Produce rendered PDF files in: /tmp/

## Scripts

Utility scripts in `toolkit/scripts/` (fish for CLI wrappers, Python for data processing).
Agents should write repetitive logic here and run via `terminal` rather than
regenerating the same Python in execute_code each turn.

- `toolkit/scripts/docx2dj.fish <docx> [output.dj]` — pandoc .docx → Djot;
  without an output path it writes to stdout, while the two-argument form
  validates and atomically replaces the requested file.
- `toolkit/scripts/split-bilingual.fish <combined.dj>` — split canonical
  `gen-bilingual.py` output into source.dj + target.dj without guessing language;
  recovery-only command that replaces same-directory outputs after validation
- `toolkit/scripts/dj2docx.fish <target.dj> [output.docx]` — pandoc .dj → .docx in `/tmp/`
- `toolkit/scripts/source2dj.py <txt|md|dj> <source.dj>` — cross-platform,
  atomic UTF-8 source normalization; Markdown is converted through Pandoc.
- `toolkit/scripts/docx2dj.py <docx> <source.dj>` — cross-platform atomic DOCX
  extraction through Pandoc.
- `toolkit/scripts/build-term-map.py <source.dj> <term-candidates.json>
  --output <term-map.yaml> --receipts <term-search-receipts.jsonl>
  [--fixed-term SOURCE=PREFERRED]` — invoke the locked MPI terminology search
  and freeze the decisions and receipts. A locked project/release may pass a
  repeated explicit fixed-term argument; the search still runs and the full
  override remains visible in the audited command receipt.
- `toolkit/scripts/deepseek-source-analysis.py <project-dir>` — serial,
  checkpointed DeepSeek V4 Flash `high` blind analysis over toolkit-frozen
  inputs; never reads `target.dj`. For long documents each batch receives the
  exact requested paragraphs plus three neighbouring paragraphs on each side,
  preserving physical blank lines, and only term entries occurring in that
  exact window. Every frozen nonblank paragraph is still analyzed exactly once
  across the checkpointed serial run, and responses pass the complete local
  v3 schema and full-source evidence checks. To avoid unstable empty final
  responses from one oversized nested object, each batch uses seven source-only
  Flash `high` components: core predicates/relations, time, three bounded
  operator groups (negation/modality, quantity/degree, tense/aspect/other),
  reference/elliptical subject, and allusions/constraints. Toolkit merges them
  by paragraph ID and accepts only the complete v3 object. Time and operator
  components receive only the current paragraph; reference receives three
  neighbours on each side. Each request reserves
  8192 completion tokens because thinking tokens and final JSON share the same
  completion budget; an empty final `content` is never accepted. If the
  provider returns empty content or finishes at that cap, the next retry keeps
  Flash `high`, the same Chinese window, component instructions, and local
  schema but omits the explicit completion cap, matching the older verified
  provider envelope. Other validation failures keep the capped request. Each
  component gets at most five technical retries without discarding other
  components that already passed in the current batch; exhausted batch retries
  fall back to one paragraph at a time under the same gates. After all seven
  independently validated components merge, every validated temporal marker
  is deterministically included in the same paragraph's `must_preserve` list
  before the complete v3 object passes full-source validation. This
  reconciliation adds no inferred meaning and emits no source text to logs.
  If the final local validator still rejects the merged object, the tool emits
  a non-retryable diagnostic containing only a fixed error code, paragraph ID,
  schema field path, and allowlisted category. Source text, evidence values,
  provider bodies, and reasoning remain excluded.
  Before any generated component is accepted, its designated source-evidence
  fields are also checked for verbatim occurrence in the current paragraph or
  frozen complete source, as appropriate. Invalid evidence rejects only that
  component and uses the existing bounded same-model, same-input, same-schema
  component retry. The same component-local prevalidation also applies every
  v3 rule decidable without a merge: Chinese analytical prose, explicit/null/
  evidence self-consistency, temporal-marker coverage, reference and compressed-
  clause role checks, and internal allusion preservation. Cross-component
  status and temporal-to-constraint rules remain in the complete v3 final gate.
- `toolkit/scripts/freeze-target.py <source.dj> <sol-draft.dj> --output
  <target.dj>` — validate line and blank-line alignment, then atomically freeze
  Sol's English as the canonical target.
- `toolkit/scripts/dj2docx.py <djot> <output.docx> --kind target|bilingual` —
  cross-platform atomic DOCX generation.
- `toolkit/scripts/check-docx.py <djot> <docx> --output <report.json>` — verify
  DOCX ZIP integrity and Pandoc-normalized text fidelity to the frozen Djot.
- `toolkit/scripts/gen-subtitles.py <project-dir>` — generate Chinese, English,
  and bilingual SRT/VTT from `source-map.json` and aligned Djot.
- `toolkit/scripts/check-subtitles.py <project-dir> --strict --output
  <subtitle-qa-report.json>` — deterministic timing, coverage, length, and
  reading-speed gate; use `--not-applicable` for non-media projects.
- `toolkit/scripts/proofread-pdf.py <docx> <pdf>` — word-level diff between manuscript and typeset PDF
- `toolkit/scripts/gen-bilingual.py <source.dj> <target.dj> --output bilingual.dj` — validate fully, then atomically replace the generated file. Stdout mode remains for pipelines but shell redirection can truncate an old file before validation.
- `toolkit/scripts/check-translation.py <book_dir>` — deterministic translation gate: input/blank alignment, line/paragraph/heading structure, emphasis/comments, CJK/punctuation/bold leakage, digit fidelity, terminology policy, bilingual freshness, and release-governance records. `--strict` exits 1 on FAIL or SKIP.
- `toolkit/scripts/doctor.py --minimal|--strict|--strategy-c [--json]` —
  read-only dependency and strategy-C repository self-check.
- `toolkit/scripts/gen-bilingual-<name>-<hash>.py` — article-specific extraction from DOCX or source/target pairing
- `toolkit/scripts/compile-typst.fish <typ> [output.pdf]` — compile a Typst file to PDF

Article-specific scripts (including Typst compile helpers) should be placed in
the article directory itself, named with a short hash: e.g.
`translate-files/<article>/compile-typst-<hash>.fish`.

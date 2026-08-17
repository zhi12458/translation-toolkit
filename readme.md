# MPI Translation Toolkit

This is the public translation toolkit for Mindful Peace International (MPI).
It contains agent skills, a Buddhist/Dharma term database, helper scripts, and
project conventions. You clone it into a private workspace and work on your
translations in sibling directories.

## Who this is for

Volunteers and maintainers who translate MPI articles with Codex or the Oh My
Pi agent workflow. The scripts enforce mechanical invariants; they do not
replace independent Buddhist/Dharma review or named human approval.

## Workspace layout

Create a workspace directory and clone this repo into `toolkit/` inside it.
Your translations and reference materials live next to `toolkit/`, not inside
it. Treat `toolkit/` as read-only unless you are intentionally contributing to
the toolkit itself.

```text
mpi-workspace/
├── toolkit/              ← this repository (public, read-only for translators)
│   ├── skills/
│   ├── terms-database/
│   ├── scripts/
│   └── AGENTS.md
├── translate-files/      ← your translation projects
└── references/           ← your private reference materials
```

Example:

```sh
mkdir ~/mpi-workspace
cd ~/mpi-workspace
git clone https://codeberg.org/eastwind/translation-toolkit.git toolkit
mkdir translate-files references
```

## Dependencies

For a minimal check-only setup, install Python 3.11 or newer, Git, and SQLite.
Python 3.11–3.14 are exercised locally or in CI. For the full Apple Silicon
macOS workflow:

```sh
brew install uv fish jq pandoc typst poppler herdr
brew install can1357/tap/omp

python3 scripts/doctor.py --strict
```

The doctor is read-only. `--minimal` checks only the Python workflow;
`--strict` also requires conversion, PDF, OMP, and Herdr tools. Toolkit commands
do not install system tools. The optional Flask term-database UI uses `uv run`;
its first launch may resolve and cache Flask and therefore needs network access
unless the dependency is already cached.

## Load the skills

The skills use the standard Agent Skills format.

### Codex

Codex discovers project skills under `.agents/skills` and user skills under
`~/.agents/skills`. It follows symlinked skill directories. Choose one
destination below; the project-local option keeps private project policy scoped
to that project. This safe loop keeps any existing destination:

```sh
toolkit=/absolute/path/to/mpi-workspace/toolkit
skill_root="$HOME/.agents/skills"
# Or, for one private project only:
# skill_root=/absolute/path/to/private-project/.agents/skills
mkdir -p "$skill_root"

for skill_dir in "$toolkit"/skills/*; do
  test -f "$skill_dir/SKILL.md" || continue
  target="$skill_root/$(basename "$skill_dir")"
  if test -e "$target" || test -L "$target"; then
    echo "keeping existing path: $target"
  else
    ln -s "$skill_dir" "$target"
  fi
done
```

### OMP + Herdr

```sh
omp config set skills.customDirectories \
  '["/absolute/path/to/mpi-workspace/toolkit/skills"]'
omp config get skills.customDirectories --json
herdr integration install omp
herdr integration status
```

See the official [Codex skills](https://learn.chatgpt.com/docs/build-skills),
[OMP](https://github.com/can1357/oh-my-pi), and
[Herdr](https://github.com/herdrdev/herdr) documentation.

## First walkthrough

Use the public fixture to verify a fresh clone; it does not depend on a private
sibling repository:

```sh
cd ~/mpi-workspace/toolkit
python3 scripts/doctor.py --minimal
```

The fixture contains:

```text
examples/minimal-article/
├── source.dj
├── target.dj
├── translation-project.yaml
├── term-map.yaml
└── review-findings.jsonl
```

Generate the bilingual file:

```sh
./scripts/gen-bilingual.py \
  examples/minimal-article/source.dj \
  examples/minimal-article/target.dj \
  --output examples/minimal-article/bilingual.dj

./scripts/check-translation.py examples/minimal-article --strict --json \
  --output examples/minimal-article/qa-report.json
```

The generator rejects line-count and blank-line-position drift before writing
content. `bilingual.dj` and `qa-report.json` are generated; do not edit or
commit them.

## Common tasks

| Task | Command |
|---|---|
| Convert `.docx` to `.dj` | `./scripts/docx2dj.fish input.docx output.dj` |
| Cross-platform source to Djot | `python3 ./scripts/source2dj.py input.txt source.dj` or `python3 ./scripts/docx2dj.py input.docx source.dj` |
| Build an audited term map | `python3 ./scripts/build-term-map.py source.dj term-candidates.json --output term-map.yaml --receipts term-search-receipts.jsonl` |
| Freeze Sol's aligned English draft | `python3 ./scripts/freeze-target.py source.dj sol-draft.dj --output target.dj` |
| Check installed tools | `python3 scripts/doctor.py --minimal` or `--strict` |
| Convert `target.dj` to `.docx` | `./scripts/dj2docx.fish ../translate-files/my-article/target.dj` |
| Cross-platform English/bilingual DOCX | `python3 ./scripts/dj2docx.py target.dj target.docx --kind target` |
| Generate and check media subtitles | `python3 ./scripts/gen-subtitles.py PROJECT && python3 ./scripts/check-subtitles.py PROJECT --strict --output PROJECT/subtitle-qa-report.json` |
| Compile a Typst file to PDF | `./scripts/compile-typst.fish ../translate-files/my-article/my-article.typ` |
| Split a generated bilingual file | `./scripts/split-bilingual.fish ../translate-files/my-article/bilingual.dj` — recovery only; canonical generator layout; atomically replaces same-directory `source.dj` and `target.dj` after validation |
| Check a draft | `./scripts/check-translation.py ../translate-files/my-article/ --json` — WARN/SKIP are explicit |
| Check a release | `./scripts/check-translation.py ../translate-files/my-article/ --strict --json --output ../translate-files/my-article/qa-report.json` — zero FAIL and zero SKIP |
| Search the term database | `./terms-database/search.py 空性` |
| Run the term database UI | `./terms-database/server.py` then open <http://127.0.0.1:8910> |
| Select ambiguous source paragraphs for K3 | `./scripts/select-kimi-focus.py ../translate-files/my-article/ --format args` — reads a complete internal `source-analysis.json`, never the English target |
| Blindly analyze only difficult paragraphs | `./scripts/kimi-source-analysis.py ../translate-files/my-article/ --paragraph-id L57 --timeout 600 --retries 1` — complete Chinese context, focused output; cannot replace the canonical full analysis |
| Benchmark full K3 source analysis | `./scripts/kimi-source-analysis.py ../translate-files/my-article/` — retained for admission testing or projects without an internal source-only analyst; not the routine default |
| Independently review bilingual accuracy | `./scripts/deepseek-review.py ../translate-files/my-article/` — focused 20-paragraph batches with adjacent context; reads no K3 analysis; merges only after every batch validates |
| Compare K3 and V4 Pro on the gold set | `./scripts/semantic-model-benchmark.py --live --runs 3 --output /tmp/semantic-model-benchmark.json` — explicit credentials only; not run in CI |

Search results are deterministic: exact Chinese matches, longer/more-specific
entries, documented source authority, then database row ID.

## Quality records

New projects should maintain six machine-readable interfaces:

- `translation-project.yaml` — author/translator, source origin, delivery
  format, external semantic-review policy, register, versions, review, and
  approval;
- `term-map.yaml` — one frozen project sense per Chinese term, with preferred,
  allowed, and forbidden renderings;
- `source-analysis.json` — blind Chinese predicates, roles, scope and
  ambiguity, bound to the source, project metadata, frozen term map and exact
  paragraph coverage; it is never derived from the English draft;
- `review-findings.jsonl` — paragraph-level review severity, resolution, and
  optional stage/model/hash provenance;
- `semantic-review.json` — final semantic-review round and freshness hashes;
- `qa-report.json` — explicit `PASS/WARN/SKIP/FAIL` gate results.

Schemas are under `schemas/`. Strict mode requires `release.level` to be
`public` or `sensitive`, terminology coverage of at least 99%, independent
review with no unresolved (`open` or `deferred`) critical/major finding, and named human approval. These
mechanical checks also require a fresh, clear post-polish semantic-review
certificate and a schema-valid source analysis bound to all frozen inputs, but still cannot
establish semantic or doctrinal correctness.

## Tests and Codeberg CI

```sh
uvx --from 'pytest>=8,<10' pytest -q
fish -n scripts/*.fish
```

`.woodpecker.yml` runs these checks on Python 3.11–3.13 in Codeberg's
Woodpecker CI after a
maintainer enables the repository at `ci.codeberg.org`. Codeberg CI requires
manual onboarding; committing the file alone does not enable hosted builds.

## Sharing your work

Keep your workspace private. Do not share translation files through this
repository. Share finished translations with the team through WeChat or Google
Docs, as arranged by your project coordinator.

## Learn more

- `AGENTS.md` — full MPI project conventions, translation workflows, review rules, and Workflow C: the herdr batch workflow for translating or reviewing many books in parallel (one omp pane per book).
- `docs/stable-workflow.zh-CN.md` — detailed Chinese installation, full workflow, strict release gate, and old submodule migration notes.
- `docs/quality-interfaces.md` — schemas and release policy for project metadata, term decisions, findings, and QA.
- `docs/semantic-review-workflow.zh-CN.md` — blind K3 source analysis,
  independent V4 Pro accuracy review, written-register policy, credentials,
  freshness gates, and the two-track gold benchmark.
- `skills/readme.dj` — how the skills are organized.
- workspace sibling `references/` — private project references; it is not part
  of this public repository.

If you improve the toolkit itself, contributions back to the Codeberg repo are
welcome. If you are only translating, leave `toolkit/` unchanged.

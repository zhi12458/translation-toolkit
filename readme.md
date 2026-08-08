# MPI Translation Toolkit

This is the public translation toolkit for Mindful Peace International (MPI).
It contains agent skills, a Buddhist/Dharma term database, helper scripts, and
project conventions. You clone it into a private workspace and work on your
translations in sibling directories.

## Who this is for

Volunteers who want to translate MPI articles using the Oh My Pi agent
workflow. You do not need to know Oh My Pi yet; this guide covers the setup.

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

Install these before you start:

- **Oh My Pi** — the agent harness you will talk to.
- **Python 3** and **uv** — used by the scripts.
- **fish** — the scripts in `toolkit/scripts/` are written for fish.
- **pandoc** — converts between `.docx` and `.dj` (djot).
- **typst** — compiles bilingual layouts to PDF.

## Load the skills

Configure your agent to load skills from the `toolkit/skills/` directory. The
skills use the standard Agent Skills format. If your agent supports an
`external_dirs`-style skill path, add the absolute path:

```yaml
skills:
  external_dirs:
    - /home/yourname/mpi-workspace/toolkit/skills
```

Replace `/home/yourname/mpi-workspace` with the actual absolute path to your
workspace.

## First walkthrough

Use the shortest existing article to verify your setup:

```sh
cd ~/mpi-workspace/toolkit
ls ../translate-files/展示
# source.dj  target.dj
```

A minimal project has these files:

```text
../translate-files/展示/
├── source.dj     ← Chinese original, one paragraph per line
└── target.dj     ← English translation, matching source line count
```

Generate the bilingual file:

```sh
./scripts/gen-bilingual.py \
  ../translate-files/展示/source.dj \
  ../translate-files/展示/target.dj \
  > ../translate-files/展示/bilingual.dj
```

The output interleaves source, target, and blank lines. `bilingual.dj` is
generated; do not edit it by hand or commit it.

## Common tasks

| Task | Command |
|---|---|
| Convert `.docx` to `.dj` | `./scripts/docx2dj.fish input.docx output.dj` |
| Convert `target.dj` to `.docx` | `./scripts/dj2docx.fish ../translate-files/展示/target.dj` |
| Compile a Typst file to PDF | `./scripts/compile-typst.fish ../translate-files/my-article/my-article.typ` |
| Run the translation gate | `./scripts/check-translation.py ../translate-files/my-article/` — 11 deterministic checks; exit 1 on any FAIL |
| Search the term database | `./terms-database/search.py 空性` |
| Run the term database UI | `./terms-database/server.py` then open <http://127.0.0.1:8910> |

## Sharing your work

Keep your workspace private. Do not share translation files through this
repository. Share finished translations with the team through WeChat or Google
Docs, as arranged by your project coordinator.

## Learn more

- `AGENTS.md` — full MPI project conventions, translation workflows, review rules, and Workflow C: the herdr batch workflow for translating or reviewing many books in parallel (one omp pane per book).
- `skills/readme.dj` — how the skills are organized.
- `references/` — design notes, formatting guides, and other reference materials.

If you improve the toolkit itself, contributions back to the Codeberg repo are
welcome. If you are only translating, leave `toolkit/` unchanged.

# Idea: distill Master Jiqun's way of talk (语气) into a skill

Date: 2026-07-20
Status: idea / not scheduled

## Background

Reviewer feedback on a translated article: translations must preserve Master
Jiqun's 语气 — the speaker's voice and manner — not just the tone (register,
formality). A translation can have the right register and still flatten the
teacher's voice.

As a first step, a "Speaker's Voice (语气)" section was added to
`skills/mpi-translation/SKILL.md`, and check D3 in
`skills/mpi-translation-review/SKILL.md` was expanded to verify 语气 markers.
That covers the immediate need, but the knowledge is currently a short bullet
list inside a general skill.

## Idea

Distill Master Jiqun's way of talk into a dedicated skill (or a reference doc
under `skills/mpi-translation/references/`), built from evidence across many
of his talks:

- Collect characteristic passages (source + approved translations) from the
  terms DB (`loc` fields) and finished articles in `translate-files/`.
- Catalog his recurring devices: rhetorical question chains, first-person
  asides (我经常说 / 我曾在讲座中 / 由此我想到), reasoning connectives
  (可见 / 所以说 / 事实上), homely analogies (rotting apple, leaking boat,
  teacup, face mask), gentle admonition with humor, measured unhurried
  authority, inclusive we/you address.
- For each device, give approved English renderings and common failure modes
  (e.g. question → declaration, "我经常说" → "it is said").
- Possibly also cover delivery/register differences between his oral talks,
  essays, and micro-blog posts.

## Open questions

- Standalone skill vs. reference doc under `mpi-translation`? A reference doc
  is probably enough; a full skill may be overkill.
- Who approves the example translations used as evidence?
- Should it also cover other MPI teachers, or stay Jiqun-specific?

---
name: mpi-translation-review
description: |
  Unified review skill for Chinese-English Buddhist/Dharma translations in djot format.
  Use in self mode to edit your own target.dj, or in other mode to write structured review-findings.jsonl for a peer translator.
  Do not use for non-djot formats or for non-Buddhist texts.
---

# Translation Review (unified)

This skill replaces the previous `self-review` and `other-review` skills.
**What to review is the same no matter the mode.** The same detection rules,
editorial standards, and terminology checks apply whether you are polishing your
own translation or reviewing another translator's work. Only the action differs:
in self mode you edit `target.dj` directly; in other mode you write
`review-findings.jsonl` for the translator to resolve.

## Modes

| Mode | When to use | Output artifact | Interaction style |
|------|-------------|-----------------|-------------------|
| **self** | You produced the current `target.dj`. | Edited `target.dj` + regenerated `bilingual.dj`. | Direct, decisive: you own the English. |
| **other** | Another translator produced the current `target.dj`. | `review-findings.jsonl` only. | Collaborative: ask before prescribing, 随喜 first, address the translator by name. |

A third mode — **direct edit** — is used when the user explicitly asks you to
apply your findings to `target.dj` even though it is someone else's translation.
Switch to self-mode output in that case, but keep a collegial tone.

## Core workflow (both modes)

1. Read `source.dj` and `target.dj` fully before changing anything.  
   (Other mode only: read the translator's note if present, and address them by name.)
2. If the text is **meditation-practice content** — a guided meditation script,
   posture/breathing exercise guide, or meditation-method explanation — load
   `references/meditation-practice-translation.md` and run its summary checklist
   as an extra pass. It distills the recurring issues a human reviewer flagged
   across a whole meditation manuscript.
3. Run a three-pass review using the detection rules below.
4. Apply the R1–R14 editorial polish checklist.
5. Check terminology against the terms DB (see `mpi-terms-search` skill).
6. Verify that every source line and blank-line position maps to the target with
   no missing, shifted, or truncated content.
7. Produce the correct artifact for your mode.

## Detection rules — three passes

Run these in order. Stop at the end of each pass and consolidate findings before
moving to the next pass. In self mode, fix immediately; in other mode, record the
issue with line/paragraph references.

### Pass 1: Accuracy and completeness

- **A1 Missing content.** Check for mid-paragraph truncation, skipped lines, or
  entire paragraphs missing. Compare source and target line counts and paragraph
  boundaries.
- **A2 Mistranslation.** Any word or phrase that contradicts the source or is
  seriously off in meaning. Flag technical terms, numbers, negation, and modal
  verbs especially.
- **A3 Terminology inconsistency.** The same Chinese term rendered in multiple
  ways without justification. Check proper names, Dharma terms, and repeated
  metaphors.
- **A4 Unnecessary addition.** English content not present in the source that
  was added for fluency but changes the meaning. Common: adding "we should,"
  "we must," "it is important to" where the source is descriptive.
- **A5 Number / time / person mismatch.** Chinese often omits plurality, tense,
  and subjects. Ensure English reflects the intended scope and subject.

### Pass 2: Fluency and naturalness

- **F1 Calque / translationese.** Source grammar or word order carried over
  literally: "as for X ...", "only then can ...", "more ultimate,"
  "choice difficulty," "keen on" (as in "keen on greed"), etc. See
  `references/translation-pitfalls.md` for a pattern table.
- **F2 Register drift.** The English is too formal, too casual, too academic,
  or too sermonizing relative to the source. Match the source's register.
- **F3 Broken collocation.** English words that do not normally appear together
  (e.g., "arise greed," "do delusion"). Fix to the usual collocation
  ("give rise to greed," "overcome delusion").
- **F4 Pronoun / reference chain error.** Missing subject, ambiguous "it" or
  "this," or inconsistent names/pronouns across sentences.
- **F5 Sentence rhythm.** Overly long, convoluted, or monotonous sentences. For
  oral talks, respect breath units and emphasis.

### Pass 3: Dharma and cultural fitness

- **D1 Buddhist term register.** Sanskritic terms (e.g., *samatha*, *vipaśyanā*)
  vs. vernacular English ("calm abiding," "insight") vs. Chinese calques. Choose
  consistently with the text's audience and the project's conventions. See
  `references/buddhist-terminology.md`.
- **D2 Cultural anachronism.** Modern concepts projected onto classical material.
  Example: translating 般若 as "wisdom" in a scholarly context may flatten the
  term; in a popular talk it may be exactly right.
- **D3 Tone AND voice (语气) of the teacher.** For oral talks, preserve the
  speaker's warmth, rhetorical questions, and direct address. Beyond register,
  check the 语气 markers in `../mpi-translation/SKILL.md` → "Speaker's Voice
  (语气)": rhetorical questions kept as questions, first-person teacher asides
  ("我经常说") kept in first person, reasoning connectives (可见, 所以说)
  preserved, inclusive we/you address, homely analogies left concrete, gentle
  rather than scolding admonition. Do not flatten into essay prose.
- **D4 Implicit meaning / implicature.** What the source implies but does not say
  (e.g., irony, conventional politeness, Gricean maxims). Ensure the implication
  survives or is compensated.
- **D5 Formatting fidelity.** Emphasis markers (`*...*`), paragraph breaks, list
  structure, and soft-line markers (`  `) are preserved. Do not introduce
  Markdown `**` bold.

## R1–R14 editorial polish checklist

After the three passes, run these final checks.

1. **R1 Spelling and punctuation.** Especially English em/en dashes (`---`, `--`)
   and Chinese punctuation that should not survive.
2. **R2 Capitalization.** Sentence case, proper nouns, titles, Sanskritic terms
   according to convention.
3. **R3 Articles.** Missing or surplus "a/an/the" after Chinese source.
4. **R4 Subject-verb agreement.** Chinese omission of subjects can hide errors.
5. **R5 Tense consistency.** Historical narrative vs. timeless teaching vs.
   present event.
6. **R6 Voice.** Active/passive choices match the source and English register.
7. **R7 Prepositions.** Common Chinese-to-English transfer errors: *in, on, at,
   of, to, for*.
8. **R8 Modifiers.** Adjective/adverb position, misplaced modifiers, stacked
   nominalizations.
9. **R9 Parallelism.** Lists, comparisons, and repeated structures should be
   grammatically parallel.
10. **R10 Redundancy.** Remove unnecessary repetition or filler introduced during
    drafting.
11. **R11 Word choice.** Precision vs. overuse of generic words ("thing," "aspect,"
    "level," "situation"). Replace with concrete terms.
12. **R12 Sentence openings.** Vary sentence beginnings; avoid a string of
    "The..." or "It..." or "This..." starts.
13. **R13 Flow / transitions.** Logical connections between sentences and
    paragraphs are clear.
14. **R14 Final read aloud.** Read the target text as if it were being delivered
    to the intended audience. Fix anything that trips the tongue or the ear.

## Mode-specific instructions

### Self mode

- You are responsible for the English. Make the edit directly.
- Use `patch` or exact-string edits. Avoid speculative rewrites of entire
  paragraphs unless necessary.
- Record only non-obvious or project-level decisions in
  `translation-findings.dj`.
- After editing, regenerate `bilingual.dj` with
  `../../toolkit/scripts/gen-bilingual.py source.dj target.dj --output bilingual.dj`.
  The generator must accept both line counts and blank-line positions.

### Other mode

- Do not edit `target.dj`. Write `review-findings.jsonl` using
  `../../schemas/review-finding.schema.json`.
- Address the translator by name if known.
- Deliberation protocol:
  - Start with what is strong (随喜 / appreciation first).
  - Phrase most issues as questions or options, not commands.
  - Distinguish "must fix" errors (accuracy, missing content, serious
    mistranslation) from "consider" suggestions (style, register, optional
    polish).
- Give every finding a stable `finding_id`, a `paragraph_id`, one severity
  (`critical/major/minor/discussion`), one category, a concrete suggestion,
  `status: open`, and a named reviewer. Keep excerpts only as short as needed
  to locate the issue.
- When the user asks you to apply the findings, switch to direct-edit mode and
  treat it as self-mode output. Update the existing finding to
  `resolved/rejected/deferred` and add `resolution_note`; never delete history.

## Output formats

### Self mode: edited target.dj

Make targeted changes. If you change a term, search the whole file for that term
and update it consistently. After editing, regenerate the bilingual file and
verify both line counts and blank-line positions.

### Other mode: review-findings.jsonl

Write exactly one JSON object per physical line. Do not wrap the file in a JSON
array and do not add Markdown headings. Example:

```json
{"finding_id":"review-001","paragraph_id":"L42","severity":"major","category":"meaning","message":"The target reverses the source condition.","suggestion":"Restore the conditional relationship.","status":"open","reviewer":"Reviewer name"}
```

`critical` and `major` findings block public release until resolved or explicitly
rejected by an authorized human reviewer. `discussion` records a question and
does not silently become an approved term decision. A zero-finding file does not
by itself constitute human approval.

## References

- `references/common-issues-taxonomy.md` — structured accuracy/readability
  checklist used in the three passes.
- `references/translation-pitfalls.md` — recurring calques and stiff renderings
  for this project's genres.
- `references/buddhist-terminology.md` — register and convention notes for
  Buddhist/Dharma terms.
- `references/meditation-practice-translation.md` — recurring review patterns
  for meditation-practice texts (person/subject consistency, sentence
  splitting, filler deletion, fixed series terms, Chan-verse quotes), distilled
  from a human-reviewed manuscript.
- `../mpi-translation/SKILL.md` — the upstream translation skill that produces the
  `target.dj` this skill reviews.
- `../mpi-terms-search/SKILL.md` — skill for querying the terms database before and
  during review.

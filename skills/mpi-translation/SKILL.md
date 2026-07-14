---
name: mpi-translation
description: Translate Chinese↔English Buddhist/Dharma content. Use for oral talks, written articles, guided meditations, Q&A, and sutra commentary. Do not use for non-religious general Chinese-English translation, technical documentation, or marketing copy.
inputs: source.dj (Chinese djot), or .docx via docx2dj.fish
outputs: target.dj (English djot), bilingual.dj, edit-suggestions.dj
compatibility: Requires pandoc for docx-to-djot conversion.
---

# Translation

Core translation technique for Buddhist/Dharma content. Conventions (djot format,
terms DB query, workflows, output format) are in AGENTS.md.

## Source context

Before translating, understand the source's format and delivery context. Is it a transcript of an oral talk, a book excerpt, a guided meditation script, a Q&A, a written article, or another genre? The register shapes the translation. If the context is not clear from the file path or source content, ask the user before proceeding. If you cannot identify the author, write the target text with the style of 济群法师.

## Mindfulness Bell Corpus

English Buddhist prose — register/style reference for translation.

- **PDFs + index**: `~/meta/www.files/public/The Mindfulness Bell/` — 6 issues (MB92–MB97, 2023–2026), `index.yaml` lists all articles by author/title/page
- **Articles**: `~/documents/jingxin-lessons/Mindfulness Bell/MB{92..97}/*.md` — per-issue markdown files. Read with `read_file`.

Four registers, useful as style targets:

| Register | Example | Key features |
|----------|---------|-------------|
| Dharma talk | Thầy (MB94 "Roses and Garbage", MB97 "Go as a River") | Short sentences, concrete images, coined terms ("interbeing"), oral address, Sanskrit with narrative explanation |
| Teaching lineage | Sister Đoan Nghiêm (MB93 "Our Patriarch Liễu Quán") | "We" voice, terms explained, cultural bridging ("like Jesus"), dates in narrative |
| Personal narrative | Mick McEvoy (MB94 "Touching the True Nature") | First-person, confessional, borrowed Dharma vocabulary, vernacular |
| Editorial | Brother Pháp Lưu (MB94 welcome letter) | Polished but warm, conceptual framing, "we" address |

Quick-find in index: Thầy talks → `"Thích Nhất Hạnh"` + page ≤ 10; teachings → `"Sister"` or `"Brother"`; narratives → first-page articles by non-monastics; lineage → `"Patriarch"` or `"ancestor"`.

## Translation Principles

1. **Terms**: Either keep Sanskrit w/ narrative explanation (bodhisattva, Māra) OR coin new English (interbeing, inter-are). Avoid clunky calques.
2. **Cultural bridging**: Add bridges for Western readers. A Chinese text mentioning 孔子 can stay; explain the function. Đoan Nghiêm's "like Jesus" is the pattern.
3. **Tone**: Chinese Dharma texts are typically more formal than English equivalents. Decide consciously: keep formality or warm up (Thầy style).
4. **Voice**: Direct address ("you"), concrete images, and oral rhythm make Dharma land in English. Abstract noun chains (common in Chinese→English translationese) kill it.
5. **Sutra quotes**: Use standard English Buddhist idiom. Check terse-idiom conventions (e.g., Diamond Sutra "lives" not "bodies").

## Pitfalls

### Pre-flight accuracy check

Before delivering a translation, run through the structured accuracy/readability
taxonomy in `../mpi-translation-review/references/common-issues-taxonomy.md`.
Catching these before review saves iteration cycles:
- Omission, over-literal renderings, over-free renderings, subject confusion,
  overtranslation, terminology errors
- Long/nested sentences, passive voice clustering, nominalization, top-heavy
  structure, obscure word choices, weak transitions

### 1:1 line mapping

Each physical source line maps to exactly one physical target line. Never merge
continuation lines (lines ending with `  ` soft breaks) into a single
translation entry. The bilingual format preserves the original line structure —
breaking this destroys alignment.

### Blank lines in bilingual

When creating an initial bilingual template from source only: blank source
lines pass through as-is. Only non-blank lines get an empty target placeholder.
Treating blank lines as content lines (adding target+separator) creates
excessive blank clusters. See `references/bilingual-format.md`.

### Soft break markers

Trailing `  ` (two spaces) on source lines indicate soft line breaks (paragraph
continuations). Preserve these markers on both source and target lines.

### Practice element lists: use noun forms

When translating lists of Buddhist practice elements — especially the five
essentials (皈依、发心、戒律、正见、止观) or similar enumerated components —
render each as a noun phrase, not a gerund. "Refuge, aspiration, precepts,
right view, śamatha-vipaśyanā" — not "taking refuge, arousing aspiration."
These are named components of a system, not actions being described. The same
applies to any catalog-style listing (三学, 八正道 components, etc.).

### Terminology decisions: user is the source of truth

When the user proposes a non-standard rendering (e.g. "人间佛教 should be
'Buddhism for daily lives'") or asks for your input ("although I don't know
what X should be"), respond with a brief options table — strengths and
weaknesses — and let them choose. Do NOT unilaterally commit to a rendering
and start applying it across the file. The user often has a reason for their
proposal (e.g. deliberate departure from terms DB convention) or a strong
opinion they haven't voiced yet. Once they pick, then apply consistently and
annotate in the inline `{% %}` comment WHY this rendering was chosen so future
editors know it was deliberate, not a slip.

## Polishing (润色)

After translating, do a deliberate readability pass before submitting for review.
Read the English aloud — if a sentence can't be spoken in one breath, fix it.

These are common patterns (not an exhaustive list). For the full taxonomy with
more categories and examples, read
`../mpi-translation-review/references/common-issues-taxonomy.md`.

Examples of systematic adjustments:

1. **Passive → active**. Passive clusters (3+ per paragraph) are the top
   readability killer in CN→EN translation. `If meat consumption were reduced`
   → `If people consume less meat`.
2. **Nominalization → verb**. `placed emphasis on cultivating` → `emphasized
   cultivating`; `the application of` → `applying`.
3. **Sentence splitting**. If a sentence has 3+ clauses and runs past one breath,
   split it. The source's period is not a contract — English readers need
   shorter breath units than Chinese readers.
4. **Academic → plain**. `constitute` → `make up`; `facilitate` → `help`;
   `endeavor to` → `try to`; `in order to` → `to`. These texts are lectures
   and conversations, not journal articles.
5. **Register match**. Dharma talks and dialogues should sound spoken —
   contractions, direct address, concrete images. If the English reads like a
   paper abstract, warm it up. Check against the MB corpus registers for the
   target genre.
6. **Review-specific calques**. For *人生百问*-style Q&A, check the pattern
   tables in `../mpi-translation-review/references/translation-pitfalls.md` for recurring
   stiff calques ("keen on," "more ultimate," "choice difficulty," etc.) and
   the Buddhist-term register notes in `../mpi-translation-review/references/buddhist-terminology.md`.

Do NOT apply these mechanically — each is a judgment call. A passive may be
correct when the agent is unknown; a nominalization may be the right technical
term. The goal is natural English that matches the source's register, not a
formulaic rewrite.

## Baker’s Equivalence Framework

Mona Baker, *In Other Words: A Coursebook on Translation* (2nd ed., Routledge, 2011), organizes translation decisions by levels of equivalence. The framework below is adapted for this project’s Chinese → English Buddhist/Dharma texts. It is a decision aid, not a substitute for source-context judgment or the terms DB.

Baker’s central premise: **equivalence is always relative**. No translation reproduces every aspect of meaning. A responsible translator identifies which level of meaning is focal in a given context and chooses the least-lossy strategy for that level.

| Level | What it covers | Relevance to this project |
|-------|---------------|---------------------------|
| Word | Propositional, expressive, presupposed, evoked meaning | Buddhist terms (Sanskrit, Chinese coinages), register, tone |
| Above word | Collocation, idioms, fixed expressions | 成语/惯用语, collocation clashes, term companions |
| Grammatical | Number, gender, person, tense/aspect, voice, word order | Chinese↔English mismatches; passive calques; topic-prominence |
| Textual | Theme/rheme, information structure (given/new), cohesion | Paragraph flow, sentence weight, reference chains |
| Pragmatic | Coherence, implicature, context, speaker intention | Oral-talk register, implied praise/reproof, Dharma convention |

### Word-level equivalence

Baker distinguishes four types of lexical meaning. For Buddhist/Dharma texts, all four are in play:

1. **Propositional meaning**: the factual, dictionary sense. Check against the terms DB; keep it consistent.
2. **Expressive meaning**: the speaker’s attitude or evaluation. Chinese Dharma texts are often more formal, reverential, or urgent than English equivalents. Decide consciously whether to warm the tone or keep the formality.
3. **Presupposed meaning**: collocational and selectional restrictions. A Chinese verb may collocate with 心 (“mind/heart”) in ways that English does not. Do not force English collocations to match Chinese ones.
4. **Evoked meaning**: dialect/register. A guided meditation script, a Dharma talk, and a lineage history each evoke a different register. Match the target register, not just the source words.

### Non-equivalence strategies at word level

When Chinese has no ready English equivalent, use one of the attested strategies below. The choice depends on whether the term is focal, repeated, or culturally loaded.

- **More general word (superordinate)**. 打坐 → “meditation” or “sitting meditation” when the precise posture is not focal.
- **More neutral/less expressive word**. 殊胜 → “special” or “rare” when the source’s religious intensity cannot be carried naturally.
- **Cultural substitution**. Replace a culture-specific item with a target-culture equivalent only when the project explicitly allows adaptation (rare here; default is preserve and explain).
- **Loan word + explanation**. Keep Sanskrit or Chinese terms such as *bodhisattva*, *karma*, *śūnyatā* with narrative explanation on first use. This is the normal Buddhist-text convention.
- **Paraphrase using a related word**. When the Chinese term is semantically complex, unpack it with a phrase built from a superordinate.
- **Paraphrase using unrelated words**. When no related word exists, unpack the concept directly: 随喜 → “rejoice in others’ merit” on first use, then “rejoice” or *anu-moda* where appropriate.
- **Omission**. Drop a word only when it is not focal and keeping it would distract the reader. Note this in `{% %}` comments.
- **Illustration**. For posture or ritual objects, rely on the context; do not add explanatory illustrations the source does not contain.

### Above-word equivalence: collocation and idioms

Chinese and English have different collocational ranges. A word-for-word match often produces *translationese*.

- Identify the Chinese word’s typical collocates (e.g., 发 with 心, 愿, 菩提心). Do not preserve an English collocate just because it translates one component literally.
- 成语, 惯用语, and set phrases are rarely translatable by a matching idiom. Prefer: (a) an English idiom with similar meaning and compatible register, (b) transparent paraphrase, or (c) omission if the idiom is ornamental.
- Be alert to **marked collocations** in the source: unusual combinations used for emphasis. Do not normalize them automatically; reproduce the emphasis if the target language allows it.

### Grammatical equivalence

Chinese and English grammatical categories do not map one-to-one. Common pitfalls:

- **Number**: Chinese nouns are not marked for number. Do not insert plural/singular markers where the source leaves number unspecified unless the context demands it.
- **Tense/aspect**: Chinese verbs do not inflect for tense. Use English tense and aspect to convey time and viewpoint, not to mirror every Chinese particle. Be consistent with narrative viewpoint (past for stories, present for timeless Dharma statements).
- **Voice**: English passives are common; Chinese uses passive-like structures differently. Avoid importing Chinese-style “bei” passives or agentless constructions into English. Convert to active when the agent is recoverable and the English register allows.
- **Word order / topic-prominence**: Chinese is topic-prominent; English is subject-prominent. Do not reproduce Chinese topic-comment structures with “As for X …” unless the emphasis is intentional. Reconstruct the sentence around a clear English subject and predicate.
- **Pronouns / person**: Chinese often omits subjects; English usually requires them. Supply “we,” “you,” or a concrete noun as appropriate to the register. Maintain the speaker–hearer relationship (e.g., a teacher addressing students) rather than defaulting to abstract third person.

### Textual equivalence: theme, information, and cohesion

A translation must read as a text in English, not as a string of accurate sentences.

- **Theme–rheme / given–new**: Put known or orienting information at the beginning of the sentence and new, important information at the end. Chinese can delay the subject; English readers expect the subject early.
- **End-weight**: Place heavier, more complex phrases toward the end of the English sentence. Split long Chinese sentences rather than front-loading them.
- **Cohesion**: maintain reference chains (pronouns, synonyms, superordinates) so the reader can trace participants across sentences. Do not over-repeat a Buddhist term where a pronoun or a brief synonym is natural, and do not under-specify where English would use a full noun phrase for clarity.
- **Conjunction**: Chinese may rely on parataxis or zero conjunction; English often needs explicit connectors. Add them when the logical relation would otherwise be unclear, but do not over-connect and make the text sound like a logic textbook.
- **Lexical cohesion**: use consistent terminology and strategic repetition to hold the text together. Avoid introducing synonyms just for variety if the source uses the same term repeatedly.

### Pragmatic equivalence: coherence and implicature

The same words can imply different things in different cultural contexts.

- **Coherence**: ensure the translation makes sense as a unit of Dharma discourse. If a Chinese passage assumes background knowledge (a sutra story, a lineage figure, a ritual), add the minimum cultural bridge needed for the target reader.
- **Implicature / Grice’s maxims**: Speakers obey (and sometimes flout) quantity, quality, relation, and manner. A Chinese text may imply humility, authority, or gentle reproof through structure rather than lexical choice. Check whether the English reader will recover the same implicature; if not, adjust wording or add a brief bridge.
- **Speaker intention**: In Dharma talks, the speaker’s purpose—teaching, admonition, consolation, inspiration—must survive the translation. When the English sounds correct but emotionally flat, the pragmatic level has been lost.

## Quality Gates (Before Declaring Done)

Run this self-check before you hand off a first-pass translation. The goal is to
catch the most expensive errors while they are still cheap to fix. For the full
post-translation review workflows, load `mpi-translation-review` (self mode for your own
translations, other mode for peer review).

### Accuracy

- [ ] **Line parity**: source and target line counts match exactly.
- [ ] **No missing content**: every Chinese paragraph, quote, poem, or rhetorical
  climax has a corresponding English rendering.
- [ ] **No overtranslation**: no parenthetical expansions or explanations not in
  the source.
- [ ] **Terminology**: key Buddhist terms checked against the MPI terms DB
  (`mpi-terms-search` skill). Consistent within the file.
- [ ] **Source faithfulness**: no concepts added, no details dropped.

### Readability

- [ ] **Active voice**: abstract/subjectless passives converted to "we" or a
  concrete agent where possible.
- [ ] **Noun → verb**: `the propagation of` → `spread`; `placed emphasis on` →
  `emphasized`.
- [ ] **Sentence length**: no sentence that cannot be spoken in one breath; split
  at natural breaks.
- [ ] **Plain vocabulary**: `constitute` → `is/make up`; `facilitate` → `help`;
  `endeavor to` → `try to`.
- [ ] **Register**: match the genre — Dharma talks and dialogues should sound
  spoken, not like paper abstracts.
- [ ] **Concrete over abstract**: `mode of existence` → `way of living`;
  `ideological content` → `ideas`.

### Final pass

Read the entire English target aloud. If anything stalls, rephrase it.

## Meditation / Mindfulness Content

When translating guided meditation scripts, exercise guides, or posture instructions
(rather than Dharma talks), use a lighter workflow. See `references/meditation-translation.md`.

## Other Pitfalls

### article-specific scripts

`toolkit/scripts/proofread-pdf.py` is hardcoded for 佛教徒的人生态度 — body-start
markers, header patterns, slug regex. Do NOT reuse for other articles.
Create article-specific scripts per `references/proofread-pdf-workflow.md`.

## References

- `references/meditation-translation.md` — lighter workflow for meditation/mindfulness content
- `references/markdown-to-djot.md` — converting .docx.md to .dj for translation prep
- `references/bilingual-format.md` — bilingual.dj layout: source/target adjacent, blank separator between pairs
- `references/diacritics-convention.md` — diacritics rules
- `references/proofread-pdf-workflow.md` — pattern for creating article-specific PDF-vs-DOCX comparison scripts
- `../mpi-translation-review/references/common-issues-taxonomy.md` (cross-skill) — structured accuracy/readability checklist for pre-flight review
- Baker, Mona. *In Other Words: A Coursebook on Translation*. 2nd ed. Routledge, 2011. — levels of equivalence (word, above-word, grammatical, textual, pragmatic) and non-equivalence strategies.

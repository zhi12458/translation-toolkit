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

Before translating, distinguish **where the Chinese came from** from **what the
English will be delivered as**. Record both in `translation-project.yaml`:

- `source_origin`: oral talk, written text, mixed, or unknown;
- `delivery_format`: publication article/book, transcript, subtitles, audio
  script, guided practice, or other.

Delivery format governs the English register. An article or book compiled from
a Dharma talk is still publication prose: polished, written, warm, and
restrained, without chatty phrasing, slang, or contractions outside quotations.
Preserve the teacher's first person, rhetorical questions, reasoning sequence,
plain analogies, and gentle manner; written does not mean academic or impersonal.
Only transcript-like deliverables, subtitles, and spoken scripts should retain
strongly conversational surface features. If this context is unclear, ask the
user before proceeding. If you cannot identify the author, preserve the calm,
reasoned voice associated with 济群法师 without inventing personal mannerisms.

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
3. **Tone**: Follow `delivery_format` and the declared register. Publication
   prose should be lucid and warm but recognizably written; do not equate
   accessibility with casual speech.
4. **Voice**: Preserve direct address, concrete images, and the teacher's
   reasoning where the source contains them. Do not add oral fillers or a
   conversational persona merely because the source originated as a talk.
5. **Sutra quotes**: Use standard English Buddhist idiom. Check terse-idiom conventions (e.g., Diamond Sutra "lives" not "bodies").

## Titles and headings

Translate the title system as a separate editorial unit before treating it as
formatting. For the main title, every table-of-contents entry, and every body
heading:

- identify the semantic head and its modifiers; preserve contrasts, purpose or
  path relations, and distinctions such as 根本 / 基础 / 关键 rather than
  replacing them with a generic attractive phrase;
- prefer the shortest idiomatic English noun phrase that carries the full
  distinction. Publication formality is not a reason to add abstractions such
  as “the process of,” “progress toward,” or “an exploration of” when the
  source does not require them;
- translate parallel Chinese headings in visibly parallel English. Do not let
  one member become a clause while its siblings remain noun phrases;
- compare title choices with the terminology map and established published
  titles, but do not force a body-term rendering into a title when it becomes
  opaque or misleading;
- make every repeated TOC/body occurrence identical after numbering and Djot
  markers are removed. A correct hierarchy does not prove a correct title.

Before freezing a title, paraphrase its meaning in plain Chinese and back-check
the proposed English against that paraphrase. If two concise readings remain
credible, record the alternatives for human choice rather than selecting the
more impressive-sounding one.

## Speaker's Voice (语气)

Tone (register, formality) is not enough — preserve the speaker's 语气: the
stance and manner carried by sentence mood. Reviewers have flagged translations
that got the tone right but flattened the teacher's voice. 语气 lives in:

- **Sentence mood.** Rhetorical questions stay questions ("幸福在哪里？" →
  "Where is happiness?", not "Happiness is nowhere to be found.").
  Exclamations and wonder stay exclamatory. Do not convert the speaker's
  questioning into declarations.
- **First-person teacher asides.** 济群法师 often speaks in his own voice:
  "我经常说……", "我曾在讲座中多次谈到……", "由此我想到……". Keep the
  first person — do not flatten to "it is often said" or impersonal prose.
  These asides are how he establishes presence with the audience.
- **Reasoning connectives.** His talks argue step by step: 可见, 所以说,
  事实上, 问题在于. Render the logical gait ("So it is clear that…", "That
  is why…", "In fact…") rather than dropping it — the reasoned,
  unhurried persuasion IS his voice.
- **Inclusive address.** Default "we" for shared human condition, "you" when
  he turns to the listener. Do not drift into abstract third person ("one",
  "people") where the source speaks as teacher-to-audience.
- **Everyday analogies, plainly told.** Rotting apples, leaking boats,
  teacups, face masks — keep the homely image concrete and unvarnished;
  do not upgrade it to literary language or explain it away.
- **Gentle admonition, never scolding.** He points out folly with warmth and
  a little humor (the "有点烦" pop song, Mo Yan's dodge). Keep the lightness;
  avoid both sermonizing severity and jokey casualness.
- **Measured authority.** Calm, composed, unhurried. No hype, no exclamation-
  point enthusiasm, no academic hedging ("arguably", "it could be said").

Check the voice against the intended delivery. A publication article or book
should read as composed prose while still sounding like the same teacher; a
transcript or audio script should remain speakable. If either becomes an
academic abstract or motivational-speaker copy, the 语气 has been lost.

## Source-meaning analysis before English drafting

When a frozen `source-analysis.json` is present, read it together with the
Chinese and term map before drafting. It constrains meaning; it is not an
English draft and must not replace reading the source. In particular:

- preserve each predicate's action type, participants, clause relation, scope,
  tense/aspect, modality, negation, quantity, and degree;
- treat `contextual_inference` as an inference and `ambiguous` as unresolved;
- never turn a nullable or omitted participant into a definite "we," "people,"
  or other agent merely to complete an English clause;
- obey `must_preserve` and `must_not_invent`; route `needs_human` analyses to a
  human instead of silently choosing one interpretation.

English may change grammatical subject or active/passive voice for idiomatic
reasons, but it must preserve semantic roles and information status. A new
grammatical subject must not introduce a new actor or assert an ambiguous
coreference as fact.

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
For spoken deliverables, read the English aloud and respect breath units. For
publication prose, read for cadence and syntactic control; a longer sentence is
acceptable when its logic remains transparent.

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
4. **Academic → clear**. `constitute` → `make up`; `facilitate` → `help`;
   `endeavor to` → `seek to` or `try to`; `in order to` → `to`. Clear written
   prose is neither bureaucratic nor chatty.
5. **Compress without deleting meaning**. Remove duplicated framing, empty
   transitions, paired near-synonyms, and abstract carrier phrases. Prefer one
   concrete verb to a noun-plus-supporting-verb construction. After revision,
   verify that negation, degree, logical relations, and the teacher's emphasis
   have not been compressed away.
6. **Delivery-register match**. Publication articles and books use polished
   written Buddhist prose: no casual contractions, slang, chat fillers, or
   sentence fragments outside quotations. Transcripts, subtitles, Q&A kept as
   dialogue, and audio scripts may use conversational features. In every form,
   retain concrete images and the source's direct address rather than adding or
   deleting them for style.
7. **Review-specific calques**. For *人生百问*-style Q&A, check the pattern
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
- **Pronouns / person**: Chinese often omits participants while English usually
  requires a grammatical subject. First determine the predicate's semantic
  roles and whether the omitted participant is recoverable. Supply “we,” “you,”
  or a concrete noun only when the source or context licenses it; otherwise use
  a neutral restructuring or mark the choice for human review. Maintain the
  speaker–hearer relationship without converting ambiguity into fact.

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
- [ ] **Titles and headings**: semantic head, modifiers, parallel distinctions,
  and TOC/body repetitions are accurate and consistent.

### Readability

- [ ] **Semantic roles before voice**: active/passive restructuring preserves
  who acts, experiences, receives, benefits, or is affected; no omitted or
  ambiguous agent is invented.
- [ ] **Noun → verb**: `the propagation of` → `spread`; `placed emphasis on` →
  `emphasized`.
- [ ] **Sentence shape**: spoken deliverables respect breath units; publication
  prose may use longer sentences only when the logic remains transparent.
- [ ] **Plain vocabulary**: `constitute` → `is/make up`; `facilitate` → `help`;
  `endeavor to` → `try to`.
- [ ] **Register**: match `delivery_format` — compiled articles/books are
  polished written prose even when `source_origin` is `oral_talk`; transcript,
  subtitle, and audio-script deliverables may sound spoken.
- [ ] **Concrete over abstract**: `mode of existence` → `way of living`;
  `ideological content` → `ideas`.
- [ ] **Concise on the second read**: remove wording that can disappear without
  changing meaning; do not shorten away qualification, logic, or voice.

### Final pass

Read the entire target in its intended mode: aloud for spoken delivery, or as a
publication proof for articles and books. Rephrase anything whose logic or
cadence stalls.

## Meditation / Mindfulness Content

When translating guided meditation scripts, exercise guides, or posture instructions
(rather than Dharma talks), use a lighter workflow. See `references/meditation-translation.md`.
Before drafting, also read `../mpi-translation-review/references/meditation-practice-translation.md`
(patterns a human reviewer flagged across a meditation manuscript) so the recurring
issues — dropped/inconsistent person, over-long sentences, filler, 字对字
renderings, fixed series terms — are avoided up front rather than caught at review.

## Other Pitfalls

### article-specific scripts

`toolkit/scripts/proofread-pdf.py` is hardcoded for 佛教徒的人生态度 — body-start
markers, header patterns, slug regex. Do NOT reuse for other articles.
Create article-specific scripts per `references/proofread-pdf-workflow.md`.

## References

- `references/meditation-translation.md` — lighter workflow for meditation/mindfulness content
- `../mpi-translation-review/references/meditation-practice-translation.md` (cross-skill) — recurring patterns for meditation-practice texts, distilled from a human-reviewed manuscript
- `references/markdown-to-djot.md` — converting .docx.md to .dj for translation prep
- `references/bilingual-format.md` — bilingual.dj layout: source/target adjacent, blank separator between pairs
- `references/diacritics-convention.md` — diacritics rules
- `references/proofread-pdf-workflow.md` — pattern for creating article-specific PDF-vs-DOCX comparison scripts
- `../mpi-translation-review/references/common-issues-taxonomy.md` (cross-skill) — structured accuracy/readability checklist for pre-flight review
- Baker, Mona. *In Other Words: A Coursebook on Translation*. 2nd ed. Routledge, 2011. — levels of equivalence (word, above-word, grammatical, textual, pragmatic) and non-equivalence strategies.

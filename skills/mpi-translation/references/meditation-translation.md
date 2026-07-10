# Meditation / Mindfulness Content Translation

When the source is a guided meditation script, exercise guide, posture instruction,
or breathing practice (rather than a Dharma talk, sutra commentary, or teaching text),
use a lighter workflow than the full dharma-translation pipeline.

## Register

Default to warm, direct instructional voice (Thầy-adjacent):
- Second-person address ("you")
- Concrete images, sensory details
- Oral rhythm, short sentences
- Present tense, imperative mood

MB corpus consultation is NOT needed for register — this content type has its own
well-established English conventions (yoga/meditation instructional voice).

## Terms

Terms DB lookup for Buddhist-mindfulness vocabulary is useful but limited to key terms:
- 正念 → mindfulness
- 觉知 → awareness
- 无我 → depends on context: "non-self" for philosophical/Dharma content; "selflessly" for embodied/movement instruction where the sense is no separate controller imposing on the action
- 中道 → Middle Way
- 丹田 → dantian (keep as-is; well-known in meditation/qigong)

Context-sensitive terms:
- 心 (xīn): in meditation/movement contexts it often means "mind/attention" not emotional "heart." 持心 means holding the mind with focused attention, not holding with emotion.
- 念 (niàn): mindfulness/attention/recollection — context between these.
- Buddhist philosophical terms (无我, 空, 缘起) in non-philosophical contexts (movement instruction, body scans) may need practical/concrete translations rather than doctrinal ones.

Skip deep terms alignment unless dense Dharma vocabulary (emptiness, dependent origination,
Buddha-nature, etc.) appears in the text.

## Comparison files

Still create 对照.dj as usual. See comparison file format in this skill.

## Pitfalls

- **Don't add formatting the source doesn't have**: sub-section labels using `【】` in Chinese should become plain `[label]` in English, not `*[label]*` or `**[label]**`. Match the source's formatting level exactly.
- **`**text**` is Markdown, not Djot**: Djot emphasis uses single asterisks (`*text*`). Never use double asterisks in `.dj` files.
- **心 ≠ heart by default**: in meditation/movement contexts, 持心 = holding the mind with attention, not holding with emotion. Translate based on context, not dictionary defaults.

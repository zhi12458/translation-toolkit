# PDF-to-DOCX Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Text over-merged | Y-gap threshold too high | Lower gap threshold (e.g. 20 → 15) |
| Missing sections | Skipped by font filter | Add font to `skip_fonts` or remove filter |
| Over-split lines | Y-gap threshold too low | Raise gap threshold (e.g. 20 → 30) |
| Wingdings boxes | Unicode bullet inserted | Use `style='List Bullet'` instead |
| CJK font wrong | East Asian font not set | Use `set_east_asian_font()` helper |
| Image missing | Not extracted before DOCX build | Run image extraction first |
| Verse mangled | Regex too aggressive | Tune verse splitting pattern |

## General debugging steps

1. Re-inspect the PDF with the span dump from `references/inspection-guide.md`.
2. Compare the config against the actual fonts and sizes in the dump.
3. Run the verification script in `SKILL.md` and check paragraph styles.
4. Adjust one threshold at a time and re-convert.

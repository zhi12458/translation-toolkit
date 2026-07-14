---
name: mpi-pdf-to-docx-conversion
description: Convert flowing text PDFs (Chinese or multi-language) to DOCX with proper fonts, styles, native bullets, lists, and embedded images. Use for text-based PDFs. Do not use for scanned/image PDFs, form-heavy PDFs, or documents where exact page layout must be preserved.
license: MIT
compatibility: Requires Python 3.9+ and uv. Dependencies (pymupdf, python-docx) are declared in the script's /// script metadata.
---

# PDF-to-DOCX Conversion

Convert text-based PDF documents (including CJK) into structured DOCX files that preserve fonts, sizes, colors, and layout intent.

## Quick start

For most PDFs, run the bundled converter with `uv`:

```bash
uv run skills/mpi-pdf-to-docx-conversion/scripts/convert_pdf_to_docx.py input.pdf output.docx
```

`uv` reads the `/// script` metadata block in the script and installs `pymupdf` and `python-docx` automatically.

For documents with unusual fonts or structure, inspect first and pass a config dict. See `references/config-patterns.md` for the config schema and common patterns.

## Workflow

1. **Inspect the PDF.** Dump fonts, sizes, bullets, and header hierarchy. See `references/inspection-guide.md`.
2. **Configure.** Build a config dict matching the PDF's patterns (fonts, bullet fonts, skip fonts, numbered patterns, header sizes). See `references/config-patterns.md`.
3. **Convert.** Run `scripts/convert_pdf_to_docx.py` or import `PDFToDOCXConverter` in Python.
4. **Verify.** Check paragraph count, styles, bullets, images, and page-number leakage. See the checklist below.

## Features

- Style-aware extraction (font, size, bold, color)
- Native Word bullets and numbering
- Image extraction and embedding
- Verse/poetry line splitting
- Multi-language support (CJK, RTL, mixed scripts)
- Flowing text across pages (no forced page breaks)

## Verification checklist

After conversion, inspect the DOCX:

```bash
python3 -c "
from docx import Document
doc = Document('output.docx')
print(f'Paragraphs: {len(doc.paragraphs)}')
for i, p in enumerate(doc.paragraphs):
    style = p.style.name if p.style else '-'
    print(f'[{i:2d}] [{style:15s}] {p.text[:80]}')
"
```

Check for:
1. [ ] All sections present (paragraph count matches expectations)
2. [ ] No merged verses or lists
3. [ ] Headers are bold and larger than body text
4. [ ] Bullets use the `List Bullet` style
5. [ ] Numbered items are separate paragraphs
6. [ ] Images are embedded in `word/media/`
7. [ ] Attribution lines are right-aligned or indented
8. [ ] Page numbers are not leaked into body text

## Troubleshooting

If output is wrong, see `references/troubleshooting.md` for a full symptom/cause/fix table. Common first checks:

- Over-merged text → lower the Y-gap threshold.
- Over-split lines → raise the Y-gap threshold.
- Wingdings boxes → use native `List Bullet` style instead.
- Missing images → ensure images are extracted before DOCX construction.

## References

- `references/inspection-guide.md` — dump PDF structure and interpret spans
- `references/config-patterns.md` — config dict, compact lists, verses, numbered steps
- `references/docx-construction.md` — East Asian fonts, bullets, image embedding
- `references/troubleshooting.md` — symptom/cause/fix table
- `scripts/convert_pdf_to_docx.py` — production-ready converter

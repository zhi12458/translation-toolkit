# PDF Inspection Guide

Before converting a PDF, dump its text spans to understand fonts, sizes, bullets, and structure.

## Dump spans

```bash
python3 << 'PY'
import pymupdf
doc = pymupdf.open("input.pdf")
for pi in range(len(doc)):
    page = doc[pi]
    blocks = page.get_text("dict")["blocks"]
    for block in blocks:
        if block["type"] != 0: continue
        for line in block["lines"]:
            for span in line["spans"]:
                bbox = span["bbox"]
                flags = span["flags"]
                attrs = []
                if flags & 2**1: attrs.append("I")
                if flags & 2**4: attrs.append("B")
                print(f"  Y={bbox[1]:.0f} [{span['size']:.1f}pt {'+'.join(attrs) or '-'}] {span['font']} | {span['text']}")
PY
```

## What to identify

- **Fonts used** — map PDF font names to DOCX font names.
- **Bullet mechanism** — Wingdings glyphs, Unicode bullets, or something else.
- **Header hierarchy** — which font size marks section vs. sub-section headers.
- **Numbered lists** — delimiter style: `1)`, `1.`, `1）`, `一、`.
- **Images** — check `page.get_images()` on each page.
- **Special sections** — tables, verses, attribution lines, page numbers, forms.

## Page numbers

Page-number fonts are usually small and repeated on every page. Add them to `skip_fonts` in the config so they do not leak into body text.

## Attribution lines

Lines like `——节选自...` often use a different font or indentation. The converter breaks paragraphs on these; verify the break point after conversion.

---
name: pdf-to-docx-conversion
description: "Convert flowing text PDFs (Chinese or multi-language) to DOCX with proper fonts, styles, native bullets, lists, and embedded images. Preserves visual hierarchy from PDF font/size/color data."
version: 1.0.0
author: Claude
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [PDF, DOCX, Documents, python-docx, pymupdf]
---

# PDF-to-DOCX Conversion

Convert PDF documents (especially flowing text documents in any language, including CJK) into well-structured DOCX files that preserve fonts, sizes, colors, and layout intent.

## Prerequisites

```bash
pip install pymupdf python-docx
```

## Features

- **Style-aware**: reads actual font, size, bold, color from PDF spans
- **Native bullets**: uses Word `List Bullet` style instead of Wingdings glyphs
- **Native numbering**: uses numbered list style for sequential items
- **Image extraction**: detects and embeds PDF images into the DOCX
- **Verse/poetry handling**: splits merged verse lines at semantic boundaries
- **Multi-language**: works with CJK, RTL, and mixed-script documents
- **Flowing text**: text flows across pages; no forced page breaks

## Quick Start

```python
from pdf_to_docx import convert_pdf_to_docx

convert_pdf_to_docx("input.pdf", "output.docx")
```

## Step-by-Step Workflow

### 1. Inspect the PDF

First, dump the PDF to understand its structure:

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

Key things to identify:
- **Fonts used** (map to DOCX fonts)
- **Bullet mechanism** (Wingdings? Unicode?)
- **Header hierarchy** (what size = section header vs sub-header)
- **Numbered lists** (what delimiter: `1)` `1.` `1）`)
- **Images** (check `page.get_images()`)
- **Special sections** (tables, verses, forms)

### 2. Configure the Converter

Create a config dict matching your PDF's patterns:

```python
config = {
    "fonts": {
        "title": "STHeitiSC-Medium",
        "body": "HYShuSongErKW",
        "page_number": "HelveticaNeue",
    },
    "header_sizes": {"section": 18, "sub": 15},
    "body_size": 12,
    "bullet_fonts": ["Wingdings", "Wingdings 2", "Wingdings 3"],
    "page_number_font": "HelveticaNeue",
    "numbered_patterns": [r'^\d+\)', r'^\d+\.'],  # detect numbered items
    "skip_fonts": ["HelveticaNeue"],  # fonts to skip (page numbers)
}
```

### 3. Run the Conversion

```python
from pdf_to_docx import PDFToDOCXConverter

converter = PDFToDOCXConverter(config)
converter.convert("input.pdf", "output.docx")
```

## Core Classes

### PDFToDOCXConverter

```python
class PDFToDOCXConverter:
    def __init__(self, config=None):
        self.cfg = config or self._default_config()

    def convert(self, pdf_path: str, docx_path: str):
        """Main entry point."""
        # 1. Extract all spans
        # 2. Merge Wingdings bullets with body text
        # 3. Group lines into paragraphs by Y-gap and style changes
        # 4. Post-process: split compact lists, verses, merged steps
        # 5. Build DOCX with proper styles
        # 6. Embed images
        pass

    def extract_spans(self, pdf_path: str) -> list[dict]:
        """Extract all text spans with full style info."""
        doc = pymupdf.open(pdf_path)
        raw = []
        for pi in range(len(doc)):
            for block in doc[pi].get_text("dict")["blocks"]:
                if block["type"] != 0: continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        raw.append({
                            "text": span["text"], "font": span["font"],
                            "size": span["size"], "flags": span["flags"],
                            "color": span["color"], "bbox": span["bbox"],
                        })
        return raw

    def detect_bullets(self, line: list) -> bool:
        """Check if first span in line is a Wingdings bullet."""
        return "Wingdings" in line[0]["font"]

    def group_paragraphs(self, lines: list) -> list[dict]:
        """Group raw lines into logical paragraphs."""
        # Group by Y-gap threshold (typically 20-30pt)
        # Break on style change (font change, size > threshold, bold toggle)
        # Break on attribution lines (——节选自...)
        # Break on special fonts (STHeitiSC-Light etc.)
        pass

    def post_process(self, paras: list) -> list[dict]:
        """Split merged compact lists and verses."""
        # See examples below for common patterns
        pass
```

## Common Post-Processing Patterns

### Compact Numbered Lists

When the PDF flows list items together in one paragraph:

```python
def split_compact_list(text: str) -> list[str]:
    """Split '1) foo 2) bar 3) baz' into separate items."""
    parts = re.split(r'(?=\d+\))', text)
    return [p for p in parts if p.strip()]
```

### Verse / Poetry Lines

When the PDF merges verse lines that should be on separate lines:

```python
def split_verse(text: str, split_markers: list[str]) -> list[str]:
    """Split verse at semantic phrase boundaries.
    Example markers: ['感恩', '愿', '更愿']"""
    pattern = '|'.join(f'(?={m})' for m in split_markers)
    return [p for p in re.split(pattern, text) if p.strip()]
```

### 小组交流流程 / Process Steps

Split Chinese process steps numbered 一、二、三、etc.:

```python
def split_chinese_steps(text: str) -> list[str]:
    """Split '一、foo 二、bar' into separate items."""
    parts = re.split(r'(?=[一二三四五六七八九十]、)', text)
    return [p.strip() for p in parts if p.strip()]
```

## DOCX Construction

### Font Setup (East Asian fonts)

```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def set_east_asian_font(run, name: str):
    """Set CJK font properly in python-docx."""
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:eastAsia'), name)
    rFonts.set(qn('w:ascii'), name)
    rFonts.set(qn('w:hAnsi'), name)
```

### Bullet Items

Use native Word bullets, NOT Wingdings characters:

```python
p = doc.add_paragraph(style='List Bullet')
p.clear()
run = p.add_run("Your bullet text here")
set_east_asian_font(run, font_name)
```

### Image Embedding

```python
from docx.shared import Inches

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run()
run.add_picture(image_path, width=Inches(3.5))
```

Extract images from PDF first:

```python
doc = pymupdf.open("input.pdf")
for pi in range(len(doc)):
    images = doc[pi].get_images()
    for idx, img in enumerate(images):
        xref = img[0]
        base = doc.extract_image(xref)
        with open(f"extracted_{pi}_{idx}.{base['ext']}", 'wb') as f:
            f.write(base['image'])
```

## Verification Checklist

After conversion, verify the DOCX:

```bash
python3 -c "
from docx import Document
doc = Document('output.docx')
print(f'Paragraphs: {len(doc.paragraphs)}')
for i, p in enumerate(doc.paragraphs):
    style = p.style.name if p.style else '-'
    txt = p.text[:80]
    print(f'[{i:2d}] [{style:15s}] {txt}')
"
```

Check for:
1. [ ] All sections present (count paragraphs)
2. [ ] No merged verses or lists
3. [ ] Headers are bold + larger size
4. [ ] Bullets use `List Bullet` style
5. [ ] Numbered items are separate paragraphs
6. [ ] Images present in `word/media/`
7. [ ] Attribution lines right-aligned/indented
8. [ ] No page numbers leaked into body

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Text over-merged | Y-gap threshold too high | Lower gap threshold (e.g. 20 → 15) |
| Missing sections | Skipped by font filter | Add font to skip_fonts or remove filter |
| Over-split lines | Y-gap threshold too low | Raise gap threshold (e.g. 20 → 30) |
| Wingdings boxes | Unicode bullet inserted | Use `style='List Bullet'` instead |
| CJK font wrong | East Asian font not set | Use `set_east_asian_font()` helper |
| Image missing | Not extracted before DOCX build | Run `extract_images()` first |
| Verse mangled | Regex too aggressive | Tune verse splitting pattern |

## Full Example Script

See `scripts/convert_pdf_to_docx.py` for a production-ready converter with all patterns pre-configured.

```python
# scripts/convert_pdf_to_docx.py
import pymupdf, re
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def convert_pdf_to_docx(pdf_path: str, docx_path: str, config: dict = None):
    """Convert a flowing text PDF to DOCX."""
    cfg = config or {}

    # Extract
    doc_pdf = pymupdf.open(pdf_path)
    raw = []
    for pi in range(len(doc_pdf)):
        for block in doc_pdf[pi].get_text("dict")["blocks"]:
            if block["type"] != 0: continue
            for line in block["lines"]:
                ss = line["spans"]
                is_b = any("Wingdings" in s["font"] for s in ss[:1])
                text = "".join(s["text"] for s in ss)
                dom = ss[1] if (is_b and len(ss) > 1) else ss[0]
                raw.append(dict(text=text, font=dom["font"], size=dom["size"],
                                bold=bool(dom["flags"] & 2**4), color=dom["color"],
                                x=dom["bbox"][0], y=dom["bbox"][1], is_bullet=is_b))

    # ... (merge bullets, group paragraphs, post-process, build DOCX)

# Run:
# python scripts/convert_pdf_to_docx.py input.pdf output.docx
```

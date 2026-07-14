# DOCX Construction Notes

Low-level notes for building the DOCX output with python-docx.

## East Asian fonts

Set CJK fonts properly on a run:

```python
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def set_east_asian_font(run, name: str):
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    rFonts.set(qn('w:eastAsia'), name)
    rFonts.set(qn('w:ascii'), name)
    rFonts.set(qn('w:hAnsi'), name)
```

## Native bullets

Use Word's `List Bullet` style, not Wingdings characters:

```python
p = doc.add_paragraph(style='List Bullet')
p.clear()
run = p.add_run("Bullet text")
set_east_asian_font(run, font_name)
```

## Image embedding

Extract images from the PDF first, then embed them:

```python
from docx.shared import Inches

# Extract
doc = pymupdf.open("input.pdf")
for pi in range(len(doc)):
    for idx, img in enumerate(doc[pi].get_images()):
        xref = img[0]
        base = doc.extract_image(xref)
        path = f"extracted_{pi}_{idx}.{base['ext']}"
        with open(path, 'wb') as f:
            f.write(base['image'])

# Embed
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run()
run.add_picture(image_path, width=Inches(3.5))
```

See `scripts/convert_pdf_to_docx.py` for the production-ready implementation.

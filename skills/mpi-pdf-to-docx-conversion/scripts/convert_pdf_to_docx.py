#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = [
#   "pymupdf",
#   "python-docx",
# ]
# ///

"""
Production-ready PDF-to-DOCX converter.
Handles multi-language text, mixed fonts, bullets, numbered lists, verses,
attributions, images, and flowing text across pages.

Usage:
    ./convert_pdf_to_docx.py input.pdf output.docx

Requires: uv (dependencies are declared in the /// script block above)
"""

import sys
import re
import pymupdf
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# ══════════════════════════════════════════════════════════════════════════════════════
# Config —— tweak these for your PDF's style conventions
# ═════════════════════════════════════════════════════════════════════════════════════

DEFAULT_CONFIG = {
    # Font names used for different roles
    "fonts": {
        "title":      "STHeitiSC-Medium",
        "body":       "HYShuSongErKW",
        "page_num":   "HelveticaNeue",
    },
    # Size thresholds (pt) for paragraph classification
    "thresholds": {
        "section_header": 18,   # —— bold, centered:  【法义】 【思考】 【练习】
        "sub_header":     14,   # —— bold: 一、认识感恩, 【使用说明】
        "body":           12,
    },
    # Fonts to treat as bullets (skipped as glyphs, trigger List Bullet style)
    "bullet_fonts": ["Wingdings", "Wingdings 2", "Wingdings 3", "Symbol"],
    # Fonts to skip entirely (page numbers, decorative markers)
    "skip_fonts":      ["HelveticaNeue"],
    "skip_size_max":   9.5,
    # Numbered-list delimiters in the PDF text
    "numbered_patterns": [
        r'^\d+\)',       # 1) 2) 3)
        r'^\d+\.\s*',    # 1.  2.  3.
        r'^\d+）',      # 1） 2） 3）  (full-width parens)
        r'^\d+、',      # 1、 2、 3、  (ideographic comma)
    ],
    # Paragraph grouping: maximum Y-gap (pt) between lines to keep in same paragraph
    "y_gap_threshold": 20,
    # Indentation for body/numbered items (cm)
    "indent_body":     0.8,
    # Verse markers —— used to split merged poetic lines
    "verse_markers":   [
        r'感恩(?!恩)',  # 感恩 (not followed by 恩)
        r'愿我们',      # 愿我们
        r'更愿',        # 更愿
        r'愿人们',      # 愿人们
        r'愿世界',      # 愿世界
    ],
}


# ══════════════════════════════════════════════════════════════════════════════════════
# DOCX helpers
# ═══════════════════════════════════════════════════════════════════════════════════════

def set_east_asian_font(run, name: str):
    """Set CJK/RTL font properly in python-docx (East Asian + ascii + hAnsi)."""
    run.font.name = name
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    for attr in ('eastAsia', 'ascii', 'hAnsi'):
        rFonts.set(qn(f'w:{attr}'), name)


def _mk_color(val: int) -> RGBColor | None:
    if val and val != 0:
        return RGBColor((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)
    return None


def _is_numbered(text: str, cfg: dict) -> bool:
    return any(re.match(pat, text) for pat in cfg["numbered_patterns"])


def _is_bullet_font(font: str, cfg: dict) -> bool:
    return any(b in font for b in cfg["bullet_fonts"])


def _skip_span(span: dict, cfg: dict) -> bool:
    """True if this span should be dropped entirely."""
    if span["font"] in cfg["skip_fonts"] and span["size"] <= cfg["skip_size_max"]:
        return True
    if _is_bullet_font(span["font"], cfg):
        return False  # bullets are handled upstream
    return False


# ══════════════════════════════════════════════════════════════════════════════════════
# Extraction
# ════════════════════════════════════════════════════════════════════════════════════════════

def extract_lines(pdf_path: str, cfg: dict) -> list[dict]:
    """Return flattened list of text lines with style info."""
    doc_pdf = pymupdf.open(pdf_path)
    lines = []
    for pi in range(len(doc_pdf)):
        page = doc_pdf[pi]
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue  # skip images
            for line in block["lines"]:
                spans = line["spans"]
                if not spans:
                    continue

                # Detect bullet: first span is Wingdings / Symbol
                is_bullet = _is_bullet_font(spans[0]["font"], cfg)

                # Dominant span for style (skip Wingdings glyph)
                dom = spans[1] if (is_bullet and len(spans) > 1) else spans[0]

                # Skip decorative spans entirely
                if _skip_span(dom, cfg):
                    continue

                text = "".join(s["text"] for s in spans)
                lines.append({
                    "text":     text,
                    "font":     dom["font"],
                    "size":     dom["size"],
                    "bold":     bool(dom["flags"] & 2**4),
                    "color":    dom["color"],
                    "x":        dom["bbox"][0],
                    "y":        dom["bbox"][1],
                    "is_bullet": is_bullet,
                })
    return lines


def extract_images(pdf_path: str, out_dir: str = "/tmp") -> list[str]:
    """Extract all embedded images from PDF. Returns list of file paths."""
    doc = pymupdf.open(pdf_path)
    paths = []
    for pi in range(len(doc)):
        page = doc[pi]
        for idx, img in enumerate(page.get_images()):
            xref = img[0]
            base = doc.extract_image(xref)
            path = f"{out_dir}/pdf_img_p{pi}_{idx}.{base['ext']}"
            with open(path, "wb") as f:
                f.write(base["image"])
            paths.append((pi, path))
    return paths


# ═════════════════════════════════════════════════════════════════════════════════════════════
# Grouping & Classification
# ══════════════════════════════════════════════════════════════════════════════════════════════

def group_paragraphs(lines: list[dict], cfg: dict) -> list[dict]:
    """Group raw lines into logical paragraphs."""
    paras = []
    i = 0
    gap_thresh = cfg["y_gap_threshold"]

    while i < len(lines):
        ln = lines[i]

        # ─── Headers ───
        if ln["bold"] and ln["size"] >= cfg["thresholds"]["section_header"]:
            paras.append({
                "text": ln["text"], "font": ln["font"], "size": ln["size"],
                "bold": True, "color": ln["color"], "x": ln["x"],
                "kind": "header"
            })
            i += 1
            continue

        if ln["bold"] and ln["size"] >= cfg["thresholds"]["sub_header"]:
            paras.append({
                "text": ln["text"], "font": ln["font"], "size": ln["size"],
                "bold": True, "color": ln["color"], "x": ln["x"],
                "kind": "subheader"
            })
            i += 1
            continue

        # ─── Attribution ───
        if ln["text"].startswith("——"):
            paras.append({
                "text": ln["text"], "font": ln["font"], "size": ln["size"],
                "bold": False, "color": ln["color"], "x": ln["x"],
                "kind": "attribution"
            })
            i += 1
            continue

        # ─── Bullet item ───
        if ln["is_bullet"]:
            body = ln["text"].lstrip("\uf06c \uf0b7 \u2022 ").lstrip()  # strip common bullet chars
            buf = [body]
            bf, bs = ln["font"], ln["size"]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if nxt["bold"] and nxt["size"] >= cfg["thresholds"]["sub_header"]:
                    break
                if nxt["is_bullet"]:
                    break
                if nxt["text"].startswith("——"):
                    break
                gap = nxt["y"] - (lines[i - 1]["y"] + lines[i - 1]["size"])
                if gap > gap_thresh:
                    break
                if _is_numbered(nxt["text"], cfg) and nxt["x"] <= 115:
                    break  # nested numbered item = new para
                if nxt["font"] != bf:
                    break
                buf.append(nxt["text"])
                i += 1
            paras.append({
                "text": "".join(buf), "font": bf, "size": bs,
                "bold": False, "color": ln["color"], "x": ln["x"],
                "kind": "bullet"
            })
            continue

        # ─── Special fonts (one-liners like STHeitiSC-Light notes) ───
        if ln["font"] == "STHeitiSC-Light":
            paras.append({
                "text": ln["text"], "font": cfg["fonts"]["body"], "size": ln["size"],
                "bold": False, "color": ln["color"], "x": ln["x"],
                "kind": "special"
            })
            i += 1
            continue

        # ─── Body / numbered / exercise labels ───
        buf = [ln["text"]]
        bf, bs, bc, bx = ln["font"], ln["size"], ln["color"], ln["x"]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            # Hard breaks
            if nxt["bold"] and nxt["size"] >= cfg["thresholds"]["sub_header"]:
                break
            if nxt["is_bullet"]:
                break
            if nxt["text"].startswith("——"):
                break
            if nxt["font"] == "STHeitiSC-Light":
                break
            if _skip_span(nxt, cfg):
                i += 1
                continue

            gap = nxt["y"] - (lines[i - 1]["y"] + lines[i - 1]["size"])
            style_changed = nxt["font"] != bf or abs(nxt["size"] - bs) > 1.5

            # Break on new numbered item at left margin
            is_new_numbered = _is_numbered(nxt["text"], cfg) and nxt["x"] <= 115
            # Break on exercise day headers
            is_day = bool(re.match(r'^第\d+ 天', nxt["text"]))
            is_ex_label = bool(re.match(r'^(今日感恩练习心得|感恩日记|我的练习)', nxt["text"]))

            if gap > gap_thresh or style_changed or is_new_numbered or is_day or is_ex_label:
                break
            buf.append(nxt["text"])
            i += 1

        text = "".join(buf)
        kind = "body"
        if _is_numbered(text, cfg) and bx <= 115:
            kind = "numbered"
        elif bool(re.match(r'^第\d+ 天', text)):
            kind = "day_header"
        elif bool(re.match(r'^(今日感恩练习心得|感恩日记|我的练习)', text)):
            kind = "exercise_label"
        elif bx > 160:
            kind = "centered_body"

        paras.append({
            "text": text, "font": bf, "size": bs, "bold": False,
            "color": bc, "x": bx, "kind": kind
        })

    return paras


# ══════════════════════════════════════════════════════════════════════════════════════════════════════
# Post-processing
# ════════════════════════════════════════════════════════════════════════════════════════════════════════

def split_compact_lists(paras: list[dict], cfg: dict) -> list[dict]:
    """Split paragraphs that contain multiple numbered items."""
    out = []
    for p in paras:
        text = p["text"]
        numbers = re.findall(r'\d+\)', text)
        # Only split if more than 2 numbered items in a body paragraph
        if p["kind"] in ("numbered", "body") and len(numbers) > 2:
            parts = re.split(r'(?=\d+\))', text)
            for part in parts:
                if part.strip():
                    out.append({
                        "text": part.strip(), "font": p["font"], "size": p["size"],
                        "bold": False, "color": p["color"], "x": p["x"], "kind": "numbered"
                    })
        else:
            out.append(p)
    return out


def split_verses(paras: list[dict], cfg: dict) -> list[dict]:
    """Split merged poetic / verse lines."""
    out = []
    for p in paras:
        text = p["text"]
        markers = cfg.get("verse_markers", [])
        if not markers:
            out.append(p)
            continue

        # Heuristic: paragraph contains repeated marker phrases
        total_markers = sum(len(re.findall(m, text)) for m in markers)
        if total_markers < 3:
            out.append(p)
            continue

        # Build a combined split regex from all markers
        combined = '|'.join(f'(?={m})' for m in markers)
        parts = re.split(combined, text)
        # Also split Chinese process steps (一、二、三、) that may prefix the verse
        prefix = ""
        verse_start = 0
        for idx, part in enumerate(parts):
            if re.match(r'[一二三四五六七八九十]、', part):
                prefix += part
                verse_start = idx + 1
            else:
                break

        # Emit prefix steps
        if prefix:
            for step in re.split(r'(?=[一二三四五六七八九十]、)', prefix):
                if step.strip():
                    out.append({
                        "text": step.strip(), "font": p["font"], "size": p["size"],
                        "bold": False, "color": p["color"], "x": p["x"], "kind": "numbered"
                    })

        # Emit verse lines
        for part in parts[verse_start:]:
            part = part.strip()
            if not part:
                continue
            # Check for trailing process step (五、回向 etc.)
            tail_match = re.search(r'([一二三四五六七八九十]、.+)$', part)
            if tail_match:
                main_text = part[:tail_match.start()].strip()
                tail = tail_match.group(1)
                if main_text:
                    out.append({
                        "text": main_text, "font": p["font"], "size": p["size"],
                        "bold": False, "color": p["color"], "x": p["x"] + 100, "kind": "verse_line"
                    })
                out.append({
                    "text": tail, "font": p["font"], "size": p["size"],
                    "bold": False, "color": p["color"], "x": p["x"], "kind": "numbered"
                })
            else:
                out.append({
                    "text": part, "font": p["font"], "size": p["size"],
                    "bold": False, "color": p["color"], "x": p["x"] + 100, "kind": "verse_line"
                })
    return out


def split_chinese_steps(paras: list[dict]) -> list[dict]:
    """Split merged Chinese process steps (一、二、etc.) in body paragraphs."""
    out = []
    for p in paras:
        text = p["text"]
        if p["kind"] == "body" and len(re.findall(r'[一二三四五六七八九十]、', text)) > 1:
            parts = re.split(r'(?=[一二三四五六七八九十]、)', text)
            for part in parts:
                if part.strip():
                    out.append({
                        "text": part.strip(), "font": p["font"], "size": p["size"],
                        "bold": False, "color": p["color"], "x": p["x"], "kind": "numbered"
                    })
        else:
            out.append(p)
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════
# DOCX building
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════

def build_docx(paras: list[dict], images: list[tuple[int, str]], cfg: dict) -> Document:
    """Build a DOCX from classified paragraphs."""
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(3.18)
    section.right_margin = Cm(3.18)

    # Track which images have been inserted (insert after first occurrence)
    inserted_images = set()

    def _add_run(paragraph, text: str, font: str, size: float, bold: bool = False,
                 color=None, alignment=None):
        if alignment is not None:
            paragraph.alignment = alignment
        run = paragraph.add_run(text)
        run.font.size = Pt(size)
        run.font.bold = bold
        if color:
            run.font.color.rgb = color
        set_east_asian_font(run, font)
        return run

    def _add_para(text: str, font: str, size: float, bold: bool = False,
                  alignment=None, sb: int = 0, sa: int = 0,
                  color=None, style=None, indent: float = None):
        if style:
            p = doc.add_paragraph(style=style)
            p.clear()
        else:
            p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(sb)
        p.paragraph_format.space_after = Pt(sa)
        p.paragraph_format.line_spacing = 1.15
        if indent:
            p.paragraph_format.left_indent = Cm(indent)
        _add_run(p, text, font, size, bold, color, alignment)
        return p

    # Image helper
    def _insert_image(image_path: str):
        ip = doc.add_paragraph()
        ip.alignment = WD_ALIGN_PARAGRAPH.CENTER
        ip.paragraph_format.space_before = Pt(6)
        ip.paragraph_format.space_after = Pt(6)
        ir = ip.add_run()
        ir.add_picture(image_path, width=Inches(3.3))

    for p in paras:
        text = p["text"]
        font = p["font"]
        size = p["size"]
        bold = p["bold"]
        color = _mk_color(p["color"])
        kind = p["kind"]

        if kind == "header":
            _add_para(text, font, size, bold=True,
                      alignment=WD_ALIGN_PARAGRAPH.CENTER, sb=10, sa=8)
        elif kind == "subheader":
            _add_para(text, font, size, bold=True, sb=8, sa=4)
        elif kind == "bullet":
            _add_para(text, font, size, style='List Bullet', sb=0, sa=1, color=color)
        elif kind == "attribution":
            _add_para(text, font, size,
                      alignment=WD_ALIGN_PARAGRAPH.RIGHT, sb=2, sa=6, color=color)
        elif kind == "numbered":
            _add_para(text, font, size, indent=cfg["indent_body"], sb=1, sa=1, color=color)
        elif kind == "day_header":
            _add_para(text, font, size, bold=True, sb=6, sa=2, color=color)
        elif kind == "exercise_label":
            _add_para(text, font, size, sb=2, sa=1, color=color)
        elif kind == "special":
            _add_para(text, font, size, sb=6, sa=4)
        elif kind == "verse_line":
            _add_para(text, font, size, indent=2.0, sb=0, sa=0, color=color)
        elif kind == "centered_body":
            _add_para(text, font, size,
                      alignment=WD_ALIGN_PARAGRAPH.CENTER, sb=2, sa=4, color=color)
        else:  # body
            indent = cfg["indent_body"] if p["x"] > 105 else None
            _add_para(text, font, size, indent=indent, sb=1, sa=2, color=color)

        # Insert images after paragraphs containing "参考示例" or other markers
        if "参考示例" in text or "示例" in text:
            for pi, img_path in images:
                if img_path not in inserted_images:
                    _insert_image(img_path)
                    inserted_images.add(img_path)
                    break

    return doc


# ════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════════════════════════════════════════

def convert_pdf_to_docx(pdf_path: str, docx_path: str, config: dict = None):
    """
    Convert a flowing text PDF to a well-structured DOCX.

    Args:
        pdf_path:  Path to input PDF
        docx_path: Path to output DOCX
        config:    Optional override dict (merged with DEFAULT_CONFIG)
    """
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg.update(config)

    # 1. Extract images
    images = extract_images(pdf_path)

    # 2. Extract text lines
    lines = extract_lines(pdf_path, cfg)

    # 3. Group into paragraphs
    paras = group_paragraphs(lines, cfg)

    # 4. Post-process
    paras = split_compact_lists(paras, cfg)
    paras = split_verses(paras, cfg)
    paras = split_chinese_steps(paras)

    # 5. Build DOCX
    doc = build_docx(paras, images, cfg)
    doc.save(docx_path)
    print(f"Saved: {docx_path} ({len(doc.paragraphs)} paragraphs)")
    return docx_path


# CLI
if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: ./convert_pdf_to_docx.py <input.pdf> <output.docx>")
        sys.exit(1)
    convert_pdf_to_docx(sys.argv[1], sys.argv[2])

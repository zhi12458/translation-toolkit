"""
Fix extraneous line breaks in Chinese markdown files.

Three file patterns:
1. Fixed-width body text (20-25 chars/line) + vertical TOC -> join lines, remove page nums
2. Mostly-paragraph with stray breaks + outline TOC -> join broken lines, preserve list items
3. Already fine -> skip (idempotent)

Usage: python3 normalize_breaks.py <directory>
"""
import re
import sys
from pathlib import Path

CJK = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
CN_PUNCT = '，。！？；：、""''（）《》【】…—～·'
NUM_MARKER = re.compile(r'^[一二三四五六七八九十]+[、，,]')
DIGIT_MARKER = re.compile(r'^\d+[、.,]')
TOC_SEP = re.compile(r'\.{3,}')  # "......" separators in outline TOCs


def has_cjk(s):
    return bool(CJK.search(s))


def is_page_num(line):
    s = line.strip()
    return s and s.isdigit() and len(s) <= 2


def is_toc_line(line):
    """Vertical TOC: single char, or 【, 】, ·, or solo digit"""
    s = line.strip()
    if not s:
        return False
    if len(s) == 1 and (has_cjk(s) or s in CN_PUNCT or s in '【】·' or s.isdigit()):
        return True
    return False


def is_section_header(line):
    """Section headers: 【...】, ## ..., # ..., 一、..., 1、..., or standalone title lines"""
    s = line.strip()
    if not s:
        return False
    if s.startswith('【') and s.endswith('】'):
        return True
    if s.startswith('#'):
        return True
    if NUM_MARKER.match(s):
        return True
    if DIGIT_MARKER.match(s):
        return True
    return False


def is_outline_toc_line(line):
    """Outline/list TOC: entries separated by ...... or short numbered items"""
    s = line.strip()
    if TOC_SEP.search(s):
        return True
    m = re.match(r'^(\d+[.、,]|[一二三四五六七八九十]+[、,])\s*\S', s)
    if m and len(s) < 30:
        return True
    return False


def find_toc_end(lines):
    """Find where the vertical TOC section ends and body text begins."""
    for i, line in enumerate(lines):
        s = line.strip()
        if has_cjk(s) and len([c for c in s if has_cjk(c)]) >= 3:
            j = i
            while j > 0 and not lines[j - 1].strip():
                j -= 1
            return j
    return 0


def process_body(lines):
    """Join body text lines into paragraphs, preserving section headers and outline items."""
    result = []
    buf = []

    def flush():
        nonlocal buf
        if buf:
            joined = ''.join(buf)
            result.append(joined)
            buf = []

    for line in lines:
        s = line.strip()

        if not s:
            flush()
            result.append('')
            continue

        if is_section_header(s):
            flush()
            result.append(s)
            continue

        if is_outline_toc_line(s):
            flush()
            result.append(s)
            continue

        if is_page_num(s):
            continue

        if has_cjk(s) or (buf and s):
            buf.append(s)
        else:
            flush()
            result.append(s)

    flush()
    return result


def process_file(filepath):
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')

    toc_end = find_toc_end(lines)

    if toc_end > 10:
        toc_part = lines[:toc_end]
        body_part = lines[toc_end:]
        body_processed = process_body(body_part)
        new_lines = toc_part + body_processed
    else:
        new_lines = process_body(lines)

    cleaned = []
    prev_blank = False
    for line in new_lines:
        is_blank = line.strip() == ''
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank

    while cleaned and cleaned[-1] == '':
        cleaned.pop()

    new_content = '\n'.join(cleaned) + '\n'

    if new_content != content:
        filepath.write_text(new_content, encoding='utf-8')
        return True
    return False


def main():
    workdir = Path(sys.argv[1])
    files = sorted(workdir.glob('*.md'))

    for f in files:
        changed = process_file(f)
        status = 'FIXED' if changed else 'OK'
        print(f'{status}: {f.name}')


if __name__ == '__main__':
    main()

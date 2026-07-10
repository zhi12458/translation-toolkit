"""Extract cleaned English body from DOCX manuscript and typeset PDF.
Usage: python3 ten-elements-c7fcd9.py <docx_path> <pdf_path>
Output: two cleaned text files in /tmp/ for diffing.
"""
import re, sys, subprocess
from pathlib import Path

DOCX_TXT = '/tmp/ten_elements_docx_body.txt'
PDF_TXT = '/tmp/ten_elements_pdf_body.txt'


def extract_docx_body(path):
    with open(path) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if 'The Dhyana Tea program team' in line:
            body_start = i
            break
    else:
        sys.exit("Could not find body start in DOCX")
    body = [l.strip() for l in lines[body_start:] if l.strip()]
    return '\n'.join(body)


def extract_pdf_body(path):
    with open(path) as f:
        lines = f.readlines()

    slug_re = re.compile(r'正念禅修十要素.*indd \d+')
    header_re = re.compile(
        r'^(The Mindful Peace Academy Collection|The Ten Key Elements of Mindfulness Meditation)$'
    )
    page_re = re.compile(r'^\d{1,3}$')
    skip_re = re.compile(
        r'^(I|II|III|IV|Three Basic Elements|The Three Key Elements of Samatha|'
        r'The Four Key Elements of Vipassana|Conclusion|Contents)$'
    )

    for i, line in enumerate(lines):
        if 'Dhyana Tea program team' in line.strip():
            body_start = i
            break
    else:
        sys.exit("Could not find body start in PDF")

    raw = []
    for line in lines[body_start:]:
        s = line.strip()
        if not s or s == '\x0c':
            continue
        if slug_re.search(s) or header_re.match(s) or page_re.match(s) or skip_re.match(s):
            continue
        raw.append(s)

    # Join hyphenated line breaks
    joined = []
    i = 0
    while i < len(raw):
        line = raw[i]
        if line.rstrip().endswith('-') and i + 1 < len(raw):
            nxt = raw[i + 1].lstrip()
            if nxt and nxt[0].islower():
                joined.append(line.rstrip()[:-1] + nxt)
                i += 2
                continue
        joined.append(line)
        i += 1

    body = ' '.join(joined)
    body = re.sub(r'\s+', ' ', body).strip()
    body = body.replace('L iving', 'Living')
    body = re.sub(r'T\s+he\b', 'The', body)
    return body


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(f"Usage: {Path(__file__).name} <docx_path> <pdf_path>")

    docx_path, pdf_path = sys.argv[1], sys.argv[2]

    subprocess.run(
        ['pandoc', docx_path, '-f', 'docx', '-t', 'plain', '--wrap=none',
         '-o', '/tmp/_docx_raw.txt'], check=True
    )
    subprocess.run(
        ['pdftotext', '-layout', pdf_path, '/tmp/_pdf_raw.txt'], check=True
    )

    docx_body = extract_docx_body('/tmp/_docx_raw.txt')
    pdf_body = extract_pdf_body('/tmp/_pdf_raw.txt')

    Path(DOCX_TXT).write_text(docx_body)
    Path(PDF_TXT).write_text(pdf_body)

    print(f"DOCX body → {DOCX_TXT}  ({len(docx_body)} chars)")
    print(f"PDF body  → {PDF_TXT}  ({len(pdf_body)} chars)")

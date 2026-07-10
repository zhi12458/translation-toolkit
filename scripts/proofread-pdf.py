"""Compare manuscript (DOCX English body) against typeset (PDF English body).
Usage: python3 scripts/proofread-pdf.py <docx_path> <pdf_path>
Output: sentences from DOCX not found in PDF, and word-level changes within matched sentences.
"""
import re, sys, subprocess


def extract_docx_en(path):
    with open(path) as f:
        lines = f.readlines()

    body_start = None
    for i, line in enumerate(lines):
        if '生活在这个世间' in line:
            body_start = i
            break
    if body_start is None:
        sys.exit("Could not find body start in DOCX")

    docx_en = []
    skip_next = 0
    for i in range(body_start, len(lines)):
        if skip_next > 0:
            skip_next -= 1
            continue
        line = lines[i].strip()
        if not line:
            continue
        has_cjk = any('\u4e00' <= c <= '\u9fff' for c in line)
        if has_cjk:
            if i + 1 < len(lines) and lines[i+1].strip() == '':
                if i + 2 < len(lines):
                    en_line = lines[i+2].strip()
                    if en_line and not any('\u4e00' <= c <= '\u9fff' for c in en_line):
                        docx_en.append(en_line)
                        skip_next = 2
        else:
            docx_en.append(line)

    # Split into sentences, filter out headings
    text = ' '.join(docx_en)
    sentences = re.split(r'(?<=[.!?"”])\s+', text)
    return [(s.strip(), len(s.strip())) for s in sentences if len(s.strip()) >= 20]


def extract_pdf_en(path):
    with open(path) as f:
        lines = f.readlines()

    body_start = None
    for i, line in enumerate(lines):
        if 'iving in this world' in line:
            body_start = i
            break
    if body_start is None:
        sys.exit("Could not find body start in PDF")

    slug_re = re.compile(r'佛教徒的人生态度.*indd \d+')
    header_re = re.compile(r'^(The Life Attitudes of Buddhists|The Mindful Peace Academy Collection)$')
    page_num_re = re.compile(r'^\d{1,3}$')

    text_lines = []
    for i in range(body_start, len(lines)):
        s = lines[i].strip()
        if not s or s == '\x0c':
            continue
        if slug_re.search(s) or header_re.match(s) or page_num_re.match(s):
            continue
        text_lines.append(s)

    # Join hyphenated breaks
    joined = []
    i = 0
    while i < len(text_lines):
        line = text_lines[i]
        if line.rstrip().endswith('-') and i + 1 < len(text_lines):
            n = text_lines[i+1].lstrip()
            if n and n[0].islower():
                joined.append(line.rstrip()[:-1] + n)
                i += 2
                continue
        joined.append(line)
        i += 1

    body = ' '.join(joined)
    body = re.sub(r'\s+', ' ', body).strip()
    body = body.replace('L iving', 'Living')
    return body


def normalize_for_search(s):
    """Normalize text for fuzzy matching."""
    s = re.sub(r'\s+', ' ', s).strip().lower()
    # Normalize quotes
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    return s


def find_sentence_in_pdf(sentence, pdf_body):
    """Try to locate sentence in PDF body. Returns (found, matched_text)."""
    s_norm = normalize_for_search(sentence)
    # Try full sentence
    if s_norm in pdf_body.lower():
        return True, sentence
    # Try first 60 chars
    key = s_norm[:60]
    if key in pdf_body.lower():
        return True, sentence
    # Try first 30 chars
    key = s_norm[:30]
    if key in pdf_body.lower():
        return True, sentence
    return False, None


def find_word_diff(docx_sentence, pdf_sentence):
    """Find word-level differences between two matched sentences."""
    if not pdf_sentence:
        return []
    dw = re.findall(r'\S+', docx_sentence)
    pw = re.findall(r'\S+', pdf_sentence)
    diffs = []
    for dwi, pwi in zip(dw, pw):
        if dwi.lower() != pwi.lower():
            diffs.append((dwi, pwi))
    if len(dw) != len(pw):
        diffs.append((f"[{len(dw)} words]", f"[{len(pw)} words]"))
    return diffs


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit("Usage: proofread-pdf.py <docx_path> <pdf_path>")

    docx_path, pdf_path = sys.argv[1], sys.argv[2]
    docx_txt = '/tmp/proofread_docx.txt'
    pdf_txt = '/tmp/proofread_pdf.txt'

    subprocess.run(['pandoc', docx_path, '-f', 'docx', '-t', 'plain', '--wrap=none', '-o', docx_txt], check=True)
    subprocess.run(['pdftotext', '-layout', pdf_path, pdf_txt], check=True)

    docx_sentences = extract_docx_en(docx_txt)
    pdf_body = extract_pdf_en(pdf_txt)
    pdf_normalized = normalize_for_search(pdf_body)

    missing = []
    found_count = 0
    for sentence, length in docx_sentences:
        s_norm = normalize_for_search(sentence)
        if s_norm in pdf_normalized:
            found_count += 1
        elif s_norm[:60] in pdf_normalized:
            found_count += 1
        elif s_norm[:30] in pdf_normalized:
            found_count += 1
        else:
            missing.append(sentence)

    print(f"DOCX body sentences: {len(docx_sentences)}")
    print(f"Matched in PDF: {found_count}")
    print(f"Missing: {len(missing)}")
    print()

    if missing:
        print("=== Sentences from DOCX NOT found in PDF ===")
        for i, s in enumerate(missing):
            print(f"\n--- Missing #{i+1} ---")
            print(s[:200])

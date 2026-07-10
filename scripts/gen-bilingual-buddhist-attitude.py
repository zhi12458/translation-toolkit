"""
Generate bilingual.dj for 佛教徒的人生态度.
Source: Chinese from DOCX manuscript.
Target: English from PDF typeset.

Strategy: find each DOCX English paragraph in PDF body, extract
the PDF text region for that paragraph using position boundaries.
"""
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "translate-files/佛教徒的人生态度/定稿 佛教徒的人生态度 善鑫慧炬照禅道靖妙一观轩慈德20260527.docx"
PDF = ROOT / "translate-files/佛教徒的人生态度/0607-二排-果澄-佛教徒的人生态度-一校-多人-0607.pdf"
OUT_DIR = ROOT / "translate-files/佛教徒的人生态度"


def has_cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)


def pandoc(path):
    r = subprocess.run(['pandoc', path, '-f', 'docx', '-t', 'plain', '--wrap=none'],
                       capture_output=True, text=True)
    return r.stdout


def extract_docx_pairs(text):
    """Return [(cn_para, en_para), ...] from body onwards."""
    lines = text.split('\n')
    body_start = None
    for i, l in enumerate(lines):
        if '生活在这个世间' in l:
            body_start = i
            break
    pairs = []
    i = body_start
    while i < len(lines):
        cn = lines[i].strip()
        if not cn or not has_cjk(cn):
            i += 1
            continue
        en = ''
        if i + 2 < len(lines) and lines[i+1].strip() == '':
            ec = lines[i+2].strip()
            if ec and not has_cjk(ec):
                en = ec
                i += 3
            else:
                i += 1
        else:
            i += 1
            continue
        pairs.append((cn, en))
    return pairs


def extract_pdf_body(text):
    """Return cleaned PDF body string."""
    lines = text.split('\n')
    body_start = None
    for i, l in enumerate(lines):
        if 'iving in this world' in l.strip():
            body_start = i
            break
    slug_re = re.compile(r'佛教徒的人生态度.*indd \d+')
    hdr_re = re.compile(r'^(The Life Attitudes of Buddhists|The Mindful Peace Academy Collection)$')
    pn_re = re.compile(r'^\d{1,3}$')
    
    tl = []
    for i in range(body_start, len(lines)):
        s = lines[i].strip()
        if not s or s == '\x0c':
            continue
        if slug_re.search(s) or hdr_re.match(s) or pn_re.match(s):
            continue
        tl.append(s)
    
    # Join hyphenation breaks — handle consecutive breaks
    joined = []
    i = 0
    while i < len(tl):
        line = tl[i].rstrip()
        if line.endswith('-') and i + 1 < len(tl):
            n = tl[i+1].lstrip()
            if n and n[0].islower():
                merged = line[:-1] + n
                # Check if MORE consecutive breaks follow
                j = i + 2
                while j < len(tl) and merged.rstrip().endswith('-'):
                    nn = tl[j].lstrip()
                    if nn and nn[0].islower():
                        merged = merged.rstrip()[:-1] + nn
                        j += 1
                    else:
                        break
                joined.append(merged)
                i = j
                continue
        joined.append(line)
        i += 1
    
    body = ' '.join(joined)
    body = re.sub(r'\s+', ' ', body).strip()
    body = body.replace('L iving', 'Living')
    return body


def norm(s):
    s = re.sub(r'\s+', ' ', s).strip().lower()
    s = s.replace('\u201c', '"').replace('\u201d', '"')
    s = s.replace('\u2018', "'").replace('\u2019', "'")
    return s


def find_positions(pairs, pdf_body):
    """For each DOCX English para, find start position in PDF body.
    Returns list of (start_pos or None, matched_text or None).
    """
    positions = []
    last_pos = 0
    for cn, en in pairs:
        needle = norm(en)
        haystack = norm(pdf_body[last_pos:])
        
        # Try full match
        idx = haystack.find(needle)
        if idx < 0:
            # Try first 80 chars
            key = needle[:80]
            idx = haystack.find(key)
        if idx < 0:
            # Try first 40 chars
            key = needle[:40]
            idx = haystack.find(key)
        if idx < 0:
            # Try first 25 chars
            key = needle[:25]
            idx = haystack.find(key)
        
        if idx >= 0:
            pos = last_pos + idx
            positions.append(pos)
            last_pos = pos + max(len(needle), 30)
        else:
            positions.append(None)
    return positions


def extract_segments(pdf_body, positions):
    """For each position, extract the PDF text region.
    Region extends from positions[i] to positions[i+1] (or end),
    trimmed to avoid bleeding into the next paragraph.
    """
    segments = []
    for i, pos in enumerate(positions):
        if pos is None:
            segments.append(None)
            continue
        
        start = pos
        end = len(pdf_body)
        for j in range(i + 1, len(positions)):
            if positions[j] is not None:
                end = positions[j]
                break
        
        raw = pdf_body[start:end].strip()
        
        # Trim: if raw contains what looks like the NEXT paragraph's heading,
        # cut at the last sentence boundary before it.
        # Headings match patterns like: "I Passive", "1) Expressions", "1. The Definitions"
        heading_pattern = re.compile(
            r'\s+(?=[IVX]+\.?\s+[A-Z]'            # Roman numeral chapter
            r'|\d+\)\s+[A-Z]'                       # 1) Sub-heading
            r'|\(\d+\)\s+[A-Z]'                     # (1) Sub-heading
            r'|\d+\.\s+[A-Z][a-z]+.*?(?:Passive|Pessimism|Abstinence|Focus|Benefit|Transcending|Love|Adapting|Conclusion|Desire|Being|What|How|The|Buddhism|Set|Free|A Middle)'  # Numbered heading
            r')'
        )
        m = heading_pattern.search(raw)
        if m:
            # Cut before this heading
            raw = raw[:m.start()].strip()
        
        segments.append(raw)
    return segments


def generate(pairs, segments, out_path):
    lines = []
    
    # Title
    lines.append('# 佛教徒的人生态度')
    lines.append('# The Life Attitudes of Buddhists')
    lines.append('')
    lines.append('------2014年秋讲于第九届菩提静修营')
    lines.append('---Lecture Given at the 9th Bodhi Meditation Retreat, 2014')
    lines.append('')
    lines.append(' 济群法师 ')
    lines.append('Master Jiqun')
    lines.append('')
    
    # TOC from DOCX
    lines.append('- 一、消极还是积极')
    lines.append('- 二、悲观还是乐观')
    lines.append('- 三、禁欲还是纵欲')
    lines.append('- 四、重生还是重死')
    lines.append('- 五、自利还是利他')
    lines.append('- 六、出世还是入世')
    lines.append('- 七、无情还是多情')
    lines.append('- 八、随缘还是进取')
    lines.append('- 九、结束语')
    lines.append('')
    lines.append('- I. Passive or Proactive')
    lines.append('- II. Pessimism or Optimism')
    lines.append('- III. Abstinence or Indulgence')
    lines.append('- IV. Focus on Life or on Death')
    lines.append('- V. Benefit Oneself or Benefit Others')
    lines.append('- VI. Transcending the World or Engaging with the World')
    lines.append('- VII. To Love or Not to Love')
    lines.append('- VIII. Adapting to Conditions or Striving for Progress')
    lines.append('- IX. Conclusion')
    lines.append('')
    
    # Body
    for (cn, en), seg in zip(pairs, segments):
        target = seg if seg else en
        lines.append(cn)
        lines.append(target)
        lines.append('')
    
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    
    matched = sum(1 for s in segments if s is not None)
    print(f"Written: {out_path}")
    print(f"  Paragraphs: {len(pairs)}, matched from PDF: {matched}, fallback to DOCX: {len(pairs) - matched}")


if __name__ == '__main__':
    print("Extracting DOCX...")
    docx_text = pandoc(DOCX)
    pairs = extract_docx_pairs(docx_text)
    print(f"  Pairs: {len(pairs)}")
    
    print("Extracting PDF...")
    r = subprocess.run(['pdftotext', '-layout', PDF, '/tmp/_bilingual_pdf.txt'], check=True)
    with open('/tmp/_bilingual_pdf.txt') as f:
        pdf_raw = f.read()
    pdf_body = extract_pdf_body(pdf_raw)
    print(f"  PDF body: {len(pdf_body)} chars")
    
    print("Finding positions...")
    positions = find_positions(pairs, pdf_body)
    found = sum(1 for p in positions if p is not None)
    print(f"  Found: {found}/{len(pairs)}")
    
    print("Extracting segments...")
    segments = extract_segments(pdf_body, positions)
    
    out = OUT_DIR / "bilingual.dj"
    generate(pairs, segments, out)

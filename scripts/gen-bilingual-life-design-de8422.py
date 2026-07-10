"""Generate bilingual.dj from DOCX for 「生命也可以被设计的」.
One-pass approach: walk interleaved paragraphs, handle multi-CN sequences.
"""
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "translate-files/生命也可以被设计的/中英文定稿-260324-生命也是可以被设计的-妙一宽山静雅初翻 慈鎏妙一审议 宽山定稿.docx"
OUT_DIR = ROOT / "translate-files/生命也可以被设计的"

def has_cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)

def pandoc(path):
    r = subprocess.run(['pandoc', path, '-f', 'docx', '-t', 'plain', '--wrap=none'],
                       capture_output=True, text=True)
    return r.stdout

def split_toc_line(line):
    s = line.strip()
    s = re.sub(r'\s+\d+\s*$', '', s)
    m = re.match(r'^(.+[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef）\)])\s+([A-Z].+)$', s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None

def extract_toc_entries(text):
    lines = text.split('\n')
    toc_start = None
    toc_end = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s.startswith('一、') and ('EDUCATION' in s or 'NURTURING' in s):
            if toc_start is None:
                toc_start = i
        if toc_start is not None and s and has_cjk(s) and re.search(r'\d+$', s):
            toc_end = i
        elif toc_start is not None and toc_end is not None and s and not re.search(r'\d+$', s) and has_cjk(s):
            break

    cn_entries = []
    en_entries = []
    for i in range(toc_start, toc_end + 1):
        cn, en = split_toc_line(lines[i])
        if cn and en:
            cn_entries.append(cn)
            en_entries.append(en)
    return cn_entries, en_entries

def extract_body_pairs(text):
    """One-pass: walk interleaved paras, joining consecutive same-language lines."""
    lines = text.split('\n')

    # Find body start
    body_start = None
    for i, l in enumerate(lines):
        if '现在是一个浮躁的时代' in l:
            body_start = i
            break

    # Extract non-blank paragraphs with language tags
    tagged = []
    for l in lines[body_start:]:
        s = l.strip()
        if s:
            tagged.append(('cn' if has_cjk(s) else 'en', s))

    # Accumulate consecutive same-language paragraphs (page-break splits only, not headings)
    merged = []
    for lang, text in tagged:
        # Heading-like patterns that should not be merged
        prev_is_heading = (merged and merged[-1][0] == lang
                           and bool(re.match(r'^[\dIVX]+[\.\s]', merged[-1][1].strip())
                                    and len(merged[-1][1].strip()) < 60))
        if (merged and merged[-1][0] == lang
                and not prev_is_heading
                and len(merged[-1][1]) > 30
                and not re.search(r'[。！？：）\u201d\u2019\uff0c\uff0e\.!\?]$', merged[-1][1])):
            # Long previous line, doesn't end naturally → page-break split, join
            merged[-1] = (lang, merged[-1][1].rstrip() + text.lstrip())
        else:
            merged.append((lang, text))

    # Build pairs: group consecutive same-language items into blocks, then zip
    blocks = []
    for lang, text in merged:
        if blocks and blocks[-1][0] == lang:
            blocks[-1][1].append(text)
        else:
            blocks.append((lang, [text]))

    pairs = []
    i = 0
    while i < len(blocks):
        if blocks[i][0] == 'cn':
            cn_block = blocks[i][1]
            # Find next EN block
            if i + 1 < len(blocks) and blocks[i+1][0] == 'en':
                en_block = blocks[i+1][1]
                n = min(len(cn_block), len(en_block))
                for j in range(n):
                    pairs.append((cn_block[j], en_block[j]))
                if len(cn_block) != len(en_block):
                    print(f"  WARNING: block mismatch CN={len(cn_block)} EN={len(en_block)} at CN[{j}]: {cn_block[j][:60]}...")
                i += 2
            else:
                print(f"  WARNING: CN block without EN block: {cn_block[0][:60]}...")
                i += 1
        else:
            print(f"  WARNING: orphan EN block: {blocks[i][1][0][:60]}...")
            i += 1

    return pairs

SANSKRIT = [
    'bodhisattva', 'bodhicitta', 'samsara', 'Dharma', 'karma',
    'nirvana', 'Sangha', 'sutra', 'Mahayana', 'Sravaka',
    'Vinaya', 'Lamrim', 'Ksitigarbha', 'Samantabhadra',
    'Chan', 'Arhatship', 'Theravada', 'buddha', 'Buddha',
    'buddhas', 'Buddhas', 'Bodhisattva', 'Bodhisattvas',
]

def apply_fixes(en_text, italicized):
    en_text = re.sub(r'(\d)\.([A-Z][a-z])', r'\1. \2', en_text)
    en_text = re.sub(r'(said|says),\"', r'\1, "', en_text)
    en_text = re.sub(r'\.([A-Z][a-z])', r'. \1', en_text)
    for term in SANSKRIT:
        if term not in italicized:
            pattern = re.compile(r'\b' + re.escape(term) + r'\b')
            m = pattern.search(en_text)
            if m:
                s, e = m.start(), m.end()
                en_text = en_text[:s] + '*' + en_text[s:e] + '*' + en_text[e:]
                italicized.add(term)
    return en_text

def generate(toc_cn, toc_en, pairs, out_path):
    italicized = set()
    lines = []

    lines.append('# 生命也是可以被设计的')
    lines.append('# Life Can Also Be Designed')
    lines.append('')
    lines.append('济群法师 2025年冬为母爱书院开示')
    lines.append('A teaching given by the Master Jiqun in the winter of 2025 at Amrita Retreat Center for Motherly Love Academy')
    lines.append('')

    for e in toc_cn:
        lines.append(f'- {e}')
    lines.append('')
    for e in toc_en:
        lines.append(f'- {e}')
    lines.append('')

    for cn, en in pairs:
        en_fixed = apply_fixes(en, italicized)
        lines.append(cn)
        lines.append(en_fixed)
        lines.append('')

    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Written: {out_path}")
    print(f"  TOC entries: {len(toc_cn)}")
    print(f"  Body pairs: {len(pairs)}")
    print(f"  Sanskrit italicized: {sorted(italicized)}")

if __name__ == '__main__':
    print("Extracting DOCX...")
    text = pandoc(DOCX)

    print("Extracting TOC...")
    toc_cn, toc_en = extract_toc_entries(text)
    for cn, en in zip(toc_cn, toc_en):
        print(f"  {cn}  →  {en}")

    print("Extracting body...")
    pairs = extract_body_pairs(text)
    print(f"  Pairs: {len(pairs)}")

    out = OUT_DIR / "bilingual.dj"
    generate(toc_cn, toc_en, pairs, out)

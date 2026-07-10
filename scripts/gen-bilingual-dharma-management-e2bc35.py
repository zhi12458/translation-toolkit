"""Extract source.dj and bilingual.dj from .docx.md file.

Handles:
- CN/EN paragraph pairs (CN line → EN line)
- Headings with merged CN+EN on same line (pandoc artifact: CN**EN)
- TOC with markdown links [CN text](#anchor)
- {#anchor} pandoc heading anchors
- Markdown heading cleanup
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "translate-files/佛法与企业管理/副本59 佛法与企业管理-maple 初翻.docx.md"
OUT = ROOT / "translate-files/佛法与企业管理"

def has_cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)

def strip_anchors(s):
    """Remove {#anchor} and markdown links [text](#anchor) — keep text."""
    s = re.sub(r'\{#[^}]*\}', '', s)          # {#anchor}
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', s)  # [text](#link) → text
    return s

def split_cnen(line):
    """Split merged CN+EN line. First strips anchors, then finds CJK→EN boundary."""
    s = strip_anchors(line).strip()
    if not has_cjk(s):
        return ('', s)
    # Find where CJK ends and ASCII English begins
    # Pattern: CJK, optional ws, optional *, optional ws, then English letter
    m = re.search(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]\s*\**\s*([A-Za-z])', s)
    if m:
        split_at = m.start(1)
        cn = s[:split_at].rstrip('* ').strip()
        en = s[split_at:].strip()
        if en and not has_cjk(en):
            return (cn, en)
    return (s, '')

def clean_cn(s):
    """Clean CN heading/paragraph."""
    s = re.sub(r'^\d+\.\s*', '', s)           # leading number (e.g. "1. ")
    s = re.sub(r'^#+\s*\**', '', s)           # heading markers: # **
    s = re.sub(r'\**\s*$', '', s)             # trailing **
    s = re.sub(r'\t\d+$', '', s)              # trailing page number
    s = s.strip()
    return s

def clean_en(s):
    """Clean EN line."""
    s = re.sub(r'^\d+[、,.]\s*', '', s)       # leading number/separator
    s = re.sub(r'\*+$', '', s)                # trailing orphaned italic * (from split)
    s = s.strip()
    return s

def is_toc_line(line, cn_raw):
    """True if this looks like a TOC entry (markdown link or tab+page-number)."""
    if re.search(r'\[.*\]\(.*\)', line):
        return True
    if re.search(r'\t\d+', cn_raw):
        return True
    return False

def parse_doc(text):
    """Parse into list of (cn, en) pairs."""
    lines = text.split('\n')
    pairs = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        stripped = strip_anchors(line)
        has_cn = has_cjk(stripped)

        if has_cn:
            cn_raw, en_raw = split_cnen(line)

            if en_raw:
                # Merged CN+EN on same line
                pairs.append((clean_cn(cn_raw), clean_en(en_raw)))
                i += 1
                continue

            # Look ahead for EN
            nxt = lines[i+1].strip() if i+1 < len(lines) else ''
            nnxt = lines[i+2].strip() if i+2 < len(lines) else ''

            if nxt and not has_cjk(nxt) and not is_toc_line(line, cn_raw):
                # Standard: CN → EN
                pairs.append((clean_cn(cn_raw), clean_en(nxt)))
                i += 2
            elif not nxt and nnxt and not has_cjk(nnxt) and not is_toc_line(line, cn_raw):
                # CN → blank → EN (heading pattern)
                pairs.append((clean_cn(cn_raw), clean_en(nnxt)))
                i += 3
            else:
                # Solo CN (TOC entry, orphan, or heading)
                pairs.append((clean_cn(cn_raw), ''))
                i += 1
        else:
            # Pure EN — TOC entry, pair with first unpaired CN TOC entry
            en = clean_en(line)
            for j in range(len(pairs)):
                if not pairs[j][1] and has_cjk(pairs[j][0]):
                    pairs[j] = (pairs[j][0], en)
                    break
            else:
                pairs.append(('', en))
            i += 1

    return pairs

def classify(pairs):
    """Classify each pair as title, subtitle, toc, heading, or para."""
    result = []
    # Pairs 0-1: title and subtitle
    result.append(('title', 0))
    result.append(('subtitle', 1))
    # Pairs 2-9: TOC (一、 through 八、)
    for i in range(2, min(10, len(pairs))):
        result.append(('toc', i))
    # Remaining: heuristics
    for i in range(10, len(pairs)):
        cn = pairs[i][0]
        if re.match(r'^[一二三四五六七八九十]、', cn):
            result.append(('heading', i))
        elif re.match(r'^\d+\\?\.\s', cn):
            result.append(('subheading', i))
        else:
            result.append(('para', i))
    return result

def write_bilingual(pairs, out_path):
    types = classify(pairs)
    lines = []
    # Title
    lines.append('# ' + pairs[0][0])
    lines.append('# ' + pairs[0][1])
    lines.append('')
    # Subtitle
    lines.append('---' + pairs[1][0])
    lines.append('---' + pairs[1][1])
    lines.append('')
    # Author
    lines.append('济群法师')
    lines.append('Master Jiqun')
    lines.append('')
    # TOC — CN block then EN block (not interleaved)
    for typ, idx in types:
        if typ == 'toc':
            lines.append('- ' + pairs[idx][0])
    lines.append('')
    for typ, idx in types:
        if typ == 'toc':
            lines.append('- ' + pairs[idx][1])
    lines.append('')
    # Body
    for typ, idx in types:
        if typ in ('title', 'subtitle', 'toc'):
            continue
        cn, en = pairs[idx]
        if cn:
            lines.append(cn)
        if en:
            lines.append(en)
        if cn or en:
            lines.append('')
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"bilingual.dj: {len(pairs)} pairs -> {out_path}")

def write_source(pairs, out_path):
    lines = [cn for cn, en in pairs if cn]
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(f"source.dj: {len(lines)} CN lines -> {out_path}")

if __name__ == '__main__':
    text = SRC.read_text()
    pairs = parse_doc(text)
    print(f"Parsed {len(pairs)} pairs from .docx.md")
    solo_cn = sum(1 for cn, en in pairs if cn and not en)
    solo_en = sum(1 for cn, en in pairs if en and not cn)
    both = sum(1 for cn, en in pairs if cn and en)
    print(f"  Both: {both}, CN-only: {solo_cn}, EN-only: {solo_en}")
    write_source(pairs, OUT / "source.dj")
    write_bilingual(pairs, OUT / "bilingual.dj")

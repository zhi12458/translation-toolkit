"""Generate bilingual.dj from DOCX manuscript only (no PDF).
Source: Chinese from DOCX. Target: English from DOCX.
"""
import re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "translate-files/佛教徒的人生态度/定稿 佛教徒的人生态度 善鑫慧炬照禅道靖妙一观轩慈德20260527.docx"
OUT_DIR = ROOT / "translate-files/佛教徒的人生态度"

def has_cjk(s):
    return any('\u4e00' <= c <= '\u9fff' for c in s)

def pandoc(path):
    r = subprocess.run(['pandoc', path, '-f', 'docx', '-t', 'plain', '--wrap=none'],
                       capture_output=True, text=True)
    return r.stdout

def extract_pairs(text):
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

SANSKRIT = [
    'bodhisattva', 'bodhicitta', 'samsara', 'Dharma', 'karma',
    'nirvana', 'Sangha', 'sutra', 'Mahayana', 'Sravaka',
    'Vinaya', 'Lamrim', 'Ksitigarbha', 'Samantabhadra',
    'Chan', 'Arhatship', 'Theravada',
]

def apply_fixes(en_text, italicized):
    """Apply typesetting fixes to English text."""
    # Fix: "2.How" → "2. How"
    en_text = re.sub(r'(\d)\.([A-Z][a-z])', r'\1. \2', en_text)
    # Fix: "said,"When → "said, "When
    en_text = re.sub(r'(said|says),"', r'\1, "', en_text)
    # Italicize Sanskrit on first occurrence
    for term in SANSKRIT:
        if term not in italicized:
            pattern = re.compile(r'\b' + re.escape(term) + r'\b')
            m = pattern.search(en_text)
            if m:
                s, e = m.start(), m.end()
                en_text = en_text[:s] + '*' + en_text[s:e] + '*' + en_text[e:]
                italicized.add(term)
    return en_text

def generate(pairs, out_path):
    italicized = set()
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
    
    # TOC
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
    for cn, en in pairs:
        en_fixed = apply_fixes(en, italicized)
        lines.append(cn)
        lines.append(en_fixed)
        lines.append('')
    
    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Written: {out_path}")
    print(f"  Paragraphs: {len(pairs)}")
    print(f"  Sanskrit italicized: {sorted(italicized)}")

if __name__ == '__main__':
    print("Extracting DOCX...")
    text = pandoc(DOCX)
    pairs = extract_pairs(text)
    print(f"  Pairs: {len(pairs)}")
    
    out = OUT_DIR / "bilingual.dj"
    generate(pairs, out)

# Bold fragments & conjoined paragraphs — fix patterns

From session fixing `静心学堂学员手册.md` (1575→1478 lines, ~100 fixes).

## Pattern A: Bold marker fragmentation

**Problem**: `**...text...**` block split across blank line with stray `**` markers:

```
**第三条 特色——依据五大要素，构建次第修学。营造良好氛围，提供有效**

引导。
```

**Detection**: Line ends with `**`, next non-blank line continues the sentence (does NOT start with `**`).

**Fix** (Python):
```python
# curr ends with **, nxt is continuation (no leading **)
curr_fixed = curr.rstrip()[:-2].rstrip()  # strip trailing **
nxt_fixed = nxt.lstrip()
if nxt_fixed.endswith('**'):
    nxt_fixed = nxt_fixed[:-2].rstrip()
    joined = curr_fixed + nxt_fixed + '**'
else:
    joined = curr_fixed + nxt_fixed  # lost closing ** — may need manual fix
```

### Anti-pattern: Complete bold items

Do NOT join when BOTH lines are complete bold blocks (start+end with `**`):

```
**第一条 ...之道。**    ← DON'T JOIN
                        ← blank line
**第二条 ...合一。**    ← DON'T JOIN
```

**Detection**: Both `curr` and `nxt` start with `**` and end with `**`.

## Pattern B: Conjoined paragraphs (Type 2)

Separate sections merged into one line. Common cases:

### Section headers merged with body
```
导言：这本指引怎么用这本指引是什么这是一本修学地图...
```
→ Split into:
```
导言：这本指引怎么用

这本指引是什么

这是一本修学地图...
```

### Song titles merged mid-lyrics
```
...生生世世不再久违《菩提花开》如果你渴求一滴水...
```
→ Split into:
```
...生生世世不再久违

### 《菩提花开》

如果你渴求一滴水...
```

### List items merged into one line
```
不在班级群发布...不从事违法活动不在班级平台拉拢...
```
→ Split into bullet list:
```
- 不在班级群发布...
- 不从事违法活动
- 不在班级平台拉拢...
```

**Approach**: Manual string replacements for known patterns. Regex is unreliable for semantic splits.

## Pattern C: Stray page numbers

Standalone digits at line ends, often from PDF page number artifacts:
- `42`, `43`, `46`, `47` at end of content lines

**Fix**: Strip trailing digits that aren't part of dates, durations, or course numbers.

## Pattern D: Encoding artifacts

`川` (U+5DDD) replacing curly quotes `"` (U+201C/U+201D):
```
把" 道理川变成" 自己的川    →    把"道理"变成"自己的"
```

**Fix**: Replace `" 道理川` → `"道理"`, `" 自己的川` → `"自己的"`.

## Multi-pass workflow

1. **Pass 1 — Join word fragments**: Scan for lines split by blank line where first line doesn't end with `。！？` and neither line is structural (header/list/table). Skip complete bold items.
2. **Pass 2 — Split conjoined**: Apply known string replacements for merged sections, song transitions, list items.
3. **Pass 3 — Clean artifacts**: Fix stray `**` markers, encoding issues, stray page numbers.
4. **Verify**: `git diff` after each pass; `git checkout` if over-aggressive.

## Rejected heuristics

- **Short-line join** (< 15 chars): Over-joins section headers (`中级和高级（以后的事）`) with body, and Q&A pairs (`正念是什么？\n\n就是...`). Only use for clear mid-word fragments.
- **Blind `**` stripping**: Removes valid bold formatting from complete bold items.

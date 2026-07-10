# Termbase Rebuild (from absorbed termbase-management)

How to rebuild the terms DuckDB from source spreadsheets. This is the full pipeline from the now-archived `termbase-management` skill.

## Prerequisites

```bash
pip install openpyxl odfpy pyyaml duckdb
```

## Step 1: Inspect spreadsheet structure

```python
from openpyxl import load_workbook
wb = load_workbook(path, read_only=True, data_only=True)
for sn in wb.sheetnames:
    ws = wb[sn]
    rows = [list(r) for r in ws.iter_rows(min_row=1, max_row=6, values_only=True)]
    print(f"[{sn}] {sum(1 for _ in ws.iter_rows())} rows, cols: {len(rows[0]) if rows else 0}")
    for r in rows[:5]: print(f"  {r}")
```

For ODS files, use odfpy:
```python
from odf.opendocument import load as odf_load
from odf.table import Table, TableRow, TableCell
from odf.text import P

doc = odf_load(path)
for table in doc.getElementsByType(Table):
    for row in table.getElementsByType(TableRow):
        cells = row.getElementsByType(TableCell)
        vals = []
        for cell in cells:
            text = ''
            for p in cell.getElementsByType(P):
                for node in p.childNodes:
                    if node.nodeType == node.TEXT_NODE:
                        text += node.data
            vals.append(text.strip() if text else None)
```

## Step 2: Convert to CSV + YAML

### Cleaning
- Strip trailing None/empty values from each row: `while row and not row[-1]: row.pop()`
- Skip entirely empty rows
- Pad all rows to the max column count

### Duplicate header handling
Some sheets have duplicate column names (e.g., two `英文` columns in paired layout). Deduplicate with suffixes:
```python
from collections import Counter
def dedup_headers(headers):
    seen = Counter()
    result = []
    for h in headers:
        s = str(h) if h else ''
        if s in seen:
            seen[s] += 1
            result.append(f"{s}_{seen[s]}")
        else:
            seen[s] = 1
            result.append(s)
    return result
```

### Output formats
- **CSV**: `csv.writer` — column-major, preserves all raw data
- **YAML**: `yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False, width=200)` — list of dicts

## Step 3: Load into DuckDB

```python
import duckdb
con = duckdb.connect('termlib.duckdb')

# Simple CSVs work with auto-detect:
con.execute("""
    CREATE TABLE table_name AS 
    SELECT * FROM read_csv_auto('file.csv', header=true, all_varchar=true)
""")
```

### Pitfall: Multiline CSV fields
CSV files with embedded newlines (common in glossary example-sentence columns) break DuckDB's auto-sniffer. Fall back to Python csv.reader:

```python
import csv
with open(path, 'r', encoding='utf-8') as f:
    rows = list(csv.reader(f))

headers = rows[0]
data = rows[1:]

col_defs = ', '.join(f'"{h}" VARCHAR' for h in cleaned_headers)
con.execute(f'CREATE TABLE "{table}" ({col_defs})')

batch_size = 500
for i in range(0, len(data), batch_size):
    batch = data[i:i+batch_size]
    placeholders = ', '.join(['(' + ', '.join(['?' for _ in headers]) + ')' for _ in batch])
    flat = [v for row in batch for v in row]
    con.execute(f'INSERT INTO "{table}" VALUES {placeholders}', flat)
```

### Pitfall: DuckDB CLI opens in-memory by default
Running plain `duckdb` gives an empty database. Always pass the file path:
```
duckdb path/to/termlib.duckdb
```

## Step 4: Create unified views

See `references/unified-view.sql` for the pattern. Key patterns:
- `UNION ALL` across all source tables
- Normalize column names to `zh`, `en`, `loc` (出处), `source`
- For paired-column sheets (e.g., `中文/英文` + `补充内容/英文_1`), emit two UNION branches
- Filter out rows where zh or en is NULL/empty

## Pitfalls

- **ODS reading**: Must traverse `odf.text.P` child elements, not direct text nodes
- **Duplicate headers**: JSON/YAML dict silently overwrites duplicate keys — always deduplicate
- **Multiline CSV + DuckDB**: `read_csv_auto` fails on CSVs with quoted newlines — use Python csv.reader
- **DuckDB path**: Always explicit file path; `duckdb` alone is in-memory
- **`execute_code` sandbox**: Does NOT share pip-installed packages — use `terminal` for Python scripts

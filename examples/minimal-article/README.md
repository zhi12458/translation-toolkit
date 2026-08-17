# Minimal reproducible article

This public fixture contains no private translation text. It is intentionally
small enough to verify the toolkit after installation.

From the toolkit root:

```sh
./scripts/gen-bilingual.py \
  examples/minimal-article/source.dj \
  examples/minimal-article/target.dj \
  --output examples/minimal-article/bilingual.dj

./scripts/check-translation.py examples/minimal-article --strict --json \
  --output examples/minimal-article/qa-report.json
```

`bilingual.dj` and `qa-report.json` are generated files. Remove them after the
smoke test. `source-analysis.json` and `semantic-review.json` are deterministic,
human-authored internal fixtures with real hashes; neither claims an external
model run. Do not use this small article as a semantic Buddhist translation gold
standard; the public model-comparison cases live in
`tests/fixtures/semantic-gold.json`.

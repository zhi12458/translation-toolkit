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
smoke test; do not use this fixture as a semantic Buddhist translation gold
standard.

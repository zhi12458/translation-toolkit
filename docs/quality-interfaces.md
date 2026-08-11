# Quality-control interfaces

The schemas in `schemas/` make project decisions and gate outcomes reviewable
outside an agent conversation.

| File | Purpose | Owner |
|---|---|---|
| `translation-project.yaml` | Author/translator, genre, audience, register, scripture/Sanskrit policy, versions, review and approval attestations | project lead |
| `term-map.yaml` | One frozen project sense per Chinese term, with preferred, allowed, and forbidden renderings plus evidence and decision state | translator + terminology reviewer |
| `review-findings.jsonl` | One finding per line with paragraph ID, severity, category, resolution state, and reviewer | independent reviewer |
| `qa-report.json` | Machine gate outcome with explicit `PASS/WARN/SKIP/FAIL` statuses | `check-translation.py` |

JSON Schema validates YAML data models because YAML 1.2 is compatible with the
JSON data model. To avoid adding a YAML parser dependency, checked YAML files
use the JSON-syntax subset of YAML 1.2; the gate parses them directly and rejects
unsupported or malformed input instead of guessing.

## Release policy

Draft mode may contain acknowledged warnings and skips. Strict mode must have:

- no `FAIL`;
- no `SKIP`;
- `release.level` set to `public` or `sensitive`;
- a present and non-empty term map;
- frozen-term coverage of at least 99%;
- a present and fresh bilingual file;
- a valid `translation-project.yaml` release policy.

Strict releases require independent review, no unresolved (`open` or `deferred`)
`critical` or `major` finding, and named human approval. The mechanical gate cannot decide whether a
Buddhist doctrinal interpretation is correct.

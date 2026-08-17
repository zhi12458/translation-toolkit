# Quality-control interfaces

The schemas in `schemas/` make project decisions and gate outcomes reviewable
outside an agent conversation.

| File | Purpose | Owner |
|---|---|---|
| `translation-project.yaml` | Author/translator, source origin, delivery format, register, external semantic-review policy, scripture/Sanskrit policy, versions, review and approval attestations | project lead |
| `term-map.yaml` | One frozen project sense per Chinese term, with preferred, allowed, and forbidden renderings plus evidence and decision state | translator + terminology reviewer |
| `source-analysis.json` | Blind, source-hash-bound Chinese predicates, roles, relations, scope, ambiguity, and translation constraints; never produced from an English draft | source-only semantic analyst |
| `review-findings.jsonl` | One finding per line with paragraph ID, severity, category, resolution state, reviewer, and optional stage/model/hash provenance | independent reviewer |
| `semantic-review.json` | Final bilingual accuracy-review round, disposition, and source/target/findings freshness hashes | independent accuracy reviewer |
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
- a schema-valid `source-analysis.json` bound to the current source, project
  metadata, term map, and exact non-blank paragraph coverage;
- a post-polish `semantic-review.json` (`review_round >= 2`) whose source,
  target, and findings hashes match the current files and whose status is
  `clear` with zero blocking findings;
- a valid `translation-project.yaml` release policy.

Strict releases require independent review, no unresolved (`open` or `deferred`)
`critical` or `major` finding, and named human approval. The mechanical gate cannot decide whether a
Buddhist doctrinal interpretation is correct.

`source_origin` and `delivery_format` are intentionally separate. An oral talk
compiled as a publication article or book cannot use conversational formality;
publication prose remains warm and accessible while avoiding chatty
contractions, slang, and casual fragments. Sensitive releases and projects with
`external_semantic_review: deny` accept only `provider: internal` semantic
artifacts. See `semantic-review-workflow.zh-CN.md` for the information firewalls,
credential rules, and benchmark protocol.

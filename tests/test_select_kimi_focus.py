import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


kimi = load_module("mpi_kimi_for_focus_tests", ROOT / "scripts" / "kimi-source-analysis.py")
selector = load_module("mpi_select_kimi_focus", ROOT / "scripts" / "select-kimi-focus.py")


def make_project(tmp_path):
    project = tmp_path / "article"
    project.mkdir()
    (project / "source.dj").write_text("有人得到食粮。\n\n慈悲需要智慧。\n", encoding="utf-8")
    (project / "target.dj").write_text(
        "ENGLISH-TARGET-MUST-NOT-BE-READ\n\nSECOND-TARGET\n", encoding="utf-8"
    )
    (project / "term-map.yaml").write_text(
        json.dumps({"version": 1, "terms": []}, ensure_ascii=False), encoding="utf-8"
    )
    metadata = {
        "project_id": "focused-routing",
        "title": "聚焦路由",
        "author": "MPI",
        "translator": "Test",
        "source_origin": "written_text",
        "delivery_format": "publication_article",
        "external_semantic_review": "allow",
        "genre": "written_article",
        "audience": "general readers",
        "register": {"voice": "gentle", "formality": "neutral"},
        "cultural_bridge": {"policy": "none"},
        "scriptures": [],
        "sanskrit": {"diacritics": True, "first_mention": "english_and_sanskrit"},
        "versions": {"toolkit_commit": "1234567", "termbase": "test"},
        "release": {"level": "draft", "independent_review_required": False},
    }
    (project / "translation-project.yaml").write_text(
        json.dumps(metadata, ensure_ascii=False), encoding="utf-8"
    )
    inputs = kimi.load_project(project)
    paragraphs = [
        {
            "paragraph_id": "L1",
            "predicates": [
                {
                    "predicate": "得到",
                    "canonical_meaning": "取得食粮",
                    "evidence": "得到",
                    "participants": [
                        {
                            "role": "agent",
                            "participant": None,
                            "evidence": None,
                            "evidence_status": "ambiguous",
                            "notes": "获取者不确定",
                        },
                        {
                            "role": "theme",
                            "participant": "食粮",
                            "evidence": "得到食粮",
                            "evidence_status": "explicit",
                            "notes": "取得的对象",
                        },
                    ],
                }
            ],
            "relations": [],
            "operators": [],
            "references_and_ellipsis": [],
            "competing_interpretations": [
                {
                    "interpretation": "获取者需由上下文判断",
                    "supporting_evidence": ["得到食粮"],
                    "counterevidence": [],
                    "evidence_status": "ambiguous",
                }
            ],
            "must_preserve": ["得到的动作类型"],
            "must_not_invent": ["不得擅定获取者"],
            "status": "needs_human",
        },
        {
            "paragraph_id": "L3",
            "predicates": [
                {
                    "predicate": "需要",
                    "canonical_meaning": "慈悲以智慧为必要条件",
                    "evidence": "需要",
                    "participants": [],
                }
            ],
            "relations": [],
            "operators": [],
            "references_and_ellipsis": [],
            "competing_interpretations": [],
            "must_preserve": ["需要关系"],
            "must_not_invent": ["不得擅增时态"],
            "status": "clear",
        },
    ]
    validated = kimi.validate_batch_content(
        json.dumps({"paragraphs": paragraphs}, ensure_ascii=False),
        inputs.paragraphs,
        kimi.load_analysis_schema(),
        inputs.source,
    )
    artifact = kimi.build_artifact(
        inputs=inputs,
        analyses=validated,
        model="kimi-k3",
        reasoning_effort="high",
        batch_size=1,
        request_count=2,
        timeout=600,
        max_tokens=32768,
    )
    artifact["provider"] = "internal"
    artifact["model"] = "internal-semantic-role"
    (project / "source-analysis.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return project


def test_selects_only_evidence_based_ambiguity(tmp_path, capsys):
    project = make_project(tmp_path)
    assert selector.main([str(project)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["total_source_paragraphs"] == 2
    assert output["selected_count"] == 1
    assert output["selected"][0]["paragraph_id"] == "L1"
    assert "needs_human" in output["selected"][0]["reasons"]
    assert "ambiguous_semantic_role" in output["selected"][0]["reasons"]


def test_manual_escalation_and_cli_argument_output_preserve_source_order(tmp_path, capsys):
    project = make_project(tmp_path)
    assert selector.main([str(project), "--include", "L3", "--format", "args"]) == 0
    assert capsys.readouterr().out.strip() == "--paragraph-id L1 --paragraph-id L3"


def test_selector_never_reads_english_target(monkeypatch, tmp_path):
    project = make_project(tmp_path)
    original = Path.read_bytes

    def guarded(path, *args, **kwargs):
        if path.name == "target.dj":
            raise AssertionError("selector attempted to read English target")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    assert selector.main([str(project), "--format", "ids"]) == 0


def test_stale_or_incomplete_canonical_analysis_is_rejected(tmp_path, capsys):
    project = make_project(tmp_path)
    path = project / "source-analysis.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["paragraphs"] = document["paragraphs"][:1]
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    assert selector.main([str(project)]) == 1
    assert "failed local validation" in capsys.readouterr().err

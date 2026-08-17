import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(name, *args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_freeze_target_validates_and_writes_atomically(tmp_path):
    source = tmp_path / "source.dj"
    draft = tmp_path / "draft.dj"
    target = tmp_path / "target.dj"
    source.write_text("标题\n\n正文\n", encoding="utf-8")
    draft.write_text("Title\n\nBody\n", encoding="utf-8")

    completed = run_script("freeze-target.py", source, draft, "--output", target)

    assert completed.returncode == 0, completed.stderr
    assert target.read_text(encoding="utf-8") == "Title\n\nBody\n"


def test_freeze_target_rejects_alignment_drift_without_overwrite(tmp_path):
    source = tmp_path / "source.dj"
    draft = tmp_path / "draft.dj"
    target = tmp_path / "target.dj"
    source.write_text("标题\n\n正文\n", encoding="utf-8")
    draft.write_text("Title\nBody\n\n", encoding="utf-8")
    target.write_text("KEEP\n", encoding="utf-8")

    completed = run_script("freeze-target.py", source, draft, "--output", target)

    assert completed.returncode == 1
    assert target.read_text(encoding="utf-8") == "KEEP\n"


def test_source2dj_normalizes_utf8_and_line_endings(tmp_path):
    source = tmp_path / "原稿.txt"
    output = tmp_path / "source.dj"
    source.write_bytes("第一段\r\n\r\n第二段".encode("utf-8"))

    completed = run_script("source2dj.py", source, output)

    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == "第一段\n\n第二段\n"
    assert "sha256=" in completed.stdout


def test_source2dj_rejects_alias_without_modifying_input(tmp_path):
    source = tmp_path / "source.dj"
    source.write_text("原文\n", encoding="utf-8")

    completed = run_script("source2dj.py", source, source)

    assert completed.returncode == 1
    assert source.read_text(encoding="utf-8") == "原文\n"


def test_docx_and_docx_render_wrappers_preserve_old_output_on_pandoc_failure(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pandoc = bin_dir / "pandoc"
    pandoc.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
    pandoc.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"

    docx = tmp_path / "input.docx"
    docx.write_bytes(b"not-a-real-docx")
    source_output = tmp_path / "source.dj"
    source_output.write_text("old source\n", encoding="utf-8")
    source_result = run_script("docx2dj.py", docx, source_output, env=environment)

    target = tmp_path / "target.dj"
    target.write_text("English\n", encoding="utf-8")
    docx_output = tmp_path / "target.docx"
    docx_output.write_bytes(b"old docx")
    target_result = run_script(
        "dj2docx.py", target, docx_output, "--kind", "target", env=environment
    )

    assert source_result.returncode == 1
    assert target_result.returncode == 1
    assert source_output.read_text(encoding="utf-8") == "old source\n"
    assert docx_output.read_bytes() == b"old docx"


def test_check_docx_rejects_invalid_zip_without_writing_report(tmp_path):
    source = tmp_path / "target.dj"
    docx = tmp_path / "target.docx"
    report = tmp_path / "docx-qa-report.json"
    source.write_text("English\n", encoding="utf-8")
    docx.write_bytes(b"not a zip")

    completed = run_script("check-docx.py", source, docx, "--output", report)

    assert completed.returncode == 1
    assert not report.exists()


def test_term_map_invokes_locked_search_and_writes_receipts(tmp_path):
    source = tmp_path / "source.dj"
    candidates = tmp_path / "term-candidates.json"
    output = tmp_path / "term-map.yaml"
    receipts = tmp_path / "term-search-receipts.jsonl"
    source.write_text("理解空性。\n", encoding="utf-8")
    candidates.write_text(
        json.dumps({"terms": [{"source": "空性", "sense": "佛教义理"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = run_script(
        "build-term-map.py",
        source,
        candidates,
        "--output",
        output,
        "--receipts",
        receipts,
    )

    assert completed.returncode == 0, completed.stderr
    term_map = json.loads(output.read_text(encoding="utf-8"))
    receipt = json.loads(receipts.read_text(encoding="utf-8"))
    assert term_map["terms"][0]["source"] == "空性"
    assert term_map["terms"][0]["status"] == "selected"
    assert receipt["search_script"] == str((ROOT / "terms-database" / "search.py").resolve())
    assert receipt["exit_code"] == 0


def write_media_project(project: Path, *, long_target=False):
    project.mkdir()
    (project / "source.dj").write_text("正念呼吸\n回到当下\n", encoding="utf-8")
    target = "A" * 90 if long_target else "Mindful breathing"
    (project / "target.dj").write_text(f"{target}\nReturn to the present\n", encoding="utf-8")
    (project / "source-map.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "media_sha256": "a" * 64,
                "segments": [
                    {"id": "s1", "start": 0.0, "end": 2.0, "source_line": 1},
                    {"id": "s2", "start": 2.0, "end": 4.0, "source_line": 2},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_subtitle_generation_and_strict_check(tmp_path):
    project = tmp_path / "media"
    write_media_project(project)

    generated = run_script("gen-subtitles.py", project)
    report = project / "subtitle-qa-report.json"
    checked = run_script(
        "check-subtitles.py", project, "--strict", "--output", report
    )

    assert generated.returncode == 0, generated.stderr
    assert checked.returncode == 0, checked.stderr
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "pass"
    for name in ("source.srt", "target.srt", "bilingual.srt", "source.vtt", "target.vtt", "bilingual.vtt"):
        assert (project / name).is_file()


def test_subtitle_check_fails_excessive_length_and_speed(tmp_path):
    project = tmp_path / "media"
    write_media_project(project, long_target=True)
    assert run_script("gen-subtitles.py", project).returncode == 0

    report = project / "subtitle-qa-report.json"
    checked = run_script("check-subtitles.py", project, "--strict", "--output", report)

    assert checked.returncode == 1
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert {item["name"] for item in payload["checks"] if item["status"] == "FAIL"} >= {
        "english_line_length",
        "english_reading_speed",
    }


def test_non_media_subtitle_report_is_explicitly_not_applicable(tmp_path):
    project = tmp_path / "document"
    project.mkdir()
    report = project / "subtitle-qa-report.json"

    completed = run_script(
        "check-subtitles.py", project, "--not-applicable", "--output", report
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "not_applicable"
    assert payload["checks"][0]["status"] == "N/A"


def test_strategy_c_doctor_checks_required_repository_files():
    completed = run_script("doctor.py", "--strategy-c", "--json")

    payload = json.loads(completed.stdout)
    assert payload["mode"] == "strategy-c"
    assert any(item["name"] == "file:scripts/check-translation.py" for item in payload["checks"])
    assert completed.returncode == (0 if payload["ok"] else 1)


def test_deepseek_flash_dry_run_is_blind_to_target_and_reads_no_credential(tmp_path):
    project = tmp_path / "flash"
    project.mkdir()
    example = ROOT / "examples" / "minimal-article"
    for name in ("source.dj", "translation-project.yaml", "term-map.yaml"):
        (project / name).write_bytes((example / name).read_bytes())
    (project / "target.dj").write_bytes(b"\xffTARGET_CANARY")

    environment = os.environ.copy()
    environment.pop("DEEPSEEK_API_KEY", None)
    completed = run_script(
        "deepseek-source-analysis.py", project, "--dry-run", env=environment
    )

    assert completed.returncode == 0, completed.stderr
    assert "no credential read" in completed.stdout
    assert not (project / "source-analysis.json").exists()


def test_deepseek_flash_rejects_command_line_credentials():
    completed = run_script(
        "deepseek-source-analysis.py",
        ROOT / "examples" / "minimal-article",
        "--api-key",
        "secret",
    )

    assert completed.returncode == 2
    assert "not accepted on the command line" in completed.stderr
    assert "secret" not in completed.stderr

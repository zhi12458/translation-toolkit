import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
WRAPPERS = (
    SCRIPTS / "docx2dj.fish",
    SCRIPTS / "dj2docx.fish",
    SCRIPTS / "compile-typst.fish",
    SCRIPTS / "split-bilingual.fish",
)
CONVERTER_WRAPPERS = WRAPPERS[:3]
FISH = shutil.which("fish")


@pytest.mark.parametrize("script", WRAPPERS)
def test_wrappers_have_argument_input_and_atomic_output_guards(script):
    text = script.read_text(encoding="utf-8")

    assert text.startswith("#!/usr/bin/env fish\n")
    assert "count $argv" in text
    assert "test -f" in text
    assert "test -r" in text
    assert "mktemp" in text
    assert "command mv -f --" in text


@pytest.mark.parametrize("script", CONVERTER_WRAPPERS)
def test_converter_wrappers_preserve_tool_status_and_delay_success_message(script):
    text = script.read_text(encoding="utf-8")

    assert "set tool_status $status" in text
    assert "exit $tool_status" in text
    assert "test -s" in text
    assert text.rfind("echo \"$out\"") > text.rfind("command mv -f --")


def test_split_never_deletes_destinations_before_validation_and_rejects_aliases():
    text = (SCRIPTS / "split-bilingual.fish").read_text(encoding="utf-8")

    assert 'rm -f "$dir/source.dj" "$dir/target.dj"' not in text
    assert 'test "$dj" = "$source_out"' in text
    assert 'test "$dj" = "$target_out"' in text
    assert text.index("test -s \"$_mpi_source_tmp\"") < text.index(
        'command mv -f -- "$_mpi_source_tmp"'
    )
    assert text.rfind('echo "target.dj: $target_out"') > text.rfind(
        'command mv -f -- "$_mpi_target_tmp"'
    )
    assert "pair_state" in text
    assert "CJK" not in text
    assert "source rollback failed" in text
    assert "previous source retained at" in text


def make_fake_tool(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/sh\nset -u\n" + body, encoding="utf-8")
    path.chmod(0o755)


def wrapper_env(bin_dir: Path, *, status: int = 0) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["FAKE_STATUS"] = str(status)
    return env


def run_fish(script: Path, *args: Path, env: dict[str, str]):
    assert FISH is not None
    return subprocess.run(
        [FISH, str(script), *(str(arg) for arg in args)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
@pytest.mark.parametrize(
    ("script_name", "tool_name", "input_name", "output_name"),
    [
        ("docx2dj.fish", "pandoc", "input.docx", "output.dj"),
        ("dj2docx.fish", "pandoc", "target.dj", "output.docx"),
        ("compile-typst.fish", "typst", "article.typ", "output.pdf"),
    ],
)
def test_converter_failure_status_is_preserved_and_old_output_survives(
    tmp_path, script_name, tool_name, input_name, output_name
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if tool_name == "pandoc":
        body = """
out=''
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-o" ]; then
        shift
        out="$1"
    fi
    shift
done
[ -z "$out" ] || printf 'partial output' > "$out"
exit "$FAKE_STATUS"
"""
    else:
        body = """
out=''
for arg in "$@"; do out="$arg"; done
[ -z "$out" ] || printf 'partial output' > "$out"
exit "$FAKE_STATUS"
"""
    make_fake_tool(bin_dir, tool_name, body)

    source = tmp_path / input_name
    source.write_text("input", encoding="utf-8")
    output = tmp_path / output_name
    output.write_text("previous output", encoding="utf-8")

    completed = run_fish(
        SCRIPTS / script_name,
        source,
        output,
        env=wrapper_env(bin_dir, status=42),
    )

    assert completed.returncode == 42
    assert completed.stdout == ""
    assert output.read_text(encoding="utf-8") == "previous output"
    assert not list(tmp_path.glob(".*.??????"))


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
def test_split_rejects_output_as_input_without_modifying_either_file(tmp_path):
    source = tmp_path / "source.dj"
    target = tmp_path / "target.dj"
    source.write_text("中文原文\n", encoding="utf-8")
    target.write_text("Existing English\n", encoding="utf-8")

    completed = run_fish(
        SCRIPTS / "split-bilingual.fish",
        source,
        env=os.environ.copy(),
    )

    assert completed.returncode == 64
    assert completed.stdout == ""
    assert source.read_text(encoding="utf-8") == "中文原文\n"
    assert target.read_text(encoding="utf-8") == "Existing English\n"


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
def test_invalid_split_preserves_previous_outputs(tmp_path):
    combined = tmp_path / "combined.dj"
    source = tmp_path / "source.dj"
    target = tmp_path / "target.dj"
    combined.write_text("只有中文\n", encoding="utf-8")
    source.write_text("old source\n", encoding="utf-8")
    target.write_text("old target\n", encoding="utf-8")

    completed = run_fish(
        SCRIPTS / "split-bilingual.fish",
        combined,
        env=os.environ.copy(),
    )

    assert completed.returncode == 65
    assert completed.stdout == ""
    assert source.read_text(encoding="utf-8") == "old source\n"
    assert target.read_text(encoding="utf-8") == "old target\n"


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
def test_valid_split_replaces_both_outputs_only_after_validation(tmp_path):
    combined = tmp_path / "combined.dj"
    source = tmp_path / "source.dj"
    target = tmp_path / "target.dj"
    combined.write_text("中文原文\nEnglish translation\n\n", encoding="utf-8")
    source.write_text("old source\n", encoding="utf-8")
    target.write_text("old target\n", encoding="utf-8")

    completed = run_fish(
        SCRIPTS / "split-bilingual.fish",
        combined,
        env=os.environ.copy(),
    )

    assert completed.returncode == 0
    assert source.read_text(encoding="utf-8") == "中文原文\n"
    assert target.read_text(encoding="utf-8") == "English translation\n"
    assert "source.dj:" in completed.stdout
    assert "target.dj:" in completed.stdout


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
def test_unpaired_bilingual_input_preserves_previous_outputs(tmp_path):
    combined = tmp_path / "combined.dj"
    source = tmp_path / "source.dj"
    target = tmp_path / "target.dj"
    combined.write_text(
        "第一行\nFirst line\n\n第二行\n",
        encoding="utf-8",
    )
    source.write_text("old source\n", encoding="utf-8")
    target.write_text("old target\n", encoding="utf-8")

    completed = run_fish(
        SCRIPTS / "split-bilingual.fish",
        combined,
        env=os.environ.copy(),
    )

    assert completed.returncode == 65
    assert completed.stdout == ""
    assert source.read_text(encoding="utf-8") == "old source\n"
    assert target.read_text(encoding="utf-8") == "old target\n"


@pytest.mark.skipif(
    FISH is None,
    reason="fish is not installed; static wrapper reliability assertions still ran",
)
def test_split_preserves_structural_blanks_without_language_guessing(tmp_path):
    combined = tmp_path / "combined.dj"
    combined.write_text(
        "2024\nIn 2024\n\n\n中文\nEnglish\n\n",
        encoding="utf-8",
    )

    completed = run_fish(
        SCRIPTS / "split-bilingual.fish",
        combined,
        env=os.environ.copy(),
    )

    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "source.dj").read_text(encoding="utf-8") == "2024\n\n中文\n"
    assert (tmp_path / "target.dj").read_text(encoding="utf-8") == "In 2024\n\nEnglish\n"

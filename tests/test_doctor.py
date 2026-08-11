import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "doctor.py"
SPEC = importlib.util.spec_from_file_location("mpi_doctor", MODULE_PATH)
doctor = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = doctor
SPEC.loader.exec_module(doctor)


def install_fake_inventory(monkeypatch, *, missing=()):
    missing = set(missing)

    def fake_which(command):
        return None if command in missing else f"/fake/bin/{command}"

    monkeypatch.setattr(doctor.shutil, "which", fake_which)
    monkeypatch.setattr(
        doctor,
        "_read_version",
        lambda path, args: (
            "Python 3.11.0"
            if Path(path).name == "python3"
            else f"{Path(path).name} test-version",
            None,
        ),
    )


def test_default_mode_reports_optional_gaps_without_failing(monkeypatch):
    install_fake_inventory(monkeypatch, missing={"fish", "typst"})

    report = doctor.build_report()

    assert report["mode"] == "default"
    assert report["required_ok"] is True
    assert report["optional_ok"] is False
    assert report["ok"] is True
    assert {check["command"] for check in report["checks"]} == {
        "python3",
        "git",
        "sqlite3",
        "uv",
        "fish",
        "pandoc",
        "typst",
        "pdftotext",
        "jq",
        "omp",
        "herdr",
    }


def test_strict_mode_fails_when_an_optional_tool_is_missing(monkeypatch):
    install_fake_inventory(monkeypatch, missing={"pandoc"})

    report = doctor.build_report(strict=True)

    assert report["mode"] == "strict"
    assert report["required_ok"] is True
    assert report["optional_ok"] is False
    assert report["ok"] is False


def test_minimal_mode_checks_only_required_tools(monkeypatch):
    install_fake_inventory(
        monkeypatch,
        missing={"uv", "fish", "pandoc", "typst", "omp", "herdr"},
    )

    report = doctor.build_report(minimal=True)

    assert report["mode"] == "minimal"
    assert report["ok"] is True
    assert [check["command"] for check in report["checks"]] == [
        "python3",
        "git",
        "sqlite3",
    ]


def test_missing_required_tool_fails_every_mode(monkeypatch):
    install_fake_inventory(monkeypatch, missing={"sqlite3"})

    assert doctor.build_report()["ok"] is False
    assert doctor.build_report(minimal=True)["ok"] is False


def test_unsupported_python_version_fails_required_check(monkeypatch):
    install_fake_inventory(monkeypatch)

    def fake_version(path, args):
        if Path(path).name == "python3":
            return "Python 3.10.14", None
        return f"{Path(path).name} test-version", None

    monkeypatch.setattr(doctor, "_read_version", fake_version)

    report = doctor.build_report(minimal=True)
    python = next(check for check in report["checks"] if check["name"] == "python")

    assert python["ok"] is False
    assert python["minimum_version"] == "3.11"
    assert "requires Python >= 3.11" in python["error"]
    assert report["ok"] is False


def test_json_output_is_machine_readable(monkeypatch, capsys):
    install_fake_inventory(monkeypatch)

    assert doctor.main(["--json", "--minimal"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["mode"] == "minimal"
    assert payload["ok"] is True
    assert all(check["required"] for check in payload["checks"])


def test_strict_and_minimal_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc_info:
        doctor.parse_args(["--strict", "--minimal"])
    assert exc_info.value.code == 2


def test_real_minimal_cli_smoke_test():
    completed = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--json", "--minimal"],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["mode"] == "minimal"
    assert {check["command"] for check in payload["checks"]} == {
        "python3",
        "git",
        "sqlite3",
    }
    assert completed.returncode == (0 if payload["ok"] else 1)

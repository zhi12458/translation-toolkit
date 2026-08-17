#!/usr/bin/env python3
"""Shared safe I/O helpers for cross-platform toolkit entry points."""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree


class ToolkitError(Exception):
    """A safe error that contains no document body."""


def resolve_input(value: str | os.PathLike[str], label: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ToolkitError(f"{label} is not a readable file: {path}")
    try:
        with path.open("rb"):
            pass
    except OSError as exc:
        raise ToolkitError(f"{label} is not readable: {path}") from exc
    return path


def resolve_output(value: str | os.PathLike[str], inputs: Sequence[Path]) -> Path:
    path = Path(value).expanduser().resolve()
    if path.exists() and path.is_dir():
        raise ToolkitError(f"output path is a directory: {path}")
    if not path.parent.is_dir():
        raise ToolkitError(f"output directory does not exist: {path.parent}")
    if any(path == item.resolve() for item in inputs):
        raise ToolkitError("input and output paths must differ")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def run_pandoc(input_path: Path, output_path: Path, *arguments: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=output_path.parent, prefix=f".{output_path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
        completed = subprocess.run(
            ["pandoc", str(input_path), *arguments, "-o", str(temporary)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise ToolkitError(f"pandoc failed with exit code {completed.returncode}")
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ToolkitError("pandoc produced an empty output")
        os.replace(temporary, output_path)
        temporary = None
    except FileNotFoundError as exc:
        raise ToolkitError("pandoc is required but was not found on PATH") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_docx_cjk_fonts(path: Path) -> None:
    """Set explicit platform CJK fonts so Word and headless renderers agree."""
    system = platform.system()
    east_asia_font = (
        "Arial Unicode MS"
        if system == "Darwin"
        else "Microsoft YaHei"
        if system == "Windows"
        else "Noto Sans CJK SC"
    )
    word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    namespace = f"{{{word_ns}}}"
    ElementTree.register_namespace("w", word_ns)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED
        ) as destination:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename in {"word/document.xml", "word/styles.xml"}:
                    root = ElementTree.fromstring(data)
                    for fonts in root.iter(f"{namespace}rFonts"):
                        for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
                            fonts.set(f"{namespace}{attribute}", east_asia_font)
                    for language in root.iter(f"{namespace}lang"):
                        language.set(f"{namespace}eastAsia", "zh-CN")
                    data = ElementTree.tostring(
                        root, encoding="utf-8", xml_declaration=True
                    )
                destination.writestr(info, data)
        os.replace(temporary, path)
        temporary = None
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ToolkitError("could not apply deterministic DOCX CJK fonts") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

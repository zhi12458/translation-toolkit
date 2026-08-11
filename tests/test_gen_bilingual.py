import importlib.util
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gen-bilingual.py"


def load_script():
    spec = importlib.util.spec_from_file_location("gen_bilingual", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen_bilingual = load_script()


class GenerateBilingualTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_empty_inputs_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Source is empty"):
            gen_bilingual.generate_bilingual_lines([], [])

    def test_blank_mask_mismatch_is_rejected(self):
        source = ["甲", "", "乙", "丙"]
        target = ["A", "B", "", "C"]

        with self.assertRaisesRegex(ValueError, r"line\(s\): 2, 3"):
            gen_bilingual.generate_bilingual_lines(source, target)

    def test_whitespace_only_lines_are_structural_blanks(self):
        lines = gen_bilingual.generate_bilingual_lines(
            ["甲", "   ", "乙"],
            ["A", "\t", "B"],
        )

        self.assertEqual(lines, ["甲", "A", "", "", "乙", "B", ""])

    def test_valid_input_uses_canonical_interleaving(self):
        lines = gen_bilingual.generate_bilingual_lines(
            ["甲", "", "乙"],
            ["A", "", "B"],
        )

        self.assertEqual(lines, ["甲", "A", "", "", "乙", "B", ""])

    def test_cli_fails_before_writing_stdout_on_alignment_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.dj"
            target = temp / "target.dj"
            source.write_text("甲\n\n乙\n", encoding="utf-8")
            target.write_text("A\nB\n\n", encoding="utf-8")

            result = self.run_cli(source, target)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Blank-line alignment mismatch", result.stderr)

    def test_stdout_mode_remains_compatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.dj"
            target = temp / "target.dj"
            source.write_text("甲\n\n乙\n", encoding="utf-8")
            target.write_text("A\n\nB\n", encoding="utf-8")

            result = self.run_cli(source, target)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "甲\nA\n\n\n乙\nB\n\n")

    def test_output_validation_failure_preserves_old_file_without_temp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.dj"
            target = temp / "target.dj"
            output = temp / "bilingual.dj"
            source.write_text("甲\n\n乙\n", encoding="utf-8")
            target.write_text("A\nB\n\n", encoding="utf-8")
            output.write_text("previous bilingual\n", encoding="utf-8")
            names_before = {path.name for path in temp.iterdir()}

            result = self.run_cli(source, target, "--output", output)
            names_after = {path.name for path in temp.iterdir()}

            self.assertEqual(output.read_text(encoding="utf-8"), "previous bilingual\n")
            self.assertEqual(names_after, names_before)
            self.assertEqual(list(temp.glob(f".{output.name}.*.tmp")), [])

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Blank-line alignment mismatch", result.stderr)

    def test_output_successfully_replaces_old_file_without_temp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.dj"
            target = temp / "target.dj"
            output = temp / "bilingual.dj"
            source.write_text("甲\n\n乙\n", encoding="utf-8")
            target.write_text("A\n\nB\n", encoding="utf-8")
            output.write_text("previous bilingual\n", encoding="utf-8")

            result = self.run_cli(source, target, "--output", output)

            self.assertEqual(
                output.read_text(encoding="utf-8"),
                "甲\nA\n\n\n乙\nB\n\n",
            )
            self.assertEqual(list(temp.glob(f".{output.name}.*.tmp")), [])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_new_output_is_private_and_existing_mode_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            new_output = temp / "new.dj"
            old_output = temp / "old.dj"
            old_output.write_text("old\n", encoding="utf-8")
            old_output.chmod(0o640)

            gen_bilingual.atomic_write_text(new_output, "new\n")
            gen_bilingual.atomic_write_text(old_output, "replacement\n")

            new_mode = stat.S_IMODE(new_output.stat().st_mode)
            old_mode = stat.S_IMODE(old_output.stat().st_mode)

        self.assertEqual(new_mode & 0o077, 0)
        self.assertEqual(old_mode, 0o640)

    def test_replace_failure_preserves_old_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            output = temp / "bilingual.dj"
            output.write_text("previous bilingual\n", encoding="utf-8")

            with mock.patch.object(
                gen_bilingual.os,
                "replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaisesRegex(OSError, "simulated replace failure"):
                    gen_bilingual.atomic_write_text(output, "new bilingual\n")

            self.assertEqual(output.read_text(encoding="utf-8"), "previous bilingual\n")
            self.assertEqual(list(temp.glob(f".{output.name}.*.tmp")), [])

    def test_output_cannot_alias_an_input(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source.dj"
            target = temp / "target.dj"
            original_source = "甲\n"
            source.write_text(original_source, encoding="utf-8")
            target.write_text("A\n", encoding="utf-8")
            names_before = {path.name for path in temp.iterdir()}

            result = self.run_cli(source, target, "--output", source)

            self.assertEqual(source.read_text(encoding="utf-8"), original_source)
            self.assertEqual({path.name for path in temp.iterdir()}, names_before)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("Output path must differ", result.stderr)


if __name__ == "__main__":
    unittest.main()

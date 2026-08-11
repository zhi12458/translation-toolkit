import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-translation.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_translation_bilingual", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_script()


class BilingualFreshnessTests(unittest.TestCase):
    def test_missing_bilingual_is_skip(self):
        result = gate.check_bilingual(["甲"], ["A"], None)

        self.assertEqual(result[0], gate.SKIP)

    def test_fresh_bilingual_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bilingual.dj"
            path.write_text("甲\nA\n\n\n乙\nB\n\n", encoding="utf-8")
            result = gate.check_bilingual(
                ["甲", "", "乙"], ["A", "", "B"], path
            )

        self.assertEqual(result[0], gate.PASS)

    def test_stale_bilingual_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bilingual.dj"
            path.write_text("甲\nold\n\n", encoding="utf-8")
            result = gate.check_bilingual(["甲"], ["A"], path)

        self.assertEqual(result[0], gate.FAIL)

    def test_blank_shift_cannot_be_declared_fresh(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bilingual.dj"
            path.write_text("甲\nA\n\n", encoding="utf-8")
            result = gate.check_bilingual(
                ["甲", "", "乙"], ["A", "B", ""], path
            )

        self.assertEqual(result[0], gate.FAIL)
        self.assertIn("blank lines differ", result[1])


if __name__ == "__main__":
    unittest.main()

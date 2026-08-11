import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-translation.py"


def load_script():
    spec = importlib.util.spec_from_file_location("check_translation_numbers", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load_script()


class NumberFidelityTests(unittest.TestCase):
    def assert_passes(self, source, target):
        self.assertEqual(gate.check_digits([source], [target])[0], gate.PASS)

    def assert_fails(self, source, target):
        self.assertEqual(gate.check_digits([source], [target])[0], gate.FAIL)

    def test_zero_requires_zero_or_zero_word(self):
        self.assert_fails("0", "nothing")
        self.assert_passes("0", "zero")

    def test_number_does_not_match_inside_digits_or_words(self):
        self.assert_fails("1", "10")
        self.assert_fails("1", "1.5")
        self.assert_fails("1", "none")

    def test_number_does_not_match_inside_larger_english_number_phrase(self):
        for source, target in (
            ("1", "one hundred"),
            ("2", "two thousand"),
            ("10", "ten million"),
            ("0", "zero point five"),
            ("1", "one point five"),
            ("100", "one hundred million"),
            ("1", "one trillion"),
            ("1", "twenty-one"),
            ("5", "twenty-five"),
            ("2", "twenty-two"),
            ("20", "one hundred and twenty"),
            ("100", "one hundred and one"),
        ):
            with self.subTest(source=source, target=target):
                self.assert_fails(source, target)

    def test_separate_number_phrases_remain_matchable(self):
        self.assert_passes("1与2", "one and two")
        self.assert_passes("1，2", "one, two")

    def test_list_number_may_end_with_punctuation(self):
        self.assert_passes("- 1", "- 1. First point")

    def test_numeric_ranges_claim_each_endpoint(self):
        self.assertEqual(
            gate.check_digits(["每天练 5-10 分钟"], ["Practice for 5–10 minutes."], strict=True)[0],
            gate.PASS,
        )

    def test_extra_target_digit_warns_in_draft_and_strict(self):
        self.assertEqual(gate.check_digits(["5"], ["5-10"])[0], gate.WARN)
        self.assertEqual(
            gate.check_digits(["5"], ["5-10"], strict=True)[0], gate.WARN
        )

    def test_chinese_number_words_may_legitimately_create_target_digits(self):
        for source, target in (
            ("第五部分", "Part 5"),
            ("世界五百强", "Fortune Global 500"),
            ("百问", "100 Questions"),
        ):
            with self.subTest(source=source, target=target):
                self.assertEqual(
                    gate.check_digits([source], [target], strict=True)[0], gate.WARN
                )

    def test_number_multiplicity_is_preserved(self):
        self.assert_fails("1与1", "one")
        self.assert_passes("1与1", "one and 1")

    def test_number_is_checked_on_corresponding_line(self):
        result = gate.check_digits(["1", "2"], ["two", "one"])

        self.assertEqual(result[0], gate.FAIL)

    def test_comma_and_word_forms_remain_supported(self):
        self.assert_passes("1000", "a thousand")
        self.assert_passes("1200", "1,200")
        self.assert_passes("1200", "twelve hundred")

    def test_decimal_digit_and_word_forms_are_supported(self):
        self.assert_passes("0.5", "0.5")
        self.assert_passes("0.5", "zero point five")
        self.assert_fails("0.5", "0 and 5")

    def test_wan_and_yi_scaling_remain_supported(self):
        self.assert_passes("10亿", "a billion")
        self.assert_passes("100万", "a million")
        self.assert_passes("180亿", "18 billion")
        self.assert_passes("1300万", "13 million")
        self.assert_passes("15亿", "1.5 billion")
        self.assert_passes("1.5亿", "150 million")

    def test_wan_and_yi_must_not_match_unscaled_coefficients(self):
        self.assert_fails("180亿", "180")
        self.assert_fails("1300万", "1,300")
        self.assert_fails("8万", "8")
        self.assert_fails("1300多万", "1,300")

    def test_approximate_wan_accepts_plus_form(self):
        self.assert_passes("1300多万", "13+ million")
        self.assert_passes("1300多万", "over 13 million")
        self.assert_fails("1300多万", "13 million")
        self.assert_fails("1300多万", "13,000,000")

    def test_date_numbers_may_reorder_and_month_may_be_named(self):
        self.assert_passes("2024年8月11日", "August 11, 2024")
        self.assert_passes("2024年8月11日", "August 11th, 2024")

    def test_century_numbers_may_use_english_ordinals(self):
        self.assert_passes("公元前6世纪到公元13世纪", "from the 6th to the 13th century")

    def test_explicit_chinese_rank_may_use_english_ordinal(self):
        self.assert_passes("排在第71位", "ranked 71st")
        self.assert_fails("共71位", "71st in total")

    def test_ordinal_quarter_and_half_are_not_treated_as_compound_numbers(self):
        self.assert_passes("第1季度", "the first quarter")
        self.assert_passes("第2季度", "the second quarter")
        self.assert_passes("第1个半年", "the first half")


if __name__ == "__main__":
    unittest.main()
